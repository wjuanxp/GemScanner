#pragma once

typedef enum { CMD_STEP, CMD_MOVEDEG, CMD_SETV, CMD_SETACC, CMD_SETSETTLE,
               CMD_SETRES, CMD_HOME, CMD_STATUS, CMD_UNKNOWN, CMD_BADARG } cmd_kind_t;

typedef struct { cmd_kind_t kind; int has_arg; long i_arg; double d_arg; } command_t;

command_t command_parse(const char *line);
