// firmware/main/pins.h
#pragma once
#include "driver/gpio.h"

#define PIN_STEP        GPIO_NUM_1
#define PIN_DIR         GPIO_NUM_2
#define PIN_ENABLE      GPIO_NUM_3
#define PIN_RGB_LED     GPIO_NUM_8   // onboard WS2812

#define DIR_ACTIVE_LEVEL    1        // DIR level for positive microsteps
#define ENABLE_ACTIVE_LEVEL 1        // level that energises the ADB-5331A
#define STEP_PULSE_US       3        // STEP high time (>= driver min, verify datasheet)
