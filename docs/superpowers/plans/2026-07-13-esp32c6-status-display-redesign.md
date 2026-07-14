# ESP32-C6 Status Display Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ESP32-C6 LCD's three plain top-left text labels with a minimalist dark-theme screen built around a large, color-coded state word, and re-tune the onboard RGB LED to the same palette.

**Architecture:** All rendering lives in `firmware/main/status_display.c` (LVGL 9.x via `esp_lvgl_port`). The `status_display_set(state, angle, steps)` signature and its `controller.c` call sites are unchanged — only the LVGL object graph, styling, per-state palette, and LED hues change. A small pure `fmt_num` component provides comma-grouped integer formatting so the steps value reads as `35,000`; it is host-tested because it has separable logic.

**Tech Stack:** ESP-IDF (target esp32c6), LVGL 9.x, `esp_lvgl_port`, `led_strip` (WS2812), ST7789 over SPI. Host tests use the existing `firmware/host_test` minunit harness.

## Global Constraints

- Target: `esp32c6` (`CONFIG_IDF_TARGET="esp32c6"`).
- Display is ST7789 **172 wide × 320 tall**, portrait; do not change `lcd_init()` hardware setup (SPI bus, panel config, gap, backlight, byte-swap).
- Public API is frozen: `status_display_set(disp_state_t state, double angle_deg, long steps)` and `status_display_init(void)` keep their exact signatures; `disp_state_t` enum values stay `ST_DISCONNECTED, ST_IDLE, ST_MOVING, ST_SETTLING`. No changes to `controller.c` or `status_display.h`.
- No new data surfaced on screen (no speed/accel/settle/res).
- All LVGL widget mutation happens under `lvgl_port_lock(50)` / `lvgl_port_unlock()`; on lock timeout, `ESP_LOGW` and skip the frame. The LED update stays outside the lock.
- State word → color mapping (accent hex / displayed word / LED r,g,b intent):
  - `ST_DISCONNECTED` → "OFFLINE" → `#5A6B8C` → LED (10,14,24)
  - `ST_IDLE`         → "READY"   → `#22C55E` → LED (0,34,12)
  - `ST_MOVING`       → "ROTATING"→ `#F5A623` → LED (40,22,0)
  - `ST_SETTLING`     → "SETTLING"→ `#22D3EE` → LED (0,28,28)
- Background `#0B0C0E`; value text near-white `#E8EAED`; captions/divider grey `#8A9099` / `#2A2D31`.

---

## File Structure

- Create: `firmware/components/fmt_num/include/fmt_num.h` — declares `fmt_thousands`.
- Create: `firmware/components/fmt_num/fmt_num.c` — comma-grouping formatter.
- Create: `firmware/components/fmt_num/CMakeLists.txt` — IDF component registration.
- Create: `firmware/host_test/test_fmt_num.c` — minunit tests for the formatter.
- Modify: `firmware/host_test/CMakeLists.txt` — register the new host test.
- Modify: `firmware/main/CMakeLists.txt` — add `fmt_num` to `REQUIRES`.
- Modify: `firmware/sdkconfig.defaults` — enable Montserrat 20 and 28.
- Modify: `firmware/main/status_display.c` — new layout, palette, LED hues, formatter use.

---

## Task 1: `fmt_num` comma-grouping formatter (pure, host-tested)

**Files:**
- Create: `firmware/components/fmt_num/include/fmt_num.h`
- Create: `firmware/components/fmt_num/fmt_num.c`
- Create: `firmware/components/fmt_num/CMakeLists.txt`
- Test: `firmware/host_test/test_fmt_num.c`
- Modify: `firmware/host_test/CMakeLists.txt:33` (append new `add_pure_test`)

**Interfaces:**
- Consumes: nothing (pure C, `<stddef.h>` only).
- Produces: `size_t fmt_thousands(long value, char *out, size_t n);` — writes `value` into `out` (max `n` bytes incl. NUL) with `,` thousands separators and a leading `-` for negatives; returns the full formatted length (excluding NUL) even if truncated. Consumed by Task 2.

- [ ] **Step 1: Write the failing test**

Create `firmware/host_test/test_fmt_num.c`:

```c
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
```

Create the header `firmware/components/fmt_num/include/fmt_num.h`:

```c
// firmware/components/fmt_num/include/fmt_num.h
#pragma once
#include <stddef.h>

// Format `value` with comma thousands-separators into `out` (<= n bytes incl NUL).
// Returns the full formatted length (excluding NUL), even when truncated.
size_t fmt_thousands(long value, char *out, size_t n);
```

Register the test — append to `firmware/host_test/CMakeLists.txt` after the `test_ramp` block (line 33):

```cmake
add_pure_test(test_fmt_num fmt_num
  ${COMPONENTS_DIR}/fmt_num/fmt_num.c
  test_fmt_num.c)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cmake -S firmware/host_test -B firmware/host_test/build
cmake --build firmware/host_test/build --target test_fmt_num
```
Expected: FAIL — link error `undefined reference to 'fmt_thousands'` (the `.c` is empty/absent).

- [ ] **Step 3: Write minimal implementation**

Create `firmware/components/fmt_num/fmt_num.c`:

```c
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

    char final[36];
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
```

Create `firmware/components/fmt_num/CMakeLists.txt`:

```cmake
idf_component_register(SRCS "fmt_num.c" INCLUDE_DIRS "include")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cmake --build firmware/host_test/build --target test_fmt_num
ctest --test-dir firmware/host_test/build -R test_fmt_num --output-on-failure
```
Expected: PASS — `test_fmt_num` passes all three test cases.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/fmt_num firmware/host_test/test_fmt_num.c firmware/host_test/CMakeLists.txt
git commit -m "feat(fw): add fmt_num comma-grouping formatter with host tests"
```

---

## Task 2: Redesign the status screen (layout, palette, fonts, LED)

**Files:**
- Modify: `firmware/sdkconfig.defaults` (enable Montserrat 20 + 28)
- Modify: `firmware/main/CMakeLists.txt:4` (add `fmt_num` to `REQUIRES`)
- Modify: `firmware/main/status_display.c` (LVGL object graph in `lcd_init()`, rewrite `status_display_set()`, retune `led_set` callers)

**Interfaces:**
- Consumes: `fmt_thousands(long, char*, size_t)` from Task 1.
- Produces: no new public symbols — `status_display_init()` / `status_display_set()` unchanged externally.

- [ ] **Step 1: Enable the larger fonts**

Append to `firmware/sdkconfig.defaults`:

```
CONFIG_LV_FONT_MONTSERRAT_20=y
CONFIG_LV_FONT_MONTSERRAT_28=y
```

Regenerate config so the new symbols take effect (existing `sdkconfig` values win over defaults, so force a regen):

```bash
rm -f firmware/sdkconfig
idf.py -C firmware reconfigure
```

Verify the symbols are now set:
```bash
grep -E "CONFIG_LV_FONT_MONTSERRAT_(20|28)=y" firmware/sdkconfig
```
Expected: both lines present.

- [ ] **Step 2: Wire the `fmt_num` component into the main app**

Edit `firmware/main/CMakeLists.txt` line 4 — add `fmt_num` to `REQUIRES`:

```cmake
# firmware/main/CMakeLists.txt
idf_component_register(SRCS "app_main.c" "stepper.c" "usb_cdc.c" "controller.c" "status_display.c"
                       INCLUDE_DIRS "."
                       REQUIRES command_parser motion_math ramp fmt_num driver esp_lcd)
```

- [ ] **Step 3: Rewrite the LVGL object graph and render logic**

Replace `firmware/main/status_display.c` with the following. The hardware half of `lcd_init()` (SPI bus, panel, backlight, `lvgl_port_init`, `lvgl_port_add_disp`) is byte-for-byte the same as today; only the screen/object-creation block and `status_display_set()` change, plus the new include, static objects, and palette tables.

```c
// firmware/main/status_display.c
#include "status_display.h"
#include "pins.h"
#include "fmt_num.h"
#include "led_strip.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_lvgl_port.h"
#include "lvgl.h"
#include "esp_log.h"
#include <stdio.h>

static const char *TAG = "status_display";

#define LCD_BL_PIN        22
#define LCD_BL_DUTY_PCT   50          // backlight brightness (0-100)
#define LCD_BL_RES        LEDC_TIMER_8_BIT   // 0..255

#define COL_BG        0x0B0C0E
#define COL_VALUE     0xE8EAED
#define COL_CAPTION   0x8A9099
#define COL_DIVIDER   0x2A2D31

// Per-state palette, indexed by disp_state_t (DISCONNECTED, IDLE, MOVING, SETTLING).
static const uint32_t k_accent[]   = { 0x5A6B8C, 0x22C55E, 0xF5A623, 0x22D3EE };
static const char    *k_word[]     = { "OFFLINE", "READY", "ROTATING", "SETTLING" };
static const uint8_t  k_led[][3]   = { {10,14,24}, {0,34,12}, {40,22,0}, {0,28,28} };

static led_strip_handle_t s_led;
static lv_obj_t *s_bar, *s_dot, *s_div;
static lv_obj_t *s_l_state, *s_l_angle, *s_l_steps;

static void led_set(uint8_t r, uint8_t g, uint8_t b) {
    // Onboard LED reads RGB order; led_strip's WS2812 model emits GRB, so swap R<->G here.
    led_strip_set_pixel(s_led, 0, g, r, b);
    led_strip_refresh(s_led);
}

// A plain filled block with no border/padding/scroll — used for the accent bar and dot.
static lv_obj_t *make_block(lv_obj_t *parent, int w, int h, int radius) {
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_border_width(o, 0, 0);
    lv_obj_set_style_pad_all(o, 0, 0);
    lv_obj_set_style_radius(o, radius, 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *make_label(lv_obj_t *parent, const lv_font_t *font, uint32_t color, int y) {
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    lv_obj_align(l, LV_ALIGN_TOP_MID, 0, y);
    return l;
}

static void lcd_init(void) {
    spi_bus_config_t bus = { .mosi_io_num = 6, .sclk_io_num = 7, .miso_io_num = -1,
        .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 172*320*2 };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
    esp_lcd_panel_io_handle_t io;
    esp_lcd_panel_io_spi_config_t io_cfg = { .dc_gpio_num = 15, .cs_gpio_num = 14,
        .pclk_hz = 40*1000*1000, .lcd_cmd_bits = 8, .lcd_param_bits = 8,
        .spi_mode = 0, .trans_queue_depth = 10 };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &io_cfg, &io));
    esp_lcd_panel_handle_t panel;
    esp_lcd_panel_dev_config_t pcfg = { .reset_gpio_num = 21, .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB, .bits_per_pixel = 16 };
    ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(io, &pcfg, &panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel));
    esp_lcd_panel_invert_color(panel, true);
    esp_lcd_panel_set_gap(panel, 34, 0);   // 172-wide ST7789 offset; tune on bench
    esp_lcd_panel_disp_on_off(panel, true);

    // LCD backlight on GPIO22 via LEDC PWM at LCD_BL_DUTY_PCT brightness
    ledc_timer_config_t bl_timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,   // ESP32-C6 has only low-speed mode
        .duty_resolution = LCD_BL_RES,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&bl_timer));
    ledc_channel_config_t bl_ch = {
        .gpio_num = LCD_BL_PIN,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = ((1 << 8) - 1) * LCD_BL_DUTY_PCT / 100,   // 8-bit: 128 = 50%
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&bl_ch));

    lvgl_port_cfg_t lp = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lp));
    lvgl_port_display_cfg_t dc = { .io_handle = io, .panel_handle = panel,
        .buffer_size = 172*40, .double_buffer = true, .hres = 172, .vres = 320,
        .rotation = { .swap_xy = false, .mirror_x = false, .mirror_y = false },
        .flags = { .swap_bytes = true } };   // RGB565 byte order for ST7789 (fixes colour fringe)
    lv_display_t *disp = lvgl_port_add_disp(&dc);
    lv_obj_t *scr = lv_display_get_screen_active(disp);   // LVGL 9.x

    // Dark canvas, no scrolling.
    lv_obj_set_style_bg_color(scr, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    // Accent top bar (full width) + accent dot; colors set per-state in _set().
    s_bar = make_block(scr, 172, 6, 0);
    lv_obj_align(s_bar, LV_ALIGN_TOP_MID, 0, 0);
    s_dot = make_block(scr, 12, 12, LV_RADIUS_CIRCLE);
    lv_obj_align(s_dot, LV_ALIGN_TOP_MID, 0, 90);

    // Hero state word (accent color set per-state).
    s_l_state = make_label(scr, &lv_font_montserrat_28, COL_VALUE, 110);

    // Hairline divider.
    s_div = make_block(scr, 140, 1, 0);
    lv_obj_set_style_bg_color(s_div, lv_color_hex(COL_DIVIDER), 0);
    lv_obj_align(s_div, LV_ALIGN_TOP_MID, 0, 160);

    // Angle value + caption.
    s_l_angle = make_label(scr, &lv_font_montserrat_28, COL_VALUE, 185);
    lv_obj_t *cap_a = make_label(scr, &lv_font_montserrat_14, COL_CAPTION, 222);
    lv_label_set_text(cap_a, "ANGLE");

    // Steps value + caption.
    s_l_steps = make_label(scr, &lv_font_montserrat_20, COL_VALUE, 250);
    lv_obj_t *cap_s = make_label(scr, &lv_font_montserrat_14, COL_CAPTION, 280);
    lv_label_set_text(cap_s, "STEPS");
}

void status_display_init(void) {
    led_strip_config_t sc = { .strip_gpio_num = PIN_RGB_LED, .max_leds = 1,
                              .led_model = LED_MODEL_WS2812 };
    led_strip_rmt_config_t rc = { .resolution_hz = 10*1000*1000 };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&sc, &rc, &s_led));
    lcd_init();
    status_display_set(ST_DISCONNECTED, 0.0, 0);
}

void status_display_set(disp_state_t state, double angle_deg, long steps) {
    lv_color_t accent = lv_color_hex(k_accent[state]);
    led_set(k_led[state][0], k_led[state][1], k_led[state][2]);

    char a[32], s[32];
    snprintf(a, sizeof(a), "%.2f\xC2\xB0", angle_deg);   // UTF-8 degree sign (U+00B0)
    fmt_thousands(steps, s, sizeof(s));

    if (lvgl_port_lock(50)) {
        lv_obj_set_style_bg_color(s_bar, accent, 0);
        lv_obj_set_style_bg_color(s_dot, accent, 0);
        lv_obj_set_style_text_color(s_l_state, accent, 0);
        lv_label_set_text(s_l_state, k_word[state]);
        lv_label_set_text(s_l_angle, a);
        lv_label_set_text(s_l_steps, s);
        lvgl_port_unlock();
    } else {
        ESP_LOGW(TAG, "lvgl lock timeout");
    }
}
```

- [ ] **Step 4: Build gate (fonts compile in, flash fits)**

Run:
```bash
idf.py -C firmware build
```
Expected: build succeeds. If the linker errors with `undefined reference to lv_font_montserrat_20`/`_28`, the font regen in Step 1 did not apply — repeat the `rm -f firmware/sdkconfig && idf.py -C firmware reconfigure` and rebuild.

- [ ] **Step 5: Commit**

```bash
git add firmware/sdkconfig.defaults firmware/main/CMakeLists.txt firmware/main/status_display.c
git commit -m "feat(fw): redesign status LCD — minimalist dark theme, colored state word"
```

- [ ] **Step 6: On-bench visual sign-off (mandatory — cannot be automated)**

Flash and observe (per the spec's mandatory visual gate):
```bash
idf.py -C firmware flash monitor
```
Confirm, cycling states by issuing motion commands over USB (e.g. a `MOVEDEG`/`STEP` to trigger ROTATING → SETTLING → READY, plus the OFFLINE boot state):
1. Each state shows the correct accent color on the top bar, dot, and hero word.
2. The widest words ("ROTATING", "SETTLING") are not clipped at 172px, and the whole stack fits within 320px (no vertical clipping).
3. The `°` glyph renders in the angle line. **If it shows as a missing-glyph box**, change the `snprintf` format in `status_display_set()` from `"%.2f\xC2\xB0"` to `"%.2f deg"` and re-flash (fallback documented in the spec).
4. Steps read comma-grouped (e.g. `35,000`) and are legible.
5. The onboard LED hue matches the on-screen accent for each state.

Report the result; do not mark this plan complete until a human confirms the visual gate.

---

## Self-Review

**Spec coverage:**
- Layout A (accent bar + dot + hero + divider + angle/steps stack, centered on 172×320) → Task 2 Step 3. ✓
- Dark palette + per-state accent colors → Global Constraints + Task 2 tables. ✓
- Wording OFFLINE/READY/ROTATING/SETTLING → `k_word[]`, Task 2. ✓
- LED re-tuned to matching hues → `k_led[]` + `led_set` in `status_display_set()`. ✓
- Fonts Montserrat 20 + 28 enabled → Task 2 Step 1. ✓
- No API change; `disp_state_t`, `status_display_set` signature, controller untouched → Global Constraints; only `status_display.c`/CMake/sdkconfig touched. ✓
- `°` glyph with documented fallback → Task 2 Step 3 code + Step 6 item 3. ✓
- Comma-grouped steps → Task 1 (tested) + used in Task 2. ✓
- Lock guard + LED outside lock → preserved in `status_display_set()`. ✓
- Build gate + mandatory bench visual sign-off → Task 2 Steps 4 and 6. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; no "handle edge cases" hand-waving (edge cases enumerated in Task 1 tests). ✓

**Type consistency:** `fmt_thousands(long, char*, size_t) -> size_t` is declared in the Task 1 header, tested in Task 1, and called identically in Task 2. State-indexed tables `k_accent`/`k_word`/`k_led` share the `disp_state_t` ordering used by `state` in `status_display_set()`. ✓
