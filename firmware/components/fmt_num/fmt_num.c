// firmware/components/fmt_num/fmt_num.c
#include "fmt_num.h"
#include <string.h>

size_t fmt_thousands(long value, char *out, size_t n) {
    int neg = value < 0;
    // Negate safely without overflowing LONG_MIN.
    unsigned long uv = neg ? (unsigned long)(-(value + 1)) + 1UL : (unsigned long)value;

    char digits[24];   // least-significant digit first
    int d = 0;
    do { digits[d++] = (char)('0' + (int)(uv % 10)); uv /= 10; } while (uv);

    char rev[32];      // digits + commas, still reversed
    int t = 0;
    for (int i = 0; i < d; i++) {
        if (i && (i % 3) == 0) rev[t++] = ',';
        rev[t++] = digits[i];
    }

    char final[36];    // sign + grouped digits + NUL (64-bit long worst case: 1+20+6+1 = 28)
    int f = 0;
    if (neg) final[f++] = '-';
    for (int i = t - 1; i >= 0; i--) final[f++] = rev[i];
    final[f] = '\0';

    size_t len = (size_t)f;
    if (n == 0) return len;
    size_t cpy = len < (n - 1) ? len : (n - 1);
    memcpy(out, final, cpy);
    out[cpy] = '\0';
    return len;
}
