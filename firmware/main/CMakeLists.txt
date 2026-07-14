# firmware/main/CMakeLists.txt
idf_component_register(SRCS "app_main.c" "stepper.c" "usb_cdc.c" "controller.c" "status_display.c"
                       INCLUDE_DIRS "."
                       REQUIRES command_parser motion_math ramp fmt_num driver esp_lcd)
