#pragma once
long   mm_degrees_to_microsteps(double deg, long steps_per_rev);
double mm_microsteps_to_degrees(long steps, long steps_per_rev);
double mm_wrap_deg(double deg);
