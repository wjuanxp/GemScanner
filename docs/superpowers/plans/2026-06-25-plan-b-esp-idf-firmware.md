# Plan B — ESP-IDF Firmware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Firmware for the Waveshare ESP32-C6-LCD-1.47 that drives the SURUGA SEIKI KRW06360 rotary stage (Oriental Motor 5-phase stepper via an ADB-5331A driver) under a USB-CDC command protocol, so the host PC can run step-and-settle scans.

**Architecture:** Pure, ESP-IDF-independent C modules (`command_parser`, `motion_math`, `ramp`) hold all testable logic and are unit-tested on the host with gcc+ctest (TDD). Thin ESP-IDF glue (`usb_cdc`, `stepper`, `status_display`, `controller`) wires those modules to hardware — GPTimer-driven STEP/DIR generation, the USB Serial/JTAG CDC link, the RGB LED + ST7789 LCD — and is verified on the bench. The controller runs a state machine: accept a move command → `OK` → ramp the stepper → settle → `READY`.

**Tech Stack:** C, ESP-IDF v5.x (installed at `D:\ESP32`), ESP32-C6 target. Host tests: MinGW gcc 13.2 + CMake/CTest 3.29. Managed components: `espressif/led_strip`, `lvgl/lvgl`, `espressif/esp_lvgl_port`.

## ESP-IDF 5.4 compatibility notes (pre-checked 2026-06-25)

The glue tasks (5, 6, 8) target ESP-IDF **5.4**. Apply these when implementing on the bench — they are folded into the task code where noted, plus these standing caveats:

- **B6 console vs. driver (most important).** `sdkconfig.defaults` sets `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`, so boot logs share the USB Serial/JTAG peripheral with the protocol. Installing `usb_serial_jtag_driver_install` while the console also owns that peripheral can interleave log bytes into the protocol stream. On the bench, if RX/replies misbehave, set the console to **None** (or route it to UART0) via `idf.py menuconfig → Component config → ESP System Settings → Channel for console output`, so the driver fully owns USB for the line protocol. Keep `printf` debugging off the protocol channel.
- **B5 GPTimer ISR not in IRAM.** The `on_alarm` callback is **not** marked `IRAM_ATTR` (the default gptimer ISR isn't in IRAM, and the callback calls flash-resident helpers; marking it IRAM without `CONFIG_GPTIMER_CTRL_FUNC_IN_IRAM` + all-IRAM callees would crash when the cache is disabled). `gptimer_set_alarm_action` and `gptimer_stop` are ISR-safe in 5.4. This is already reflected in the Task 5 code.
- **B8 led_strip v2.x.** Set `.led_model = LED_MODEL_WS2812` in `led_strip_config_t` (WS2812 is GRB); reflected in Task 8 code. `led_strip_new_rmt_device` + `led_strip_rmt_config_t{.resolution_hz}` are correct for v2.
- **B8 LVGL 9.2 / esp_lvgl_port v2.** In LVGL 9, prefer `lv_display_get_screen_active(disp)` over the deprecated `lv_disp_get_scr_act(disp)`. The 172-wide ST7789 panel has a column/row **offset** vs the controller's 240×320 RAM — call `esp_lcd_panel_set_gap(panel, X_OFFSET, Y_OFFSET)` and tune `X_OFFSET`/`Y_OFFSET` (commonly 34,0 for this panel) plus `mirror`/`swap_xy` on the bench until the labels sit correctly. `esp_lcd_panel_dev_config_t.rgb_ele_order` is the correct 5.4 field name.
- **General.** First `idf.py build` downloads the managed components named in `idf_component.yml`; ensure network access. Run `idf.py set-target esp32c6` once before the first build.

## Global Constraints

- Target chip: **esp32c6**. ESP-IDF environment is at `D:\ESP32` — activate it with `D:\ESP32\export.ps1` (PowerShell) or `D:/ESP32/export.bat` before any `idf.py` command.
- Host unit tests build with **gcc** + **CMake/CTest** and must NOT include any ESP-IDF header. The three pure components (`command_parser`, `motion_math`, `ramp`) contain **zero** `#include "esp_*"`/`driver/*`/FreeRTOS includes — only C stdlib.
- USB-CDC link uses the **USB Serial/JTAG** controller (`driver/usb_serial_jtag.h`), not TinyUSB.
- Driver interface: **1-pulse mode** — `STEP` (pulse) + `DIR` (direction) + `ENABLE` outputs, level-shifted 3.3 V→5 V to the ADB-5331A opto inputs (external buffer; see README wiring). Active levels are defined once in `main/pins.h`.
- **steps-per-360° is never hardcoded** — set at runtime via the `SETRES` command (motor step angle × driver microstep × stage gear ratio, calibrated by the PC). `MOVEDEG` returns `ERR nores` until `SETRES` is sent.
- **HOME does not move** (no origin sensor yet): it zeroes the logical angle and replies `OK` then `READY`.
- Protocol is line-based ASCII, `\n`-terminated, replies also `\n`-terminated. Exact command/response grammar is fixed in §Protocol below and must match across `command_parser` and `controller`.
- Candidate GPIOs (verify against the board silk; avoid strapping pins 8/9/15 and the LCD/SD pins 4,5,6,7,14,15,21,22): **STEP=GPIO1, DIR=GPIO2, ENABLE=GPIO3**, future HOME input=GPIO0, onboard RGB LED=GPIO8.

## Protocol (authoritative)

| Command | Meaning | Immediate reply | Deferred reply |
|---------|---------|-----------------|----------------|
| `STEP <n>` | Move `n` microsteps, signed (+ = DIR active) | `OK` (or `ERR busy`) | `READY` after move + settle |
| `MOVEDEG <x>` | Move `x` degrees (float) | `OK` / `ERR busy` / `ERR nores` | `READY` after move + settle |
| `SETV <v>` | Max speed, microsteps/s (uint) | `OK` / `ERR badarg` | — |
| `SETACC <a>` | Acceleration, microsteps/s² (uint) | `OK` / `ERR badarg` | — |
| `SETSETTLE <ms>` | Settle delay, ms (uint) | `OK` / `ERR badarg` | — |
| `SETRES <n>` | Microsteps per 360° (uint) | `OK` / `ERR badarg` | — |
| `HOME` | Zero logical angle (no motion) | `OK` | `READY` |
| `STATUS` | Query | `STATUS angle=<deg> steps=<n> state=<idle\|moving\|settling> v=<> a=<> settle=<ms> res=<n>` | — |

Unknown verb → `ERR unknown`. Malformed/overflowing argument → `ERR badarg`. One reply line per event; the host waits for `READY` before capturing a frame.

---

### Task 1: Firmware + host-test scaffold

**Files:**
- Create: `firmware/CMakeLists.txt`
- Create: `firmware/sdkconfig.defaults`
- Create: `firmware/main/CMakeLists.txt`
- Create: `firmware/main/app_main.c`
- Create: `firmware/main/pins.h`
- Create: `firmware/host_test/CMakeLists.txt`
- Create: `firmware/host_test/minunit.h`
- Create: `firmware/host_test/test_scaffold.c`
- Create: `firmware/.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a buildable ESP-IDF project skeleton and a CTest host-test harness (`minunit.h`) that later tasks extend.

- [ ] **Step 1: Write the failing host test**

```c
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
```

- [ ] **Step 2: Create the MinUnit header**

```c
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
```

- [ ] **Step 3: Create the host-test CMake harness**

```cmake
# firmware/host_test/CMakeLists.txt
cmake_minimum_required(VERSION 3.16)
project(gemscanner_fw_host_tests C)
enable_testing()
set(CMAKE_C_STANDARD 11)

set(COMPONENTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../components)

# Helper: add a host test that compiles a pure component + its test file.
function(add_pure_test test_name component)
  add_executable(${test_name} ${ARGN})
  target_include_directories(${test_name} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${COMPONENTS_DIR}/${component}/include)
  add_test(NAME ${test_name} COMMAND ${test_name})
endfunction()

# Scaffold test needs no component.
add_executable(test_scaffold test_scaffold.c)
target_include_directories(test_scaffold PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
add_test(NAME test_scaffold COMMAND test_scaffold)
```

- [ ] **Step 4: Build and run the host test — verify it passes**

```bash
cd firmware/host_test
cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure
```
Expected: `test_scaffold` passes; `1 test, 0 failures` from ctest.

- [ ] **Step 5: Create the ESP-IDF skeleton**

```cmake
# firmware/CMakeLists.txt
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(gemscanner_fw)
```

```
# firmware/sdkconfig.defaults
CONFIG_IDF_TARGET="esp32c6"
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
CONFIG_FREERTOS_HZ=1000
```

```cmake
# firmware/main/CMakeLists.txt
idf_component_register(SRCS "app_main.c"
                       INCLUDE_DIRS ".")
```

```c
// firmware/main/pins.h
#pragma once
#include "driver/gpio.h"

#define PIN_STEP        GPIO_NUM_1
#define PIN_DIR         GPIO_NUM_2
#define PIN_ENABLE      GPIO_NUM_3
#define PIN_RGB_LED     GPIO_NUM_8   // onboard WS2812

#define DIR_ACTIVE_LEVEL    1        // DIR level for positive microsteps
#define ENABLE_ACTIVE_LEVEL 1        // level that energises the ADB-5331A
#define STEP_PULSE_US       3        // STEP high time (>= driver min, verify datasheet)
```

```c
// firmware/main/app_main.c
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void) {
    printf("gemscanner-fw boot\n");
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

```
# firmware/.gitignore
build/
host_test/build/
sdkconfig
sdkconfig.old
managed_components/
dependencies.lock
```

- [ ] **Step 6: (Optional, requires hardware/IDF env) verify the ESP-IDF project configures**

```powershell
D:\ESP32\export.ps1
cd firmware ; idf.py set-target esp32c6 ; idf.py reconfigure
```
Expected: configuration succeeds. (Full `idf.py build` is exercised in Task 9. This step is not gating if the IDF env is unavailable in the current shell.)

- [ ] **Step 7: Commit**

```bash
git add firmware/
git commit -m "chore: scaffold ESP-IDF firmware project and host-test harness"
```

---

### Task 2: Command parser (pure C, host-tested)

**Files:**
- Create: `firmware/components/command_parser/include/command_parser.h`
- Create: `firmware/components/command_parser/command_parser.c`
- Create: `firmware/components/command_parser/CMakeLists.txt`
- Create: `firmware/host_test/test_command_parser.c`
- Modify: `firmware/host_test/CMakeLists.txt` (register the new test)

**Interfaces:**
- Consumes: nothing (C stdlib only).
- Produces:
  ```c
  typedef enum { CMD_STEP, CMD_MOVEDEG, CMD_SETV, CMD_SETACC, CMD_SETSETTLE,
                 CMD_SETRES, CMD_HOME, CMD_STATUS, CMD_UNKNOWN, CMD_BADARG } cmd_kind_t;
  typedef struct { cmd_kind_t kind; int has_arg; long i_arg; double d_arg; } command_t;
  command_t command_parse(const char *line);
  ```
  `command_parse` trims trailing `\r`/`\n`/spaces, matches the verb case-insensitively, and parses the argument (integer verbs use `i_arg`; `MOVEDEG` uses `d_arg`). A verb that requires an argument but is given none/garbage yields `CMD_BADARG`. An unrecognized verb yields `CMD_UNKNOWN`.

- [ ] **Step 1: Write the failing tests**

```c
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
```

- [ ] **Step 2: Register the test, build, and verify it fails**

Append to `firmware/host_test/CMakeLists.txt`:
```cmake
add_pure_test(test_command_parser command_parser
  ${COMPONENTS_DIR}/command_parser/command_parser.c
  test_command_parser.c)
```
Run:
```bash
cd firmware/host_test && cmake -S . -B build && cmake --build build 2>&1 | tail -20
```
Expected: build FAILS (no `command_parser.c` / `command_parser.h` yet).

- [ ] **Step 3: Write the header and implementation**

```c
// firmware/components/command_parser/include/command_parser.h
#pragma once

typedef enum { CMD_STEP, CMD_MOVEDEG, CMD_SETV, CMD_SETACC, CMD_SETSETTLE,
               CMD_SETRES, CMD_HOME, CMD_STATUS, CMD_UNKNOWN, CMD_BADARG } cmd_kind_t;

typedef struct { cmd_kind_t kind; int has_arg; long i_arg; double d_arg; } command_t;

command_t command_parse(const char *line);
```

```c
// firmware/components/command_parser/command_parser.c
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
    int has_space = (*arg != 0);
    if (has_space) *arg++ = 0;
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
```

```cmake
# firmware/components/command_parser/CMakeLists.txt
idf_component_register(SRCS "command_parser.c" INCLUDE_DIRS "include")
```

- [ ] **Step 4: Build and run — verify pass**

```bash
cd firmware/host_test && cmake --build build && ctest --test-dir build -R test_command_parser --output-on-failure
```
Expected: PASS (`6 tests, 0 failures`).

- [ ] **Step 5: Commit**

```bash
git add firmware/components/command_parser firmware/host_test/test_command_parser.c firmware/host_test/CMakeLists.txt
git commit -m "feat(fw): ASCII command parser with host tests"
```

---

### Task 3: Motion math (pure C, host-tested)

**Files:**
- Create: `firmware/components/motion_math/include/motion_math.h`
- Create: `firmware/components/motion_math/motion_math.c`
- Create: `firmware/components/motion_math/CMakeLists.txt`
- Create: `firmware/host_test/test_motion_math.c`
- Modify: `firmware/host_test/CMakeLists.txt`

**Interfaces:**
- Consumes: nothing (C stdlib `math.h`).
- Produces:
  ```c
  long  mm_degrees_to_microsteps(double deg, long steps_per_rev);  // rounds to nearest
  double mm_microsteps_to_degrees(long steps, long steps_per_rev);
  double mm_wrap_deg(double deg);                                  // -> [0, 360)
  ```

- [ ] **Step 1: Write the failing tests**

```c
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
```

- [ ] **Step 2: Register, build, verify fail**

Append to `firmware/host_test/CMakeLists.txt`:
```cmake
add_pure_test(test_motion_math motion_math
  ${COMPONENTS_DIR}/motion_math/motion_math.c
  test_motion_math.c)
```
Run `cmake -S . -B build && cmake --build build` → FAILS (module missing).

- [ ] **Step 3: Implement**

```c
// firmware/components/motion_math/include/motion_math.h
#pragma once
long   mm_degrees_to_microsteps(double deg, long steps_per_rev);
double mm_microsteps_to_degrees(long steps, long steps_per_rev);
double mm_wrap_deg(double deg);
```

```c
// firmware/components/motion_math/motion_math.c
#include "motion_math.h"
#include <math.h>

long mm_degrees_to_microsteps(double deg, long steps_per_rev) {
    double s = deg / 360.0 * (double)steps_per_rev;
    return (long)llround(s);
}
double mm_microsteps_to_degrees(long steps, long steps_per_rev) {
    if (steps_per_rev == 0) return 0.0;
    return (double)steps / (double)steps_per_rev * 360.0;
}
double mm_wrap_deg(double deg) {
    double w = fmod(deg, 360.0);
    if (w < 0) w += 360.0;
    return w;
}
```

```cmake
# firmware/components/motion_math/CMakeLists.txt
idf_component_register(SRCS "motion_math.c" INCLUDE_DIRS "include")
```

- [ ] **Step 4: Build and run — verify pass**

```bash
cd firmware/host_test && cmake --build build && ctest --test-dir build -R test_motion_math --output-on-failure
```
Expected: PASS (`3 tests, 0 failures`).

- [ ] **Step 5: Commit**

```bash
git add firmware/components/motion_math firmware/host_test/test_motion_math.c firmware/host_test/CMakeLists.txt
git commit -m "feat(fw): degrees/microsteps + angle-wrap math with host tests"
```

---

### Task 4: Trapezoidal ramp planner (pure C, host-tested)

**Files:**
- Create: `firmware/components/ramp/include/ramp.h`
- Create: `firmware/components/ramp/ramp.c`
- Create: `firmware/components/ramp/CMakeLists.txt`
- Create: `firmware/host_test/test_ramp.c`
- Modify: `firmware/host_test/CMakeLists.txt`

**Interfaces:**
- Consumes: nothing (`math.h`).
- Produces:
  ```c
  typedef struct { unsigned v_start; unsigned v_max; unsigned accel; } ramp_profile_t; // microsteps/s, /s, /s^2
  // Microsecond interval to wait before emitting step `i` (0-based) of a `total`-step move.
  // Trapezoidal: accelerate from v_start to v_max, cruise, symmetric decel back to v_start.
  unsigned ramp_interval_us(const ramp_profile_t *p, unsigned total, unsigned i);
  ```
  Velocity in step-space kinematics: `v(d) = sqrt(v_start^2 + 2*accel*d)` ramping up over the first `accel_steps = (v_max^2 - v_start^2)/(2*accel)` steps (clamped to `total/2` for triangular moves), mirrored on the way down; interval = `1e6 / v`, clamped so `v ∈ [v_start, v_max]`.

- [ ] **Step 1: Write the failing tests**

```c
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
```

- [ ] **Step 2: Register, build, verify fail**

Append to `firmware/host_test/CMakeLists.txt`:
```cmake
add_pure_test(test_ramp ramp
  ${COMPONENTS_DIR}/ramp/ramp.c
  test_ramp.c)
```
Run build → FAILS.

- [ ] **Step 3: Implement**

```c
// firmware/components/ramp/include/ramp.h
#pragma once
typedef struct { unsigned v_start; unsigned v_max; unsigned accel; } ramp_profile_t;
unsigned ramp_interval_us(const ramp_profile_t *p, unsigned total, unsigned i);
```

```c
// firmware/components/ramp/ramp.c
#include "ramp.h"
#include <math.h>

unsigned ramp_interval_us(const ramp_profile_t *p, unsigned total, unsigned i) {
    if (total == 0 || i >= total) return 0;
    double v_start = p->v_start > 0 ? (double)p->v_start : 1.0;
    double v_max   = p->v_max   > v_start ? (double)p->v_max : v_start;
    double accel   = p->accel   > 0 ? (double)p->accel : 1.0;

    // steps to ramp from v_start to v_max
    double accel_steps = (v_max*v_max - v_start*v_start) / (2.0 * accel);
    if (accel_steps > total / 2.0) accel_steps = total / 2.0;  // triangular

    double dist_from_end = (double)(total - 1 - i);
    double d = (double)i < accel_steps ? (double)i
             : (dist_from_end < accel_steps ? dist_from_end : accel_steps);
    double v = sqrt(v_start*v_start + 2.0*accel*d);
    if (v > v_max) v = v_max;
    if (v < v_start) v = v_start;
    return (unsigned)(1e6 / v + 0.5);
}
```

```cmake
# firmware/components/ramp/CMakeLists.txt
idf_component_register(SRCS "ramp.c" INCLUDE_DIRS "include")
```

- [ ] **Step 4: Build and run — verify pass**

```bash
cd firmware/host_test && cmake --build build && ctest --test-dir build -R test_ramp --output-on-failure
```
Expected: PASS (`5 tests, 0 failures`). Then run the whole host suite: `ctest --test-dir build --output-on-failure` → all green.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/ramp firmware/host_test/test_ramp.c firmware/host_test/CMakeLists.txt
git commit -m "feat(fw): trapezoidal ramp planner with host tests"
```

---

### Task 5: Stepper driver glue (ESP-IDF, bench-verified)

> Tasks 5–9 run on the ESP32-C6 and require the board, the 5 V buffer, the ADB-5331A, and the motor. They are verified on the bench, not by host unit tests. Activate the IDF env (`D:\ESP32\export.ps1`) before `idf.py`.

**Files:**
- Create: `firmware/main/stepper.h`
- Create: `firmware/main/stepper.c`
- Modify: `firmware/main/CMakeLists.txt` (add `stepper.c`, deps `ramp`, `driver`, `esp_timer`)

**Interfaces:**
- Consumes: `ramp.h` (`ramp_profile_t`, `ramp_interval_us`), `pins.h`.
- Produces:
  ```c
  void stepper_init(void);
  // Blocks the calling task until the move completes. dir handled from sign of `microsteps`.
  void stepper_move_blocking(long microsteps, const ramp_profile_t *profile);
  ```
  Implementation: a GPTimer drives one microstep per alarm. DIR/ENABLE are set before motion. For step `i`, the next alarm is scheduled `ramp_interval_us(profile, total, i)` ahead; in the alarm callback the STEP line is pulsed high for `STEP_PULSE_US` then low (`esp_rom_delay_us`), a step counter advances, and a task notification is sent when all steps are done. `stepper_move_blocking` waits on that notification.

- [ ] **Step 1: Implement**

```c
// firmware/main/stepper.h
#pragma once
#include "ramp.h"
void stepper_init(void);
void stepper_move_blocking(long microsteps, const ramp_profile_t *profile);
```

```c
// firmware/main/stepper.c
#include "stepper.h"
#include "pins.h"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static gptimer_handle_t s_timer;
static volatile unsigned s_total, s_index;
static const ramp_profile_t *s_profile;
static TaskHandle_t s_waiter;

// NOT IRAM_ATTR: default gptimer ISR runs from flash; callee helpers are flash-resident.
static bool on_alarm(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *arg) {
    (void)t; (void)e; (void)arg;
    gpio_set_level(PIN_STEP, 1);
    esp_rom_delay_us(STEP_PULSE_US);
    gpio_set_level(PIN_STEP, 0);
    s_index++;
    BaseType_t hp = pdFALSE;
    if (s_index >= s_total) {
        gptimer_stop(t);
        vTaskNotifyGiveFromISR(s_waiter, &hp);
    } else {
        gptimer_alarm_config_t a = { .reload_count = 0, .alarm_count =
            ramp_interval_us(s_profile, s_total, s_index), .flags.auto_reload_on_alarm = false };
        gptimer_set_alarm_action(t, &a);
    }
    return hp == pdTRUE;
}

void stepper_init(void) {
    gpio_config_t io = { .pin_bit_mask = (1ULL<<PIN_STEP)|(1ULL<<PIN_DIR)|(1ULL<<PIN_ENABLE),
                         .mode = GPIO_MODE_OUTPUT };
    gpio_config(&io);
    gpio_set_level(PIN_ENABLE, ENABLE_ACTIVE_LEVEL);
    gpio_set_level(PIN_STEP, 0);

    gptimer_config_t cfg = { .clk_src = GPTIMER_CLK_SRC_DEFAULT,
                             .direction = GPTIMER_COUNT_UP, .resolution_hz = 1000000 }; // 1 us tick
    gptimer_new_timer(&cfg, &s_timer);
    gptimer_event_callbacks_t cbs = { .on_alarm = on_alarm };
    gptimer_register_event_callbacks(s_timer, &cbs, NULL);
    gptimer_enable(s_timer);
}

void stepper_move_blocking(long microsteps, const ramp_profile_t *profile) {
    if (microsteps == 0) return;
    gpio_set_level(PIN_DIR, microsteps > 0 ? DIR_ACTIVE_LEVEL : !DIR_ACTIVE_LEVEL);
    esp_rom_delay_us(5);  // DIR setup time before first pulse
    s_total = (unsigned)(microsteps > 0 ? microsteps : -microsteps);
    s_index = 0;
    s_profile = profile;
    s_waiter = xTaskGetCurrentTaskHandle();

    gptimer_set_raw_count(s_timer, 0);
    gptimer_alarm_config_t a = { .reload_count = 0,
        .alarm_count = ramp_interval_us(profile, s_total, 0), .flags.auto_reload_on_alarm = false };
    gptimer_set_alarm_action(s_timer, &a);
    gptimer_start(s_timer);
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
}
```

Update `firmware/main/CMakeLists.txt`:
```cmake
idf_component_register(SRCS "app_main.c" "stepper.c"
                       INCLUDE_DIRS "."
                       REQUIRES ramp driver esp_timer)
```

- [ ] **Step 2: Bench verification (requires hardware)**

Temporarily call from `app_main` (revert after): `stepper_init();` then in a loop `stepper_move_blocking(+steps, &profile)` / `-steps` with `profile={200,4000,20000}` and `steps` = one full revolution per your `SETRES` value.
```powershell
D:\ESP32\export.ps1 ; cd firmware ; idf.py set-target esp32c6 ; idf.py build flash monitor
```
Expected on the bench: the stage rotates the commanded amount, smoothly (audible accel/decel), reverses on sign flip, and returns to the same physical position after equal +N/−N moves (no lost steps at the chosen `v_max`). If steps are lost, lower `v_max` or raise `accel`/`v_start`. Record the working profile.

- [ ] **Step 3: Commit**

```bash
git add firmware/main/stepper.c firmware/main/stepper.h firmware/main/CMakeLists.txt
git commit -m "feat(fw): GPTimer-driven STEP/DIR stepper with ramped motion"
```

---

### Task 6: USB-CDC line I/O (ESP-IDF, bench-verified)

**Files:**
- Create: `firmware/main/usb_cdc.h`
- Create: `firmware/main/usb_cdc.c`
- Modify: `firmware/main/CMakeLists.txt` (add `usb_cdc.c`, dep `driver`)

**Interfaces:**
- Consumes: `driver/usb_serial_jtag.h`.
- Produces:
  ```c
  void usb_cdc_init(void);
  // Blocking read of one line (without the terminator) into buf (cap bytes). Returns length, or -1.
  int  usb_cdc_read_line(char *buf, int cap);
  void usb_cdc_write_line(const char *s);   // appends "\n"
  ```

- [ ] **Step 1: Implement**

```c
// firmware/main/usb_cdc.h
#pragma once
void usb_cdc_init(void);
int  usb_cdc_read_line(char *buf, int cap);
void usb_cdc_write_line(const char *s);
```

```c
// firmware/main/usb_cdc.c
#include "usb_cdc.h"
#include "driver/usb_serial_jtag.h"
#include <string.h>

void usb_cdc_init(void) {
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    usb_serial_jtag_driver_install(&cfg);
}

int usb_cdc_read_line(char *buf, int cap) {
    int n = 0;
    for (;;) {
        uint8_t ch;
        int r = usb_serial_jtag_read_bytes(&ch, 1, portMAX_DELAY);
        if (r <= 0) continue;
        if (ch == '\n') { buf[n] = 0; return n; }
        if (ch == '\r') continue;
        if (n < cap - 1) buf[n++] = (char)ch;
    }
}

void usb_cdc_write_line(const char *s) {
    usb_serial_jtag_write_bytes((const uint8_t *)s, strlen(s), portMAX_DELAY);
    usb_serial_jtag_write_bytes((const uint8_t *)"\n", 1, portMAX_DELAY);
}
```

Update `firmware/main/CMakeLists.txt` REQUIRES to include `driver` (already present from Task 5) and add `usb_cdc.c` to SRCS.

- [ ] **Step 2: Bench verification (requires hardware)**

Temporarily wire `app_main` to echo: `usb_cdc_init();` then loop `usb_cdc_read_line` → `usb_cdc_write_line`. Flash, open the COM port at any baud (USB Serial/JTAG ignores baud), type `hello` → expect `hello` echoed back, one line per Enter. Confirm `\r\n` and `\n` line endings both work.

- [ ] **Step 3: Commit**

```bash
git add firmware/main/usb_cdc.c firmware/main/usb_cdc.h firmware/main/CMakeLists.txt
git commit -m "feat(fw): USB Serial/JTAG line read/write"
```

---

### Task 7: Controller / command dispatch (ESP-IDF, bench-verified)

**Files:**
- Create: `firmware/main/controller.h`
- Create: `firmware/main/controller.c`
- Modify: `firmware/main/CMakeLists.txt` (add `controller.c`, deps `command_parser motion_math ramp`)

**Interfaces:**
- Consumes: `command_parser.h`, `motion_math.h`, `ramp.h`, `stepper.h`, `usb_cdc.h`.
- Produces:
  ```c
  void controller_run(void);   // never returns: read line -> dispatch -> reply
  ```
  Holds mutable state: `long pos_steps` (logical position), `long steps_per_rev` (0 = unset), `ramp_profile_t profile` (defaults `{200, 4000, 20000}`), `unsigned settle_ms` (default 150), `enum {IDLE, MOVING, SETTLING} state`. Dispatch follows the §Protocol table exactly: on a move command it replies `OK`, performs `stepper_move_blocking`, updates `pos_steps`, delays `settle_ms`, then replies `READY`. `STATUS` reports `pos_steps`, `mm_microsteps_to_degrees(pos_steps, steps_per_rev)` wrapped via `mm_wrap_deg`, and current settings. `SETRES 0` or any arg ≤ 0 for `SETV/SETACC/SETRES` → `ERR badarg`.

- [ ] **Step 1: Implement**

```c
// firmware/main/controller.h
#pragma once
void controller_run(void);
```

```c
// firmware/main/controller.c
#include "controller.h"
#include "command_parser.h"
#include "motion_math.h"
#include "ramp.h"
#include "stepper.h"
#include "usb_cdc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>

static long pos_steps = 0;
static long steps_per_rev = 0;
static ramp_profile_t profile = { .v_start = 200, .v_max = 4000, .accel = 20000 };
static unsigned settle_ms = 150;

static void do_move(long microsteps) {
    usb_cdc_write_line("OK");
    stepper_move_blocking(microsteps, &profile);
    pos_steps += microsteps;
    vTaskDelay(pdMS_TO_TICKS(settle_ms));
    usb_cdc_write_line("READY");
}

void controller_run(void) {
    char line[80], out[160];
    for (;;) {
        if (usb_cdc_read_line(line, sizeof(line)) < 0) continue;
        command_t c = command_parse(line);
        switch (c.kind) {
        case CMD_STEP: do_move(c.i_arg); break;
        case CMD_MOVEDEG:
            if (steps_per_rev <= 0) { usb_cdc_write_line("ERR nores"); break; }
            do_move(mm_degrees_to_microsteps(c.d_arg, steps_per_rev)); break;
        case CMD_SETV:  if (c.i_arg > 0) { profile.v_max = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETACC:if (c.i_arg > 0) { profile.accel = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETSETTLE: if (c.i_arg >= 0) { settle_ms = (unsigned)c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_SETRES: if (c.i_arg > 0) { steps_per_rev = c.i_arg; usb_cdc_write_line("OK"); } else usb_cdc_write_line("ERR badarg"); break;
        case CMD_HOME: pos_steps = 0; usb_cdc_write_line("OK"); usb_cdc_write_line("READY"); break;
        case CMD_STATUS: {
            double deg = mm_wrap_deg(mm_microsteps_to_degrees(pos_steps, steps_per_rev));
            snprintf(out, sizeof(out),
                "STATUS angle=%.3f steps=%ld state=idle v=%u a=%u settle=%u res=%ld",
                deg, pos_steps, profile.v_max, profile.accel, settle_ms, steps_per_rev);
            usb_cdc_write_line(out); break;
        }
        case CMD_BADARG: usb_cdc_write_line("ERR badarg"); break;
        default: usb_cdc_write_line("ERR unknown"); break;
        }
    }
}
```

Update `firmware/main/CMakeLists.txt` SRCS to add `controller.c`, REQUIRES to add `command_parser motion_math`.

- [ ] **Step 2: Bench verification (requires hardware)**

Set `app_main` to `stepper_init(); usb_cdc_init(); controller_run();` (this is the real wiring finalized in Task 9). Flash, open the COM port, then exercise the protocol:
```
SETRES 50000      -> OK
SETV 4000         -> OK
STATUS            -> STATUS angle=0.000 steps=0 state=idle v=4000 a=20000 settle=150 res=50000
STEP 12500        -> OK ... (stage turns 90°) ... READY
MOVEDEG 90        -> OK ... (turns another 90°) ... READY
STATUS            -> angle≈180.000 steps=25000
HOME              -> OK / READY ; STATUS -> angle=0.000 steps=0
WIGGLE            -> ERR unknown
MOVEDEG 10  (after a fresh boot, before SETRES) -> ERR nores
```
Confirm `OK` arrives immediately and `READY` only after motion+settle. Time the `READY` lag ≈ move time + `settle_ms`.

- [ ] **Step 3: Commit**

```bash
git add firmware/main/controller.c firmware/main/controller.h firmware/main/CMakeLists.txt
git commit -m "feat(fw): command dispatch controller with OK/READY/STATUS protocol"
```

---

### Task 8: Status display — RGB LED + LCD (ESP-IDF, bench-verified)

**Files:**
- Create: `firmware/main/status_display.h`
- Create: `firmware/main/status_display.c`
- Create: `firmware/main/idf_component.yml` (managed deps)
- Modify: `firmware/main/CMakeLists.txt`
- Modify: `firmware/main/controller.c` (emit status changes)

**Interfaces:**
- Consumes: `espressif/led_strip`, `lvgl/lvgl`, `espressif/esp_lvgl_port`, `esp_lcd` (ST7789 over SPI, pins from the Waveshare board: MOSI=6, SCLK=7, CS=14, DC=15, RST=21, BL=22; 172×320).
- Produces:
  ```c
  typedef enum { ST_DISCONNECTED, ST_IDLE, ST_MOVING, ST_SETTLING } disp_state_t;
  void status_display_init(void);
  void status_display_set(disp_state_t state, double angle_deg, long steps);
  ```
  RGB LED encodes state by color (disconnected=dim blue, idle=green, moving=amber, settling=cyan). The LCD shows three LVGL labels: state name, `angle=…°`, `steps=…`. `controller.c` calls `status_display_set(...)` on each state transition.

- [ ] **Step 1: Declare managed components**

```yaml
# firmware/main/idf_component.yml
dependencies:
  espressif/led_strip: "^2"
  lvgl/lvgl: "~9.2.0"
  espressif/esp_lvgl_port: "^2"
```

- [ ] **Step 2: Implement the display module**

```c
// firmware/main/status_display.h
#pragma once
typedef enum { ST_DISCONNECTED, ST_IDLE, ST_MOVING, ST_SETTLING } disp_state_t;
void status_display_init(void);
void status_display_set(disp_state_t state, double angle_deg, long steps);
```

```c
// firmware/main/status_display.c
#include "status_display.h"
#include "pins.h"
#include "led_strip.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "driver/spi_master.h"
#include "esp_lvgl_port.h"
#include "lvgl.h"
#include <stdio.h>

static led_strip_handle_t s_led;
static lv_obj_t *s_l_state, *s_l_angle, *s_l_steps;

static void led_set(uint8_t r, uint8_t g, uint8_t b) {
    led_strip_set_pixel(s_led, 0, r, g, b);
    led_strip_refresh(s_led);
}

static void lcd_init(void) {
    spi_bus_config_t bus = { .mosi_io_num = 6, .sclk_io_num = 7, .miso_io_num = -1,
        .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 172*320*2 };
    spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO);
    esp_lcd_panel_io_handle_t io;
    esp_lcd_panel_io_spi_config_t io_cfg = { .dc_gpio_num = 15, .cs_gpio_num = 14,
        .pclk_hz = 40*1000*1000, .lcd_cmd_bits = 8, .lcd_param_bits = 8,
        .spi_mode = 0, .trans_queue_depth = 10 };
    esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &io_cfg, &io);
    esp_lcd_panel_handle_t panel;
    esp_lcd_panel_dev_config_t pcfg = { .reset_gpio_num = 21, .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB, .bits_per_pixel = 16 };
    esp_lcd_new_panel_st7789(io, &pcfg, &panel);
    esp_lcd_panel_reset(panel); esp_lcd_panel_init(panel);
    esp_lcd_panel_invert_color(panel, true);
    esp_lcd_panel_set_gap(panel, 34, 0);   // 172-wide ST7789 offset; tune on bench
    esp_lcd_panel_disp_on_off(panel, true);

    lvgl_port_cfg_t lp = ESP_LVGL_PORT_INIT_CONFIG();
    lvgl_port_init(&lp);
    lvgl_port_display_cfg_t dc = { .io_handle = io, .panel_handle = panel,
        .buffer_size = 172*40, .double_buffer = true, .hres = 172, .vres = 320,
        .rotation = { .swap_xy = false, .mirror_x = false, .mirror_y = false } };
    lv_display_t *disp = lvgl_port_add_disp(&dc);
    lv_obj_t *scr = lv_display_get_screen_active(disp);   // LVGL 9.x
    s_l_state = lv_label_create(scr); lv_obj_align(s_l_state, LV_ALIGN_TOP_LEFT, 6, 10);
    s_l_angle = lv_label_create(scr); lv_obj_align(s_l_angle, LV_ALIGN_TOP_LEFT, 6, 40);
    s_l_steps = lv_label_create(scr); lv_obj_align(s_l_steps, LV_ALIGN_TOP_LEFT, 6, 70);
}

void status_display_init(void) {
    led_strip_config_t sc = { .strip_gpio_num = PIN_RGB_LED, .max_leds = 1,
                              .led_model = LED_MODEL_WS2812 };
    led_strip_rmt_config_t rc = { .resolution_hz = 10*1000*1000 };
    led_strip_new_rmt_device(&sc, &rc, &s_led);
    lcd_init();
    status_display_set(ST_DISCONNECTED, 0.0, 0);
}

void status_display_set(disp_state_t state, double angle_deg, long steps) {
    switch (state) {
        case ST_DISCONNECTED: led_set(0, 0, 12); break;
        case ST_IDLE:         led_set(0, 30, 0); break;
        case ST_MOVING:       led_set(40, 20, 0); break;
        case ST_SETTLING:     led_set(0, 25, 25); break;
    }
    static const char *names[] = { "DISCONNECTED", "IDLE", "MOVING", "SETTLING" };
    char a[32], s[32];
    snprintf(a, sizeof(a), "angle=%.2f", angle_deg);
    snprintf(s, sizeof(s), "steps=%ld", steps);
    if (lvgl_port_lock(50)) {
        lv_label_set_text(s_l_state, names[state]);
        lv_label_set_text(s_l_angle, a);
        lv_label_set_text(s_l_steps, s);
        lvgl_port_unlock();
    }
}
```

Update `firmware/main/CMakeLists.txt`: add `status_display.c` to SRCS and `esp_lcd spi_flash` not needed; add `esp_lcd driver` to REQUIRES (managed components are pulled via `idf_component.yml`).

- [ ] **Step 3: Wire state transitions in `controller.c`**

In `do_move`, surround the phases:
```c
status_display_set(ST_MOVING, cur_angle(), pos_steps);
stepper_move_blocking(microsteps, &profile);
pos_steps += microsteps;
status_display_set(ST_SETTLING, cur_angle(), pos_steps);
vTaskDelay(pdMS_TO_TICKS(settle_ms));
status_display_set(ST_IDLE, cur_angle(), pos_steps);
```
where `cur_angle()` returns `mm_wrap_deg(mm_microsteps_to_degrees(pos_steps, steps_per_rev))`. Include `status_display.h`.

- [ ] **Step 4: Bench verification (requires hardware)**

```powershell
D:\ESP32\export.ps1 ; cd firmware ; idf.py build flash monitor
```
On boot the LED is dim blue and the LCD shows `DISCONNECTED / angle=0.00 / steps=0`. After a `STEP`/`MOVEDEG`, the LED turns amber during motion, cyan while settling, green when idle, and the LCD angle/steps update. (`idf.py build` here also downloads the managed components — first build is slower.)

- [ ] **Step 5: Commit**

```bash
git add firmware/main/status_display.c firmware/main/status_display.h firmware/main/idf_component.yml firmware/main/CMakeLists.txt firmware/main/controller.c
git commit -m "feat(fw): RGB LED + ST7789/LVGL status display"
```

---

### Task 9: Top-level wiring, full build, README (bench-verified)

**Files:**
- Modify: `firmware/main/app_main.c`
- Create: `firmware/README.md`

**Interfaces:**
- Consumes: `stepper.h`, `usb_cdc.h`, `controller.h`, `status_display.h`.
- Produces: the final `app_main` that initializes all subsystems and enters `controller_run()`; documentation of the protocol, wiring (incl. the 5 V buffer and pin map), and build/flash/test commands.

- [ ] **Step 1: Finalize `app_main`**

```c
// firmware/main/app_main.c
#include "stepper.h"
#include "usb_cdc.h"
#include "status_display.h"
#include "controller.h"

void app_main(void) {
    status_display_init();
    stepper_init();
    usb_cdc_init();
    controller_run();   // never returns
}
```

- [ ] **Step 2: Write `firmware/README.md`**

Document: (a) the §Protocol table; (b) the wiring — ESP32-C6 `STEP=GPIO1, DIR=GPIO2, ENABLE=GPIO3` → **3.3 V→5 V buffer/level-shifter** → ADB-5331A 1-pulse inputs (PULSE/DIR/AWO), with a note to verify the driver's input current-limit resistor and the STEP min pulse width against the ADB-5331A datasheet, and to set the driver to 1-pulse mode; (c) `steps-per-360° = motor step angle × driver microstep × stage gear ratio`, set at runtime via `SETRES`; (d) build/flash: `D:\ESP32\export.ps1` then `idf.py set-target esp32c6 && idf.py build flash monitor`; (e) host tests: `cd host_test && cmake -S . -B build && cmake --build build && ctest --test-dir build`.

- [ ] **Step 3: Full firmware build (requires IDF env)**

```powershell
D:\ESP32\export.ps1 ; cd firmware ; idf.py set-target esp32c6 ; idf.py build
```
Expected: build succeeds, producing `build/gemscanner_fw.bin`. Flash and run the full Task 7 protocol script end-to-end, confirming LED/LCD reflect state.

- [ ] **Step 4: Re-run the full host suite**

```bash
cd firmware/host_test && cmake --build build && ctest --test-dir build --output-on-failure
```
Expected: all host tests pass (`test_scaffold`, `test_command_parser`, `test_motion_math`, `test_ramp`).

- [ ] **Step 5: Commit**

```bash
git add firmware/main/app_main.c firmware/README.md
git commit -m "feat(fw): wire app_main and document protocol, wiring, build"
```

---

## Self-Review

**Spec coverage (design spec §6 ESP-IDF firmware):**
- USB-CDC over USB Serial/JTAG → Task 6.
- Command protocol (`STEP/MOVEDEG/SETV/SETACC/SETSETTLE/HOME/STATUS`, plus `SETRES` for runtime resolution) with `OK`/`READY`/`ERR` → Task 2 (parse) + Task 7 (dispatch). The spec's `SETSETTLE` and settle-then-`READY` behavior is in Task 7.
- Ramped STEP generation to avoid lost steps + settle delay then `READY` → Task 4 (ramp math) + Task 5 (GPTimer glue) + Task 7 (settle).
- STEP/DIR/ENABLE to ADB-5331A in 1-pulse mode with 5 V level shifting → Task 5 + Task 9 README wiring; pins in `pins.h` (Task 1).
- steps-per-360° calibrated/never hardcoded → `SETRES` (Tasks 2,7); `MOVEDEG` blocked until set.
- LCD + RGB LED status (connection/angle/progress) → Task 8.
- HOME without sensor (deferred) → Task 7 (zeroes logical angle).

**Placeholder scan:** No TBD/TODO. Pure-logic tasks (2–4) carry complete code + assertive host tests. Hardware tasks (5–9) carry complete implementation code plus concrete bench-verification procedures (exact serial I/O and observations) since they cannot be host-unit-tested — this is called out in the plan header and Global Constraints.

**Type/interface consistency:** `ramp_profile_t {v_start,v_max,accel}` and `ramp_interval_us(p,total,i)` are defined in Task 4 and consumed unchanged in Tasks 5/7. `command_t`/`cmd_kind_t` from Task 2 are consumed in Task 7's switch with matching enumerators. `mm_degrees_to_microsteps`/`mm_microsteps_to_degrees`/`mm_wrap_deg` (Task 3) are used in Task 7 exactly as declared. `stepper_move_blocking(microsteps, profile)`, `usb_cdc_read_line/write_line`, and `status_display_set(state, angle, steps)` signatures match across producer and consumer tasks. The §Protocol table is the single source of truth shared by parser and controller.

**Testability boundary:** Host-automated coverage stops at the pure components (parser, units, ramp). Everything touching RMT/GPTimer/USB/LCD is bench-verified — an inherent property of firmware, made explicit so a reviewer doesn't expect host tests for Tasks 5–9.

---

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Note: Tasks 5–9 require the physical board/driver/motor on the bench, so their verification steps need you (or a hardware-connected session) in the loop; Tasks 1–4 are fully host-automated and can be driven start-to-finish.
2. **Inline Execution** — implement tasks here with checkpoints.

Which approach? (And do you want this on a `plan-b-firmware` branch off `main`?)
