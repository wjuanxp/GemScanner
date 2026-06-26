// firmware/host_test/test_command_parser.c
#include "minunit.h"
#include "command_parser.h"

MU_TEST(parses_step_signed) {
    command_t c = command_parse("STEP -1500\n");
    mu_assert_int_eq(CMD_STEP, c.kind);
    mu_assert_int_eq(1, c.has_arg);
    mu_assert_int_eq(-1500, c.i_arg);
}
MU_TEST(parses_movedeg_float) {
    command_t c = command_parse("MOVEDEG 2.5\r\n");
    mu_assert_int_eq(CMD_MOVEDEG, c.kind);
    mu_assert_dbl_near(2.5, c.d_arg, 1e-9);
}
MU_TEST(verb_is_case_insensitive) {
    mu_assert_int_eq(CMD_STATUS, command_parse("status").kind);
    mu_assert_int_eq(CMD_HOME, command_parse("Home\n").kind);
}
MU_TEST(setv_requires_arg) {
    mu_assert_int_eq(CMD_BADARG, command_parse("SETV\n").kind);
    mu_assert_int_eq(CMD_BADARG, command_parse("SETV abc\n").kind);
}
MU_TEST(unknown_verb) {
    mu_assert_int_eq(CMD_UNKNOWN, command_parse("WIGGLE 3\n").kind);
}
MU_TEST(status_and_home_take_no_arg) {
    command_t c = command_parse("STATUS\n");
    mu_assert_int_eq(CMD_STATUS, c.kind);
    mu_assert_int_eq(0, c.has_arg);
}
MU_TEST_SUITE(parser_suite) {
    MU_RUN_TEST(parses_step_signed);
    MU_RUN_TEST(parses_movedeg_float);
    MU_RUN_TEST(verb_is_case_insensitive);
    MU_RUN_TEST(setv_requires_arg);
    MU_RUN_TEST(unknown_verb);
    MU_RUN_TEST(status_and_home_take_no_arg);
}
int main(void) { MU_RUN_SUITE(parser_suite); MU_REPORT(); return MU_EXIT_CODE; }
