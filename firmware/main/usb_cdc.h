#pragma once
void usb_cdc_init(void);
int  usb_cdc_read_line(char *buf, int cap);
void usb_cdc_write_line(const char *s);
