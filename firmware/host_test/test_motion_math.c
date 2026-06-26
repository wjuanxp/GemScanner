// firmware/host_test/test_motion_math.c
#include "minunit.h"
#include "motion_math.h"

MU_TEST(deg_to_steps_rounds) {
    mu_assert_int_eq(5000, mm_degrees_to_microsteps(90.0, 20000));
    mu_assert_int_eq(-5000, mm_degrees_to_microsteps(-90.0, 20000));
    mu_assert_int_eq(56, mm_degrees_to_microsteps(1.0, 20000)); // 55.56 -> 56
}
MU_TEST(steps_to_deg) {
    mu_assert_dbl_near(90.0, mm_microsteps_to_degrees(5000, 20000), 1e-9);
}
MU_TEST(wrap) {
    mu_assert_dbl_near(10.0, mm_wrap_deg(370.0), 1e-9);
    mu_assert_dbl_near(350.0, mm_wrap_deg(-10.0), 1e-9);
    mu_assert_dbl_near(0.0, mm_wrap_deg(360.0), 1e-9);
}
MU_TEST_SUITE(mm_suite) {
    MU_RUN_TEST(deg_to_steps_rounds);
    MU_RUN_TEST(steps_to_deg);
    MU_RUN_TEST(wrap);
}
int main(void) { MU_RUN_SUITE(mm_suite); MU_REPORT(); return MU_EXIT_CODE; }
