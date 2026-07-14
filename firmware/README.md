# GemScanner Firmware (ESP32-C6)

Motion-control firmware for the gemstone outline scanner. Runs on a **Waveshare
ESP32-C6-LCD-1.47** and drives the SURUGA SEIKI KRW06360 rotary stage (Oriental
Motor 5-phase stepper via an **ADB-5331A** driver) under a line-based USB-CDC
command protocol, so the host PC can run step-and-settle scans.

Built with **ESP-IDF 5.4**.

## Architecture

Pure logic is isolated from hardware so it can be unit-tested on a PC:

| Path | Responsibility | Tested |
|------|----------------|--------|
| `components/command_parser` | ASCII line → `command_t` | host (gcc/ctest) |
| `components/motion_math` | degrees↔microsteps, angle wrap | host |
| `components/ramp` | trapezoidal step-interval planner | host |
| `components/fmt_num` | integer → comma-grouped string (`35,000`) | host |
| `main/stepper.c` | GPTimer STEP/DIR pulse generation w/ ramp | bench |
| `main/usb_cdc.c` | USB Serial/JTAG line read/write | bench |
| `main/controller.c` | command dispatch + state machine | bench |
| `main/status_display.c` | RGB LED + ST7789 LCD (LVGL) status | bench |
| `main/app_main.c` | init order + run loop | bench |

These `components/*` modules contain **no ESP-IDF headers** and are compiled
both into the firmware and into the host test harness (`host_test/`).

## Command protocol

Line-based ASCII, terminated by `\n`, `\r`, or `\r\n`. Replies are `\n`-terminated.
A move command replies `OK` immediately, then `READY` after the move completes and
the settle delay elapses.

| Command | Meaning | Immediate | Deferred |
|---------|---------|-----------|----------|
| `STEP <n>` | move `n` microsteps, signed (+ = DIR active) | `OK` | `READY` |
| `MOVEDEG <x>` | move `x` degrees (float) | `OK` / `ERR nores` | `READY` |
| `SETV <v>` | max speed, microsteps/s (>0) | `OK` / `ERR badarg` | — |
| `SETACC <a>` | acceleration, microsteps/s² (>0) | `OK` / `ERR badarg` | — |
| `SETSETTLE <ms>` | settle delay, ms (≥0) | `OK` / `ERR badarg` | — |
| `SETRES <n>` | microsteps per 360° (>0) | `OK` / `ERR badarg` | — |
| `HOME` | zero the logical angle (no motion) | `OK` | `READY` |
| `STATUS` | query | `STATUS angle=<deg> steps=<n> state=idle v=<> a=<> settle=<ms> res=<n>` | — |

Unknown verb → `ERR unknown`. Bad/missing argument → `ERR badarg`.

**`steps-per-360°` is never hardcoded.** It is `motor step angle × driver microstep ×
stage gear ratio` and must be sent at runtime with `SETRES` (the PC calibrates it).
Until `SETRES` is sent, `MOVEDEG` returns `ERR nores` and the reported/displayed
`angle` stays `0.00` (steps still track).

Defaults at boot: `v=4000`, `a=20000`, `settle=150`, `res=0`, `pos=0`.

## Wiring

### Stepper driver (1-pulse mode)
The ADB-5331A must be set to **1-pulse mode** (PULSE + DIRECTION). Its inputs are
opto-isolated and expect ~5 V, so drive them through a **3.3 V → 5 V buffer /
level-shifter** — do not wire the ESP32 GPIOs straight into the driver.

| ESP32-C6 | Signal | → buffer → ADB-5331A |
|----------|--------|----------------------|
| GPIO1 | STEP (pulse) | PULSE+ |
| GPIO2 | DIR | DIR+ |
| GPIO3 | ENABLE | AWO/ENABLE+ |
| GND | common | input commons |

Active levels and the STEP pulse width are in `main/pins.h` (`DIR_ACTIVE_LEVEL`,
`ENABLE_ACTIVE_LEVEL`, `STEP_PULSE_US`). Verify the driver's input current-limit
resistor and minimum pulse width against the ADB-5331A datasheet. (HOME has no
sensor yet — it only zeroes the logical angle.)

### On-board peripherals (no external wiring)

Both indicators share one **per-state palette** so they always agree. The state
is one of four values (`disp_state_t`); the LCD shows a friendlier word for each:

| State (`disp_state_t`) | LCD word | Accent colour | Meaning |
|------------------------|----------|---------------|---------|
| `ST_DISCONNECTED` | **OFFLINE** | muted blue `#5A6B8C` | no host link |
| `ST_IDLE` | **READY** | green `#22C55E` | waiting for a command |
| `ST_MOVING` | **ROTATING** | amber `#F5A623` | stage in motion |
| `ST_SETTLING` | **SETTLING** | cyan `#22D3EE` | holding to stabilise |

(The USB `STATUS` reply is separate and still reports `state=idle`; the words
above are display-only.)

- **RGB LED** (WS2812, GPIO8): lit in the accent colour of the current state
  (blue / green / amber / cyan above), dimmed for comfortable brightness. *Note:*
  this board's LED takes **RGB** order while `led_strip`'s WS2812 model emits GRB,
  so `led_set()` swaps R↔G.
- **LCD** (ST7789, 172×320, SPI: MOSI=6 SCLK=7 CS=14 DC=15 RST=21, backlight=22):
  a minimalist **dark-theme** status screen (`status_display.c`) — a full-width
  accent bar and dot at the top, the large colour-coded **state word** (hero), a
  hairline divider, then `angle` (`142.50°`) and comma-grouped `steps` (`35,000`)
  as value + caption pairs, centred on the near-black canvas. Uses the Montserrat
  20/28 fonts (enabled in `sdkconfig.defaults`; 14 is on by default). Three
  settings were needed for this panel: `swap_bytes = true` (RGB565 byte order —
  without it text shows a colour fringe), `esp_lcd_panel_set_gap(panel, 34, 0)`
  (the 172-wide panel's RAM offset), and the backlight on **GPIO22 via LEDC PWM**
  at `LCD_BL_DUTY_PCT` (default 50%).

## Build, flash, monitor

Activate ESP-IDF 5.4 first (this install lives at `D:\ESP32`):

```powershell
& 'D:\ESP32\idf\v5.4\esp-idf\export.ps1'
cd 'D:\CodingProject\GemScanner\firmware'
idf.py set-target esp32c6     # once
idf.py build
idf.py -p COMx flash monitor  # COMx = the board's port; Ctrl+] exits monitor
```

The first build downloads the managed components (`lvgl 9.3`, `esp_lvgl_port 2.8`,
`led_strip 2.5`) — it needs network and is slower.

### Talking to it
In `idf.py monitor` there is **no local echo** — you won't see what you type, only
the board's replies. Press Enter (sends CR; the firmware accepts CR/LF/CRLF). Try:

```
SETRES 50000
STATUS
STEP 12500      → OK … READY  (stage turns ~90° if res≈50000)
MOVEDEG 45      → OK … READY
```

If replies are garbled by interleaved log bytes, set the console off USB:
`idf.py menuconfig → Component config → ESP System Settings → Channel for console
output → None` (or UART0), then rebuild — the protocol then owns the USB link.

## Host unit tests (no hardware)

```bash
cd firmware/host_test
cmake -S . -B build -G Ninja
cmake --build build
ctest --test-dir build --output-on-failure
```

Covers `command_parser`, `motion_math`, `ramp`, and `fmt_num`.
