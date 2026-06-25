// firmware/host_test/test_ramp.c
#include "minunit.h"
#include "ramp.h"

static const ramp_profile_t P = { .v_start = 200, .v_max = 4000, .accel = 20000 };

MU_TEST(first_step_near_vstart) {
    unsigned us = ramp_interval_us(&P, 2000, 0);
    mu_assert_dbl_near(1e6 / 200.0, (double)us, 60.0);   // ~5000 us
}
MU_TEST(cruise_reaches_vmax) {
    unsigned mid = ramp_interval_us(&P, 2000, 1000);     // long move -> cruising
    mu_assert_dbl_near(1e6 / 4000.0, (double)mid, 5.0);  // ~250 us
}
MU_TEST(profile_is_symmetric) {
    unsigned a = ramp_interval_us(&P, 2000, 3);
    unsigned b = ramp_interval_us(&P, 2000, 2000 - 1 - 3);
    mu_assert_int_eq((long)a, (long)b);
}
MU_TEST(triangular_move_never_reaches_vmax) {
    // 50-step move with this accel can't reach v_max; mid interval slower than cruise
    unsigned mid = ramp_interval_us(&P, 50, 25);
    mu_check((double)mid > 1e6 / 4000.0 + 5.0);
}
MU_TEST(velocity_never_below_vstart) {
    // interval at any step never exceeds 1e6/v_start
    for (unsigned i = 0; i < 2000; i++)
        mu_check(ramp_interval_us(&P, 2000, i) <= (unsigned)(1e6 / 200.0) + 1);
}
MU_TEST_SUITE(ramp_suite) {
    MU_RUN_TEST(first_step_near_vstart);
    MU_RUN_TEST(cruise_reaches_vmax);
    MU_RUN_TEST(profile_is_symmetric);
    MU_RUN_TEST(triangular_move_never_reaches_vmax);
    MU_RUN_TEST(velocity_never_below_vstart);
}
int main(void) { MU_RUN_SUITE(ramp_suite); MU_REPORT(); return MU_EXIT_CODE; }
