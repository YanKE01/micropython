// Both of these can be set by mpconfigboard.cmake if a BOARD_VARIANT is
// specified.

#ifndef MICROPY_HW_BOARD_NAME
#define MICROPY_HW_BOARD_NAME "ESP32 P4X EYE"
#endif

#ifndef MICROPY_HW_MCU_NAME
#define MICROPY_HW_MCU_NAME "ESP32P4"
#endif

#define MICROPY_WRAP_TUD_CDC_RX_CB(name) __mp_##name
#define MICROPY_WRAP_TUD_EVENT_HOOK_CB(name) __mp_##name

#define MICROPY_HW_USB_VID 0x37C5
#define MICROPY_HW_USB_PID 0x1206
#define MICROPY_HW_USB_MANUFACTURER_STRING "OpenMV"
#define MICROPY_HW_USB_PRODUCT_FS_STRING "OpenMV Virtual Comm Port in HS Mode"
#define MICROPY_HW_USB_CDC_INTERFACE_STRING "OpenMV CDC"

#define MICROPY_PY_ESPNOW                (0)

#define MICROPY_HW_ENABLE_SDCARD            (1)

#ifndef USB_SERIAL_JTAG_PACKET_SZ_BYTES
#define USB_SERIAL_JTAG_PACKET_SZ_BYTES (64)
#endif

// Enable UART REPL for modules that have an external USB-UART and don't use native USB.
#define MICROPY_HW_ENABLE_UART_REPL     (1)

#define MICROPY_PY_MACHINE_I2S          (1)

// Disable Wi-Fi and Bluetooth by default, these are re-enabled in the WIFI variants
#ifndef MICROPY_PY_NETWORK_WLAN
#define MICROPY_PY_NETWORK_WLAN         (0)
#endif
#ifndef MICROPY_PY_BLUETOOTH
#define MICROPY_PY_BLUETOOTH            (0)
#endif
