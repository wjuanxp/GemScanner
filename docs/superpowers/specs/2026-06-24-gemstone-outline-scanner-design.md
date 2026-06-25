# Gemstone Outline Scanner — Design Spec

**Date:** 2026-06-24
**Status:** Approved for planning
**Author:** GemScanner project

## 1. Purpose

Build a desktop application that reconstructs a 3D model of a gemstone from its
**silhouette outlines** captured at many rotation angles (shape-from-silhouette /
visual hull). A gemstone mounted on a motorized rotary stage is backlit by a
collimated source and imaged through a telecentric lens, giving an **orthographic**
(parallel-ray) projection. The app drives a **step-and-settle** scan over 360°,
extracts the silhouette at each angle, and reconstructs a watertight 3D mesh for
export and inspection.

## 2. Hardware

| Item | Part | Role |
|------|------|------|
| Lens | TVS-5MDT0.12×250 (C-mount telecentric) | Orthographic, magnification-stable imaging |
| Camera (primary) | Baumer EXG50 (GigE Vision, 5 MP, ~3.45 µm pixels) | Silhouette capture via GenICam/neoAPI |
| Camera (future) | Generic USB camera on the same lens | Alternate backend, config-selectable |
| Backlight | Collimated / telecentric backlight | Crisp, magnification-stable silhouette edges |
| Rotary stage | SURUGA SEIKI KRW06360 | Gemstone rotation about a vertical axis |
| Motor | Oriental Motor C005C-9021 5P-1 (5-phase stepper) | Drives the stage |
| Driver | Oriental Motor **ADB-5331A** (5-phase) | STEP/DIR/ENABLE → motor windings |
| Controller | Waveshare ESP32-C6-LCD-1.47 | Motion control + status LCD, USB-CDC link to PC |
| Host | Windows 11 PC | Runs the Python application |

### Telecentric → orthographic
Because rays are parallel, each silhouette is a parallel projection: object size in
pixels is independent of distance from the lens, and a single image **row** maps to a
fixed object **height** `z`. This makes the reconstruction math simple and exact.

## 3. Scan workflow (step-and-settle)

1. PC commands the ESP32 to rotate one fixed angular increment.
2. ESP32 ramps the stepper (accel/decel), stops, waits a configurable **settle**
   delay for vibration to die out, then reports `READY`.
3. PC captures **one** frame from the camera.
4. Repeat for N angles over 360° (default **2°/frame → 180 views**, tunable).
5. The frame stack + metadata is written as a scan dataset.
6. Reconstruction runs (offline or immediately) and exports a mesh.

A **pre-scan FoV check** (see §4.4) runs before a full scan to confirm the gem stays
in frame at every angle.

## 4. Reconstruction

### 4.1 Approach A — per-slice strip intersection (implement now)
Exploits the orthographic projection:

- Each image row `v` corresponds to a fixed object height `z` (via mm/pixel scale).
- At a given height, each silhouette provides a 1D **occupied span** along the image
  column axis. Back-projected through the scene as a parallel **strip** (slab) at the
  stage rotation angle θ, positioned **relative to the calibrated rotation-axis
  column** (not the gem).
- The cross-section at height `z` is the **intersection of all strips** across the N
  angles — a convex polygon per slice.
- Stack the per-slice polygons along `z` and triangulate the side walls (plus end
  caps) into a watertight mesh.

Properties: fast, pure NumPy/Shapely, exact for orthographic single-axis capture.

### 4.2 Approach B — voxel space carving (future seam)
A general voxel grid carved by projecting voxels into each silhouette, then
marching-cubes to a mesh. Needed only if axis tilt or a second rotation axis is added
later. The `reconstruction/` module exposes a `Reconstructor` interface so B can be
dropped in without touching acquisition or vision code.

### 4.3 Off-center & asymmetric handling
Shape-from-silhouette reconstructs in a world frame defined by the **rotation axis**,
not by the gem, so the method **does not require the gem to be centered on the axis or
to be symmetric**:

- **Off-center placement is valid.** An off-center gem traces a circle as it rotates;
  its silhouette slides sinusoidally in the frame. That motion *encodes the offset*,
  and the reconstruction uses it correctly because every strip is registered to the
  calibrated axis column.
- **Frames are registered to the axis, never re-centered.** The pipeline must NOT
  auto-crop or re-center individual silhouettes — doing so would destroy the offset
  information and corrupt the hull.
- **Asymmetry is fully supported.** Each per-slice cross-section is the intersection
  of back-projected strips and can be any convex polygon; no symmetry is assumed or
  used.
- **Accurate axis calibration is the load-bearing requirement.** Off-center placement
  amplifies sensitivity to rotation-axis-column error, so calibration §7.2 must be
  precise.

The §4.5 per-slice-convex limitation is unchanged by off-center/asymmetric placement.

### 4.4 Pre-scan field-of-view / eccentricity check
Before a full scan, a quick probe rotates the gem through the angle range and checks
each silhouette:

- **Clipping guard:** if any silhouette touches a frame border, the gem (offset + size)
  exceeds the usable field of view at some angle → reconstruction would be truncated.
  The app warns and aborts the scan, naming the offending angle.
- **Eccentricity report:** the gem's offset from the rotation axis is measured and
  reported so the operator can re-seat the gem if it risks clipping. Eccentricity is a
  convenience-to-fix-if-clipping issue, **not** a correctness requirement.

This check lives in `acquisition/` and reuses the silhouette extraction (`vision/`)
and the calibrated axis (`calibration/`).

### 4.5 Known limitations (documented, not solved)
- **Single vertical axis ⇒ per-slice convex cross-sections.** True facet concavities
  and the under-table region are filled to the convex/tangent envelope.
- **Holder occlusion.** The mount occludes the silhouette near the gem base; the
  holder region is masked and reconstruction is valid above the mask.
- **Axis tilt × off-center interaction.** If the axis is not vertical *and* the gem is
  off-center, points smear across slices. Mitigation: keep the axis mechanically
  vertical and correct residual tilt from calibration §7.2.

These are inherent to single-axis silhouette scanning and acceptable for overall
geometry and proportion measurement.

## 5. Software architecture (Python, Windows)

Config-driven, independently testable modules:

```
gemscanner/
  camera/         CameraBackend interface + BaumerNeoAPICamera, OpenCVUsbCamera
  motion/         Serial client + RotaryStage (home, step, move_to_angle, wait_ready, status)
  acquisition/    ScanController: step-and-settle loop + pre-scan FoV check; writes dataset
  vision/         Silhouette extraction (threshold/Otsu, morphology, largest contour, holder mask)
  reconstruction/ Reconstructor interface + StripIntersectionReconstructor (A); seam for VoxelCarver (B)
  calibration/    Scale, rotation-axis column/tilt, steps-per-360°, eccentricity; persisted JSON
  storage/        Scan dataset I/O (frames + manifest.json); mesh export STL/PLY/OBJ
  ui/             Phase 1: CLI commands + Open3D live view / 3D preview
  config/         YAML config (camera backend, scan params, serial port, calibration path)
```

### 5.1 Camera abstraction
`CameraBackend` defines `open()`, `close()`, `set_exposure()`, `grab() -> ndarray`.
`BaumerNeoAPICamera` wraps Baumer **neoAPI** (Python); `OpenCVUsbCamera` wraps
`cv2.VideoCapture`. Backend is chosen in config — **swapping Baumer → USB is a config
change, not a code change.**

### 5.2 Motion client
`RotaryStage` speaks the ESP32 line protocol over a serial COM port (pyserial).
High-level methods hide the wire protocol; `wait_ready()` blocks until the ESP32
reports the move settled.

### 5.3 Scan dataset
A scan is a folder:
```
scan_<timestamp>/
  frames/0000.png ... 0179.png
  manifest.json   # angles[], mm_per_px, axis_column, axis_tilt, eccentricity,
                  # camera settings, steps_per_rev, settle_ms, backend, software version
```
Reconstruction reads only the dataset, so capture and reconstruction are decoupled
and reconstruction is re-runnable offline.

## 6. ESP32-C6 firmware (ESP-IDF)

Built with **ESP-IDF** (environment at `D:\ESP32`).

- **Link:** USB-CDC over the ESP32-C6 USB Serial/JTAG controller (`usb_serial_jtag`
  driver), exposed as a COM port on the PC.
- **Command protocol (line-based, ASCII):**
  | Command | Action | Reply |
  |---------|--------|-------|
  | `STEP <n>` | Move n microsteps (signed) | `OK` then `READY` after settle |
  | `MOVEDEG <x>` | Move x degrees | `OK` then `READY` |
  | `SETV <v>` / `SETACC <a>` | Set speed / accel | `OK` |
  | `SETSETTLE <ms>` | Set settle delay | `OK` |
  | `HOME` | Seek home sensor (if fitted) | `OK` then `READY` |
  | `STATUS` | Query | `STATUS angle=… steps=… state=…` |
  Errors reply `ERR <reason>`.
- **Step generation:** ESP-IDF **RMT** peripheral generates the STEP pulse train with
  software accel/decel ramps (trapezoidal) to avoid lost steps and reduce vibration;
  GPIO drives DIR and ENABLE. After a move, hold for the settle delay, then emit
  `READY`.
- **Pins → ADB-5331A:** STEP / DIR / ENABLE on free GPIOs (candidates GPIO **1/2/3**),
  optional home photo-interrupter input on another free GPIO. Avoid LCD pins
  (6,7,14,15,21,22), RGB LED (8), SD (4,5), and strapping pins (8,9,15). Final pin map
  to be confirmed against the board's broken-out header in the implementation plan.
- **Level shifting:** ADB-5331A inputs are opto-isolated pulse/direction inputs; add
  the series resistor / level shifter required for 3.3 V logic per the ADB-5331A
  datasheet.
- **steps-per-360°** = motor step angle × driver microstep setting × stage gear ratio.
  **Calibrated/configured, never hardcoded** (verified by a full-revolution check).
- **LCD (ST7789) + RGB LED (GPIO8):** show connection state, current angle, and scan
  progress.

## 7. Calibration

1. **Scale (mm/pixel):** image a calibrated gauge; derive mm/px (≈0.029 mm/px
   theoretical at 0.12× with ~3.45 µm pixels — measured for real).
2. **Rotation axis:** image a thin pin; track its centroid versus angle; fit a
   sinusoid → axis column and small tilt. Critical for correct strip intersection and
   the load-bearing input for off-center reconstruction (§4.3).
3. **Steps-per-360°:** command a nominal full revolution; correct against a physical
   reference until the stage returns to start.
4. **Eccentricity (per gem, runtime):** measured during the pre-scan FoV check (§4.4)
   from the silhouette-centroid swing; reported, not required to be zero.

Calibration is persisted to JSON and embedded in each scan's manifest.

## 8. Phasing

- **Phase 1 (this build):** ESP-IDF firmware (motion + protocol + LCD status); Python
  camera abstraction (Baumer first); motion client; step-and-settle ScanController +
  pre-scan FoV check; silhouette extraction; calibration routines; Approach A
  reconstruction + mesh export; **CLI + Open3D** live view and 3D preview.
- **Phase 2 (later):** USB camera backend hardening; Qt GUI; Approach B voxel carving;
  continuous-spin capture mode.

## 9. Success criteria

- A full 360° step-and-settle scan completes unattended and writes a valid dataset.
- The pre-scan FoV check correctly warns when an off-center gem would clip the frame.
- Silhouette extraction yields a clean single contour per frame under collimated
  backlight.
- Approach A produces a watertight mesh whose overall dimensions match caliper
  measurements of a reference gem within the calibrated mm/px tolerance — including an
  intentionally off-center and an asymmetric reference gem.
- Reconstruction is re-runnable offline from a stored dataset.
- Switching from the Baumer backend to a USB camera requires only a config edit.

## 10. Out of scope (Phase 1)

Qt GUI; voxel carving (B); continuous-spin capture; multi-axis capture; automated
facet/proportion grading; networked/WiFi control.
