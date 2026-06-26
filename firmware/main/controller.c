// firmware/main/controller.c
#include "controller.h"
#include "command_parser.h"
#include "motion_math.h"
#include "ramp.h"
#include "stepper.h"
#include "usb_cdc.h"
#include "status_display.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>

static long pos_steps = 0;
static long steps_per_rev = 0;
static ramp_profile_t profile = { .v_start = 200, .v_max = 4000, .accel = 20000 };
static unsigned settle_ms = 150;

static double cur_angle(void) {
    return mm_wrap_deg(mm_microsteps_to_degrees(pos_steps, steps_per_rev));
}

static void do_move(long microsteps) {
    usb_cdc_write_line("OK");
    status_display_set(ST_MOVING, cur_angle(), pos_steps);
    stepper_move_blocking(microsteps, &profile);
    pos_steps += microsteps;
    status_display_set(ST_SETTLING, cur_angle(), pos_steps);
    vTaskDelay(pdMS_TO_TICKS(settle_ms));
    status_display_set(ST_IDLE, cur_angle(), pos_steps);
    usb_cdc_write_line("READY");
}

void controller_run(void) {
    char line[80], out[160];
    for (;;) {
        if (usb_cdc_read_line(line, sizeof(line)) < 0) continue;
        command_t c = command_parse(line);
        switch (c.kind) {
        case CMD_STEP: do_move(c.i_arg); break;
        case CMD_MOVEDEG:
            if (steps_per_rev <= 0) { usb_cdc_write_line("ERR nores"); break; }
            do_move(mm_degrees_to_microsteps(c.d_arg, steps_per_rev)); break;
        case CMD_SETV:  if (c.i_arg > 0) { profile.v_max = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETACC:if (c.i_arg > 0) { profile.accel = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETSETTLE: if (c.i_arg >= 0) { settle_ms = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETRES: if (c.i_arg > 0) { steps_per_rev = c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_HOME: pos_steps = 0; usb_cdc_write_line("OK"); usb_cdc_write_line("READY"); break;
        case CMD_STATUS: {
            double deg = mm_wrap_deg(mm_microsteps_to_degrees(pos_steps, steps_per_rev));
            snprintf(out, sizeof(out),
                "STATUS angle=%.3f steps=%ld state=idle v=%u a=%u settle=%u res=%ld",
                deg, pos_steps, profile.v_max, profile.accel, settle_ms, steps_per_rev);
            usb_cdc_write_line(out); break;
        }
        case CMD_BADARG: usb_cdc_write_line("ERR badarg"); break;
        default: usb_cdc_write_line("ERR unknown"); break;
        }
    }
}
