// firmware/components/fmt_num/include/fmt_num.h
#pragma once
#include <stddef.h>

// Format `value` with comma thousands-separators into `out` (<= n bytes incl NUL).
// Returns the full formatted length (excluding NUL), even when truncated.
size_t fmt_thousands(long value, char *out, size_t n);
