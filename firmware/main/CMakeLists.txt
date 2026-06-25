# firmware/main/CMakeLists.txt
idf_component_register(SRCS "app_main.c" "stepper.c"
                       INCLUDE_DIRS "."
                       REQUIRES ramp driver)
