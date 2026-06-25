#include "usb_cdc.h"
#include "driver/usb_serial_jtag.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

void usb_cdc_init(void) {
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    usb_serial_jtag_driver_install(&cfg);
}

int usb_cdc_read_line(char *buf, int cap) {
    int n = 0;
    for (;;) {
        uint8_t ch;
        int r = usb_serial_jtag_read_bytes(&ch, 1, portMAX_DELAY);
        if (r <= 0) continue;
        if (ch == '\n' || ch == '\r') {     // accept CR, LF, or CRLF as line end
            if (n == 0) continue;           // skip empty lines (e.g. the LF of a CRLF)
            buf[n] = 0;
            return n;
        }
        if (n < cap - 1) buf[n++] = (char)ch;
    }
}

void usb_cdc_write_line(const char *s) {
    usb_serial_jtag_write_bytes((const uint8_t *)s, strlen(s), portMAX_DELAY);
    usb_serial_jtag_write_bytes((const uint8_t *)"\n", 1, portMAX_DELAY);
}
