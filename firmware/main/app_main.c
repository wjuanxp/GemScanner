#include "status_display.h"
#include "stepper.h"
#include "usb_cdc.h"
#include "controller.h"
void app_main(void) {
    status_display_init();
    stepper_init();
    usb_cdc_init();
    controller_run();   // never returns
}
