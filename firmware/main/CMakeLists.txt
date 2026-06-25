# firmware/main/CMakeLists.txt
idf_component_register(SRCS "app_main.c" "stepper.c" "usb_cdc.c" "controller.c"
                       INCLUDE_DIRS "."
                       REQUIRES command_parser motion_math ramp driver)
