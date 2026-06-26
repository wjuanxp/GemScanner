// firmware/main/status_display.c
#include "status_display.h"
#include "pins.h"
#include "led_strip.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_lvgl_port.h"
#include "lvgl.h"
#include "esp_log.h"
#include <stdio.h>

static const char *TAG = "status_display";

static led_strip_handle_t s_led;
static lv_obj_t *s_l_state, *s_l_angle, *s_l_steps;

static void led_set(uint8_t r, uint8_t g, uint8_t b) {
    led_strip_set_pixel(s_led, 0, r, g, b);
    led_strip_refresh(s_led);
}

static void lcd_init(void) {
    spi_bus_config_t bus = { .mosi_io_num = 6, .sclk_io_num = 7, .miso_io_num = -1,
        .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 172*320*2 };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
    esp_lcd_panel_io_handle_t io;
    esp_lcd_panel_io_spi_config_t io_cfg = { .dc_gpio_num = 15, .cs_gpio_num = 14,
        .pclk_hz = 40*1000*1000, .lcd_cmd_bits = 8, .lcd_param_bits = 8,
        .spi_mode = 0, .trans_queue_depth = 10 };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &io_cfg, &io));
    esp_lcd_panel_handle_t panel;
    esp_lcd_panel_dev_config_t pcfg = { .reset_gpio_num = 21, .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB, .bits_per_pixel = 16 };
    ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(io, &pcfg, &panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel));
    esp_lcd_panel_invert_color(panel, true);
    esp_lcd_panel_set_gap(panel, 34, 0);   // 172-wide ST7789 offset; tune on bench
    esp_lcd_panel_disp_on_off(panel, true);

    // Drive LCD backlight (GPIO22) high
    gpio_config_t bl = { .pin_bit_mask = (1ULL << 22), .mode = GPIO_MODE_OUTPUT };
    gpio_config(&bl);
    gpio_set_level(22, 1);   // LCD backlight on

    lvgl_port_cfg_t lp = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lp));
    lvgl_port_display_cfg_t dc = { .io_handle = io, .panel_handle = panel,
        .buffer_size = 172*40, .double_buffer = true, .hres = 172, .vres = 320,
        .rotation = { .swap_xy = false, .mirror_x = false, .mirror_y = false } };
    lv_display_t *disp = lvgl_port_add_disp(&dc);
    lv_obj_t *scr = lv_display_get_screen_active(disp);   // LVGL 9.x
    s_l_state = lv_label_create(scr); lv_obj_align(s_l_state, LV_ALIGN_TOP_LEFT, 6, 10);
    s_l_angle = lv_label_create(scr); lv_obj_align(s_l_angle, LV_ALIGN_TOP_LEFT, 6, 40);
    s_l_steps = lv_label_create(scr); lv_obj_align(s_l_steps, LV_ALIGN_TOP_LEFT, 6, 70);
}

void status_display_init(void) {
    led_strip_config_t sc = { .strip_gpio_num = PIN_RGB_LED, .max_leds = 1,
                              .led_model = LED_MODEL_WS2812 };
    led_strip_rmt_config_t rc = { .resolution_hz = 10*1000*1000 };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&sc, &rc, &s_led));
    lcd_init();
    status_display_set(ST_DISCONNECTED, 0.0, 0);
}

void status_display_set(disp_state_t state, double angle_deg, long steps) {
    switch (state) {
        case ST_DISCONNECTED: led_set(0, 0, 12); break;
        case ST_IDLE:         led_set(0, 30, 0); break;
        case ST_MOVING:       led_set(40, 20, 0); break;
        case ST_SETTLING:     led_set(0, 25, 25); break;
    }
    static const char *names[] = { "DISCONNECTED", "IDLE", "MOVING", "SETTLING" };
    char a[32], s[32];
    snprintf(a, sizeof(a), "angle=%.2f", angle_deg);
    snprintf(s, sizeof(s), "steps=%ld", steps);
    if (lvgl_port_lock(50)) {
        lv_label_set_text(s_l_state, names[state]);
        lv_label_set_text(s_l_angle, a);
        lv_label_set_text(s_l_steps, s);
        lvgl_port_unlock();
    } else {
        ESP_LOGW(TAG, "lvgl lock timeout");
    }
}
