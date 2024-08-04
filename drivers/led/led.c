#include "led.h"
#include "driver/gpio.h"
#include <stdio.h>

void hw_led_init()
{
    gpio_config_t io_cfg = {
        .mode = GPIO_MODE_OUTPUT,
        .intr_type = GPIO_INTR_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pin_bit_mask = (1ull << GPIO_NUM_11),
    };
    gpio_config(&io_cfg);
}

void hw_led_on()
{
    gpio_set_level(GPIO_NUM_11, 1);
}

void hw_led_off()
{
    gpio_set_level(GPIO_NUM_11, 0);
}

/******************************************************************************
 * object function wrappers.
 *****************************************************************************/
static mp_obj_t led_init_func(void)
{
    hw_led_init();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(led_init_obj, led_init_func);

static mp_obj_t led_on_func(void)
{
    hw_led_on();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(led_on_obj, led_on_func);

static mp_obj_t led_off_func(void)
{
    hw_led_off();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(led_off_obj, led_off_func);

static const mp_rom_map_elem_t led_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&led_init_obj)},
    {MP_ROM_QSTR(MP_QSTR_on), MP_ROM_PTR(&led_on_obj)},
    {MP_ROM_QSTR(MP_QSTR_off), MP_ROM_PTR(&led_off_obj)},
};
static MP_DEFINE_CONST_DICT(led_module_globals, led_module_globals_table);

const mp_obj_module_t led_user_cmodule = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&led_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_led, led_user_cmodule);
