// firmware/host_test/test_fmt_num.c
#include "minunit.h"
#include "fmt_num.h"
#include <string.h>

static char buf[32];

MU_TEST(groups_basic) {
    fmt_thousands(0, buf, sizeof(buf));        mu_check(strcmp(buf, "0") == 0);
    fmt_thousands(999, buf, sizeof(buf));      mu_check(strcmp(buf, "999") == 0);
    fmt_thousands(1000, buf, sizeof(buf));     mu_check(strcmp(buf, "1,000") == 0);
    fmt_thousands(35000, buf, sizeof(buf));    mu_check(strcmp(buf, "35,000") == 0);
    fmt_thousands(1234567, buf, sizeof(buf));  mu_check(strcmp(buf, "1,234,567") == 0);
}
MU_TEST(negatives) {
    fmt_thousands(-35000, buf, sizeof(buf));   mu_check(strcmp(buf, "-35,000") == 0);
    fmt_thousands(-1, buf, sizeof(buf));       mu_check(strcmp(buf, "-1") == 0);
}
MU_TEST(returns_full_len_and_truncates) {
    size_t n = fmt_thousands(1234567, buf, sizeof(buf));
    mu_assert_int_eq(9, (int)n);               // "1,234,567"
    char small[4];
    size_t n2 = fmt_thousands(1234567, small, sizeof(small)); // fits "1,2" + NUL
    mu_assert_int_eq(9, (int)n2);              // full length still reported
    mu_check(strcmp(small, "1,2") == 0);       // truncated, NUL-terminated
}
MU_TEST_SUITE(fmt_suite) {
    MU_RUN_TEST(groups_basic);
    MU_RUN_TEST(negatives);
    MU_RUN_TEST(returns_full_len_and_truncates);
}
int main(void) { MU_RUN_SUITE(fmt_suite); MU_REPORT(); return MU_EXIT_CODE; }
