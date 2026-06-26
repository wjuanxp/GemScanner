#include "command_parser.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static int ci_eq(const char *a, const char *b) {
    while (*a && *b) { if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0; a++; b++; }
    return *a == 0 && *b == 0;
}

command_t command_parse(const char *line) {
    command_t c = { CMD_UNKNOWN, 0, 0, 0.0 };
    // Input lines are capped at 63 chars; longer lines are truncated before parsing.
    char buf[64];
    size_t n = 0;
    while (line[n] && n < sizeof(buf) - 1) { buf[n] = line[n]; n++; }
    buf[n] = 0;
    // strip trailing CR/LF/space
    while (n > 0 && (buf[n-1] == '\r' || buf[n-1] == '\n' || buf[n-1] == ' ' || buf[n-1] == '\t')) buf[--n] = 0;

    char *verb = buf;
    while (*verb == ' ' || *verb == '\t') verb++;
    char *arg = verb;
    while (*arg && *arg != ' ' && *arg != '\t') arg++;
    if (*arg) *arg++ = 0;   // terminate the verb if a separator was found
    while (*arg == ' ' || *arg == '\t') arg++;
    int arg_present = (*arg != 0);

    struct { const char *name; cmd_kind_t kind; int wants; } table[] = {
        {"STEP", CMD_STEP, 'i'}, {"MOVEDEG", CMD_MOVEDEG, 'd'},
        {"SETV", CMD_SETV, 'i'}, {"SETACC", CMD_SETACC, 'i'},
        {"SETSETTLE", CMD_SETSETTLE, 'i'}, {"SETRES", CMD_SETRES, 'i'},
        {"HOME", CMD_HOME, 0}, {"STATUS", CMD_STATUS, 0},
    };
    for (size_t k = 0; k < sizeof(table)/sizeof(table[0]); k++) {
        if (!ci_eq(verb, table[k].name)) continue;
        c.kind = table[k].kind;
        if (table[k].wants == 0) { c.has_arg = 0; return c; }
        if (!arg_present) { c.kind = CMD_BADARG; return c; }
        char *end = NULL;
        if (table[k].wants == 'i') {
            long v = strtol(arg, &end, 10);
            if (end == arg || *end != 0) { c.kind = CMD_BADARG; return c; }
            c.i_arg = v; c.has_arg = 1;
        } else {
            double v = strtod(arg, &end);
            if (end == arg || *end != 0) { c.kind = CMD_BADARG; return c; }
            c.d_arg = v; c.has_arg = 1;
        }
        return c;
    }
    return c;  // CMD_UNKNOWN
}
