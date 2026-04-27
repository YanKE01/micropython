"""
This script processes the output from the C preprocessor and extracts all
qstr. Each qstr is transformed into a qstr definition of the form 'Q(...)'.

This script works with Python 3.3+.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import multiprocessing, multiprocessing.dummy


def _gcc_rsp_quote(arg):
    # GCC's @file convention: tokens are whitespace-separated. To embed
    # whitespace, wrap in double quotes with backslash-escape inside. Unquoted
    # backslashes are literal, so Windows paths without whitespace work as-is.
    if not arg:
        return '""'
    if not any(c in arg for c in ' \t\n\r"'):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Extract MP_QSTR_FOO macros.
_MODE_QSTR = "qstr"

# Extract MP_COMPRESSED_ROM_TEXT("") macros.  (Which come from MP_ERROR_TEXT)
_MODE_COMPRESS = "compress"

# Extract MP_REGISTER_(EXTENSIBLE_)MODULE(...) macros.
_MODE_MODULE = "module"

# Extract MP_REGISTER_ROOT_POINTER(...) macros.
_MODE_ROOT_POINTER = "root_pointer"


class PreprocessorError(Exception):
    pass


def is_c_source(fname):
    return os.path.splitext(fname)[1] in [".c"]


def is_cxx_source(fname):
    return os.path.splitext(fname)[1] in [".cc", ".cp", ".cxx", ".cpp", ".CPP", ".c++", ".C"]


def preprocess():
    if any(src in args.dependencies for src in args.changed_sources):
        sources = args.sources
    elif any(args.changed_sources):
        sources = args.changed_sources
    else:
        sources = args.sources
    csources = []
    cxxsources = []
    for source in sources:
        if is_cxx_source(source):
            cxxsources.append(source)
        elif is_c_source(source):
            csources.append(source)
    try:
        os.makedirs(os.path.dirname(args.output[0]))
    except OSError:
        pass

    def pp(flags):
        def run(files):
            # Spill flags + files to a per-chunk response file. ESP-IDF + OpenMV
            # already pushes the combined arg list past Windows' CreateProcess
            # 32K limit even after per-CPU chunking, so use GCC's @file syntax
            # to keep the actual command line short.
            fd, rsp_path = tempfile.mkstemp(suffix=".qstr.rsp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as rsp:
                    for arg in list(flags) + list(files):
                        rsp.write(_gcc_rsp_quote(arg))
                        rsp.write("\n")
                try:
                    return subprocess.check_output(args.pp + ["@" + rsp_path])
                except subprocess.CalledProcessError as er:
                    raise PreprocessorError(str(er))
            finally:
                try:
                    os.unlink(rsp_path)
                except OSError:
                    pass

        return run

    try:
        cpus = multiprocessing.cpu_count()
    except NotImplementedError:
        cpus = 1
    p = multiprocessing.dummy.Pool(cpus)
    with open(args.output[0], "wb") as out_file:
        for flags, sources in (
            (args.cflags, csources),
            (args.cxxflags, cxxsources),
        ):
            batch_size = (len(sources) + cpus - 1) // cpus
            chunks = [sources[i : i + batch_size] for i in range(0, len(sources), batch_size or 1)]
            for output in p.imap(pp(flags), chunks):
                out_file.write(output)


def write_out(fname, output):
    if output:
        for m, r in [("/", "__"), ("\\", "__"), (":", "@"), ("..", "@@")]:
            fname = fname.replace(m, r)
        with open(args.output_dir + "/" + fname + "." + args.mode, "w") as f:
            f.write("\n".join(output) + "\n")


def process_file(f):
    # match gcc-like output (# n "file") and msvc-like output (#line n "file")
    re_line = re.compile(r"^#(?:line)?\s+\d+\s\"([^\"]+)\"")
    if args.mode == _MODE_QSTR:
        re_match = re.compile(r"MP_QSTR_[_a-zA-Z0-9]+")
    elif args.mode == _MODE_COMPRESS:
        re_match = re.compile(r'MP_COMPRESSED_ROM_TEXT\("([^"]*)"\)')
    elif args.mode == _MODE_MODULE:
        re_match = re.compile(
            r"(?:MP_REGISTER_MODULE|MP_REGISTER_EXTENSIBLE_MODULE|MP_REGISTER_MODULE_DELEGATION)\(.*?,\s*.*?\);"
        )
    elif args.mode == _MODE_ROOT_POINTER:
        re_match = re.compile(r"MP_REGISTER_ROOT_POINTER\(.*?\);")
    output = []
    last_fname = None
    for line in f:
        if line.isspace():
            continue
        m = re_line.match(line)
        if m:
            fname = m.group(1)
            if not is_c_source(fname) and not is_cxx_source(fname):
                continue
            if fname != last_fname:
                write_out(last_fname, output)
                output = []
                last_fname = fname
            continue
        for match in re_match.findall(line):
            if args.mode == _MODE_QSTR:
                name = match.replace("MP_QSTR_", "")
                output.append("Q(" + name + ")")
            elif args.mode in (_MODE_COMPRESS, _MODE_MODULE, _MODE_ROOT_POINTER):
                output.append(match)

    if last_fname:
        write_out(last_fname, output)
    return ""


def cat_together():
    import glob
    import hashlib

    hasher = hashlib.md5()
    all_lines = []
    for fname in glob.glob(args.output_dir + "/*." + args.mode):
        with open(fname, "rb") as f:
            lines = f.readlines()
            all_lines += lines
    all_lines.sort()
    all_lines = b"\n".join(all_lines)
    hasher.update(all_lines)
    new_hash = hasher.hexdigest()
    # print(new_hash)
    old_hash = None
    try:
        with open(args.output_file + ".hash") as f:
            old_hash = f.read()
    except IOError:
        pass
    mode_full = "QSTR"
    if args.mode == _MODE_COMPRESS:
        mode_full = "Compressed data"
    elif args.mode == _MODE_MODULE:
        mode_full = "Module registrations"
    elif args.mode == _MODE_ROOT_POINTER:
        mode_full = "Root pointer registrations"
    if old_hash != new_hash or not os.path.exists(args.output_file):
        print(mode_full, "updated")

        with open(args.output_file, "wb") as outf:
            outf.write(all_lines)
        with open(args.output_file + ".hash", "w") as f:
            f.write(new_hash)
    else:
        print(mode_full, "not updated")


if __name__ == "__main__":
    # Expand @file argv tokens so very long preprocessor invocations stay
    # under cmd.exe's 8KB single-line limit on Windows. Each non-blank line
    # in the file becomes one argv token.
    _expanded = []
    for _arg in sys.argv[1:]:
        if isinstance(_arg, str) and _arg.startswith("@") and len(_arg) > 1:
            try:
                with open(_arg[1:], "r", encoding="utf-8") as _f:
                    for _line in _f:
                        _line = _line.rstrip("\r\n")
                        if _line:
                            _expanded.append(_line)
                continue
            except OSError:
                pass
        _expanded.append(_arg)
    sys.argv[1:] = _expanded

    if len(sys.argv) < 6:
        print("usage: %s command mode input_filename output_dir output_file" % sys.argv[0])
        sys.exit(2)

    class Args:
        pass

    args = Args()
    args.command = sys.argv[1]

    if args.command == "pp":
        named_args = {
            s: []
            for s in [
                "pp",
                "output",
                "cflags",
                "cxxflags",
                "sources",
                "changed_sources",
                "dependencies",
            ]
        }

        for arg in sys.argv[1:]:
            if arg in named_args:
                current_tok = arg
            else:
                named_args[current_tok].append(arg)

        if not named_args["pp"] or len(named_args["output"]) != 1:
            print("usage: %s %s ..." % (sys.argv[0], " ... ".join(named_args)))
            sys.exit(2)

        for k, v in named_args.items():
            setattr(args, k, v)

        try:
            preprocess()
        except PreprocessorError as er:
            print(er)
            sys.exit(1)

        sys.exit(0)

    if args.command == "qstr_preprocess":
        # Pure-Python replacement for the
        #   cat <sources> | sed 's/^Q(.*)/"&"/' | <pp> @rsp - | sed 's/^"\(Q(.*)\)"/\1/' > <output>
        # shell pipeline that the qstrdefs.preprocessed.h rule used to run.
        # Windows cmd has no cat/sed/pipes, and the preprocessor invocation
        # also exceeds CreateProcess's 32K limit on this codebase, so flags
        # go through GCC's @file response file.
        named_args = {
            s: [] for s in ["qstr_preprocess", "output", "pp", "flags", "sources"]
        }
        for arg in sys.argv[1:]:
            if arg in named_args:
                current_tok = arg
            else:
                named_args[current_tok].append(arg)

        if not named_args["pp"] or len(named_args["output"]) != 1:
            print(
                "usage: %s qstr_preprocess output FILE pp CMD... flags FLAGS... sources FILES..."
                % sys.argv[0]
            )
            sys.exit(2)

        # Concatenate sources and wrap any "Q(...)"-style line in quotes so
        # the C preprocessor leaves it alone (the unwrap pass restores it).
        wrapped = io.BytesIO()
        for src in named_args["sources"]:
            with open(src, "rb") as sf:
                for line in sf:
                    stripped = line.rstrip(b"\r\n")
                    eol = line[len(stripped):]
                    if stripped.startswith(b"Q("):
                        wrapped.write(b'"' + stripped + b'"' + eol)
                    else:
                        wrapped.write(line)

        fd, rsp_path = tempfile.mkstemp(suffix=".qstr_pp.rsp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as rsp:
                for f in named_args["flags"]:
                    rsp.write(_gcc_rsp_quote(f) + "\n")
                rsp.write("-\n")
            try:
                pp_out = subprocess.check_output(
                    named_args["pp"] + ["@" + rsp_path],
                    input=wrapped.getvalue(),
                )
            except subprocess.CalledProcessError as er:
                print(er)
                sys.exit(1)
        finally:
            try:
                os.unlink(rsp_path)
            except OSError:
                pass

        # Unwrap the leading "...Q(...)..." quoting we added above. sed's
        # original pattern was `^"\(Q(.*)\)"` which is greedy up to the last
        # ")" before a closing `"`.
        unq = re.compile(rb'^"(Q\(.*\))"')
        out_path = named_args["output"][0]
        try:
            os.makedirs(os.path.dirname(out_path))
        except OSError:
            pass
        with open(out_path, "wb") as outf:
            for line in pp_out.splitlines(keepends=True):
                m = unq.match(line)
                if m:
                    outf.write(m.group(1) + line[m.end():])
                else:
                    outf.write(line)

        sys.exit(0)

    args.mode = sys.argv[2]
    args.input_filename = sys.argv[3]  # Unused for command=cat
    args.output_dir = sys.argv[4]
    args.output_file = None if len(sys.argv) == 5 else sys.argv[5]  # Unused for command=split

    if args.mode not in (_MODE_QSTR, _MODE_COMPRESS, _MODE_MODULE, _MODE_ROOT_POINTER):
        print("error: mode %s unrecognised" % sys.argv[2])
        sys.exit(2)

    try:
        os.makedirs(args.output_dir)
    except OSError:
        pass

    if args.command == "split":
        with io.open(args.input_filename, encoding="utf-8") as infile:
            process_file(infile)

    if args.command == "cat":
        cat_together()
