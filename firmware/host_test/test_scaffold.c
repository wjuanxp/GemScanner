// firmware/host_test/test_scaffold.c
#include "minunit.h"

MU_TEST(scaffold_runs) {
    mu_assert_int_eq(2, 1 + 1);
}

MU_TEST_SUITE(scaffold_suite) {
    MU_RUN_TEST(scaffold_runs);
}

int main(void) {
    MU_RUN_SUITE(scaffold_suite);
    MU_REPORT();
    return MU_EXIT_CODE;
}
