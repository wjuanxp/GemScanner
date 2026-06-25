// firmware/main/stepper.h
#pragma once
#include "ramp.h"
void stepper_init(void);
void stepper_move_blocking(long microsteps, const ramp_profile_t *profile);
