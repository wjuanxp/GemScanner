#pragma once
typedef struct { unsigned v_start; unsigned v_max; unsigned accel; } ramp_profile_t;
unsigned ramp_interval_us(const ramp_profile_t *p, unsigned total, unsigned i);
