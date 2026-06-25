// firmware/main/stepper.c
#include "stepper.h"
#include "pins.h"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static gptimer_handle_t s_timer;
static volatile unsigned s_total, s_index;
static volatile const ramp_profile_t *s_profile;
static volatile TaskHandle_t s_waiter;

// NOT IRAM_ATTR: default gptimer ISR runs from flash; callee helpers are flash-resident.
static bool on_alarm(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *arg) {
    (void)t; (void)e; (void)arg;
    gpio_set_level(PIN_STEP, 1);
    esp_rom_delay_us(STEP_PULSE_US);
    gpio_set_level(PIN_STEP, 0);
    s_index++;
    BaseType_t hp = pdFALSE;
    if (s_index >= s_total) {
        gptimer_stop(t);
        vTaskNotifyGiveFromISR(s_waiter, &hp);
    } else {
        // auto-reload to 0 => alarm_count is the relative interval to the next step
        gptimer_alarm_config_t a = { .reload_count = 0, .alarm_count =
            ramp_interval_us((const ramp_profile_t *)s_profile, s_total, s_index), .flags.auto_reload_on_alarm = true };
        gptimer_set_alarm_action(t, &a);
    }
    return hp == pdTRUE;
}

void stepper_init(void) {
    gpio_config_t io = { .pin_bit_mask = (1ULL<<PIN_STEP)|(1ULL<<PIN_DIR)|(1ULL<<PIN_ENABLE),
                         .mode = GPIO_MODE_OUTPUT };
    gpio_config(&io);
    gpio_set_level(PIN_ENABLE, ENABLE_ACTIVE_LEVEL);
    gpio_set_level(PIN_STEP, 0);

    gptimer_config_t cfg = { .clk_src = GPTIMER_CLK_SRC_DEFAULT,
                             .direction = GPTIMER_COUNT_UP, .resolution_hz = 1000000 }; // 1 us tick
    gptimer_new_timer(&cfg, &s_timer);
    gptimer_event_callbacks_t cbs = { .on_alarm = on_alarm };
    gptimer_register_event_callbacks(s_timer, &cbs, NULL);
    gptimer_enable(s_timer);
}

void stepper_move_blocking(long microsteps, const ramp_profile_t *profile) {
    if (microsteps == 0) return;
    gpio_set_level(PIN_DIR, microsteps > 0 ? DIR_ACTIVE_LEVEL : !DIR_ACTIVE_LEVEL);
    esp_rom_delay_us(5);  // DIR setup time before first pulse
    s_total = (unsigned)(microsteps > 0 ? microsteps : -microsteps);
    s_index = 0;
    s_profile = profile;
    s_waiter = xTaskGetCurrentTaskHandle();

    gptimer_set_raw_count(s_timer, 0);
    gptimer_alarm_config_t a = { .reload_count = 0,
        .alarm_count = ramp_interval_us((const ramp_profile_t *)s_profile, s_total, 0), .flags.auto_reload_on_alarm = true };
    gptimer_set_alarm_action(s_timer, &a);
    gptimer_start(s_timer);
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
}
