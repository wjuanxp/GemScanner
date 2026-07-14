# ESP32-C6 Status Display Redesign

**Date:** 2026-07-13
**Component:** `firmware/main/status_display.c` (+ `.h`), `firmware/sdkconfig.defaults`
**Status:** Design approved, pending spec review

## Goal

Redesign the on-device LCD status screen so an observer can tell, at a glance and
across the room, what the scanner is currently doing. Replace the current three
plain top-left text labels with a minimalist dark-theme layout built around a
large, color-coded state word. Re-tune the onboard RGB LED to the same palette so
the two indicators agree.

## Hardware / platform constraints (fixed)

- Display: ST7789 LCD, **172 wide × 320 tall**, portrait. Color inversion on,
  RGB565 with byte swap (already configured in `lcd_init()`).
- Onboard WS2812 RGB LED (single pixel), driven via `led_set(r,g,b)` which already
  swaps R<->G for the board's GRB ordering.
- LVGL 9.x via `esp_lvgl_port`, configured through Kconfig/`sdkconfig` (no manual
  `lv_conf.h`). Default font is Montserrat 14; larger sizes are **not** compiled in.
- Rendering must hold the LVGL lock (`lvgl_port_lock`/`_unlock`), as today.

## Scope

**In scope**

- New screen layout and styling in `status_display.c`.
- New state wording and dark-theme color palette.
- Enable the larger Montserrat fonts needed for the hero/value text.
- Re-tune LED colors to match the new per-state palette.

**Out of scope (unchanged)**

- `status_display_set(disp_state_t, double angle_deg, long steps)` signature and
  its call sites in `controller.c` stay exactly as they are.
- No new data surfaced (speed/accel/settle/res are NOT added to the display).
- `disp_state_t` enum values stay the same (`ST_DISCONNECTED`, `ST_IDLE`,
  `ST_MOVING`, `ST_SETTLING`); only their *displayed words and colors* change.
- No change to when states are set or to connection detection.

## Layout (Approach A — accent top-bar + centered stack)

Background near-black `#0B0C0E`. One accent color per state; all other text is
white/grey. The content group is centered vertically in the 320px canvas.

```
┌────────────────┐   172 x 320
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│  ← 6px full-width accent bar (state color), pinned to top edge
│                │
│       ●        │  ← 12px round dot, accent color
│                │
│   ROTATING     │  ← Montserrat 28, accent color   (HERO)
│                │
│ ────────────── │  ← 1px hairline divider, #2A2D31
│                │
│    142.50°     │  ← Montserrat 28, near-white #E8EAED
│     ANGLE      │  ← Montserrat 14, grey #8A9099   (caption)
│                │
│     35,000     │  ← Montserrat 20, near-white #E8EAED
│     STEPS      │  ← Montserrat 14, grey #8A9099   (caption)
│                │
└────────────────┘
```

Alignment: everything horizontally centered on the 172px width. The dot → hero →
divider → angle block → steps block form one vertical stack centered around the
screen middle.

### Elements and LVGL objects

Persistent objects created once in `lcd_init()` (extending the current
`s_l_state/s_l_angle/s_l_steps` set), stored as file-static:

- `s_bar`   — top accent bar: `lv_obj_t` rectangle, 172×6, aligned `TOP_MID`.
- `s_dot`   — accent dot: small rounded `lv_obj_t`, 12×12, radius = full.
- `s_l_state` — hero label, Montserrat 28.
- `s_div`   — hairline: `lv_obj_t` 140×1, color `#2A2D31`.
- `s_l_angle` — angle value, Montserrat 28.
- `s_cap_angle` — static caption "ANGLE", Montserrat 14, grey (set once).
- `s_l_steps` — steps value, Montserrat 20.
- `s_cap_steps` — static caption "STEPS", Montserrat 14, grey (set once).

The screen background is set to `#0B0C0E` once at init.

## State palette and wording

`status_display_set()` maps state → {word, accent color}. LED gets the same accent
(scaled down to the LED's dim brightness range as today).

| Enum            | Displayed word | Accent (hex) | LED (r,g,b, dim) | Meaning              |
|-----------------|----------------|--------------|------------------|----------------------|
| ST_DISCONNECTED | OFFLINE        | #5A6B8C      | (10, 14, 24)     | no host link         |
| ST_IDLE         | READY          | #22C55E      | (0, 34, 12)      | waiting for command  |
| ST_MOVING       | ROTATING       | #F5A623      | (40, 22, 0)      | turntable in motion  |
| ST_SETTLING     | SETTLING       | #22D3EE      | (0, 28, 28)      | holding to stabilize |

LED values keep today's low brightness (the panel LED is bright); exact triplets
above are the intent and may be nudged on the bench. The mapping (blue/green/
amber/cyan) matches the current LED semantics, so behavior is consistent, just
recolored to align with the screen.

On each `status_display_set()` call: set the accent color on `s_bar`, `s_dot`, and
`s_l_state`; set hero text to the word; update angle and steps text; set LED.

### Text formatting

- Angle: `"%.2f°"` — matches current 2-decimal precision. The `°` glyph is ASCII
  0xB0; confirm it renders in the compiled Montserrat 28 set, else fall back to
  `" deg"` suffix or a drawn ring. (Verify on bench; documented as a build check.)
- Steps: thousands-grouped for readability (e.g. `35,000`). A small helper formats
  a `long` with comma separators into the existing stack buffer.

## Font configuration

Add to `firmware/sdkconfig.defaults`:

```
CONFIG_LV_FONT_MONTSERRAT_20=y
CONFIG_LV_FONT_MONTSERRAT_28=y
```

Montserrat 14 is already enabled and remains the default. Two extra glyph tables
add modest flash; acceptable. Reference the fonts in C as `&lv_font_montserrat_20`
and `&lv_font_montserrat_28`.

## Data flow

Unchanged from today:

```
controller.c do_move()/init  ──►  status_display_set(state, angle, steps)
                                        │
                                        ├─► LVGL: lock → set accent+text on
                                        │         bar/dot/hero/angle/steps → unlock
                                        └─► led_set(accent-dim)
```

`status_display_init()` still calls `status_display_set(ST_DISCONNECTED, 0.0, 0)`
at the end, so the redesigned OFFLINE screen is the boot state.

## Error handling

- Keep the existing `lvgl_port_lock(50)` guard; on timeout, log a warning and skip
  the frame (as today). The LED update stays outside the lock so status color
  still updates even if LVGL is briefly busy.
- All label/object creation is checked implicitly by LVGL; init runs once at boot.

## Testing

This is embedded UI; verification is primarily on-device visual plus a build gate.

1. **Build gate:** `idf.py build` for `esp32c6` succeeds with the new fonts and
   sdkconfig entries (confirms fonts compile in and flash fits).
2. **Bench visual check (mandatory sign-off):** flash and confirm each of the four
   states renders correctly — accent bar/dot/hero color, centered layout within
   172×320 (no clipping of the widest word "SETTLING"/"ROTATING"), angle & steps
   legibility, `°` glyph renders (or fallback applied), LED hue matches screen.
   Cycle states by issuing motion commands over USB and observing MOVING→SETTLING→
   READY, plus the OFFLINE boot state.
3. No host unit test — the drawing code is LVGL-call-only with no separable logic
   except the comma-grouping helper, which can be exercised by the existing
   `firmware/host_test` harness if a quick assert is cheap to add.

## Open verification items (resolve during implementation)

- Confirm `°` renders in Montserrat 28; else apply `" deg"` fallback.
- Confirm total layout height fits 320px with the chosen paddings (angle block +
  steps block + hero + bar); adjust vertical gaps if tight.
- Nudge LED brightness triplets on the bench for even perceived brightness across
  hues.
