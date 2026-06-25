// firmware/host_test/minunit.h  (compact MinUnit + float/int helpers)
#ifndef MINUNIT_H
#define MINUNIT_H
#include <stdio.h>
#include <math.h>

static int mu_tests_run = 0;
static int mu_fails = 0;

#define MU_TEST(name) static void name(void)
#define MU_TEST_SUITE(name) static void name(void)
#define MU_RUN_TEST(test) do { test(); mu_tests_run++; } while (0)
#define MU_RUN_SUITE(suite) do { suite(); } while (0)
#define MU_REPORT() printf("\n%d tests, %d failures\n", mu_tests_run, mu_fails)
#define MU_EXIT_CODE (mu_fails ? 1 : 0)

#define mu_check(cond) do { if (!(cond)) { \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); mu_fails++; } } while (0)
#define mu_assert_int_eq(exp, act) do { long _e=(exp),_a=(act); if (_e!=_a) { \
    printf("FAIL %s:%d: expected %ld got %ld\n", __FILE__, __LINE__, _e, _a); mu_fails++; } } while (0)
#define mu_assert_dbl_near(exp, act, eps) do { double _e=(exp),_a=(act); if (fabs(_e-_a)>(eps)) { \
    printf("FAIL %s:%d: expected %g got %g (eps %g)\n", __FILE__, __LINE__, _e, _a, (double)(eps)); mu_fails++; } } while (0)
#endif
