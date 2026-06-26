#include "ramp.h"
#include <math.h>

unsigned ramp_interval_us(const ramp_profile_t *p, unsigned total, unsigned i) {
    if (total == 0 || i >= total) return 0;
    double v_start = p->v_start > 0 ? (double)p->v_start : 1.0;
    double v_max   = p->v_max   > v_start ? (double)p->v_max : v_start;
    double accel   = p->accel   > 0 ? (double)p->accel : 1.0;

    // steps to ramp from v_start to v_max
    double accel_steps = (v_max*v_max - v_start*v_start) / (2.0 * accel);
    if (accel_steps > total / 2.0) accel_steps = total / 2.0;  // triangular

    double dist_from_end = (double)(total - 1 - i);
    double d = (double)i < accel_steps ? (double)i
             : (dist_from_end < accel_steps ? dist_from_end : accel_steps);
    double v = sqrt(v_start*v_start + 2.0*accel*d);
    if (v > v_max) v = v_max;
    if (v < v_start) v = v_start;
    return (unsigned)(1e6 / v + 0.5);
}
