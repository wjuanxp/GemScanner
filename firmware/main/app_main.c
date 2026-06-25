// firmware/main/app_main.c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void) {
    printf("gemscanner-fw boot\n");
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
