// firmware/components/motion_math/motion_math.c
#include "motion_math.h"
#include <math.h>

long mm_degrees_to_microsteps(double deg, long steps_per_rev) {
    double s = deg / 360.0 * (double)steps_per_rev;
    return (long)llround(s);
}
double mm_microsteps_to_degrees(long steps, long steps_per_rev) {
    if (steps_per_rev == 0) return 0.0;
    return (double)steps / (double)steps_per_rev * 360.0;
}
double mm_wrap_deg(double deg) {
    double w = fmod(deg, 360.0);
    if (w < 0) w += 360.0;
    return w;
}
