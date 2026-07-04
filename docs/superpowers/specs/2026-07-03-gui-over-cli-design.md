# GemScanner GUI — Design Spec

**Date:** 2026-07-03
**Status:** Approved (brainstorming), pending implementation plan
**Depends on:** Plan A (reconstruction core), Plan B (firmware), Plan C (hardware integration) — all merged to `main` and bench-verified 2026-07-03.

## 1. Purpose & Scope

A PySide6 desktop application that turns the current edit-YAML-and-rerun-scripts workflow into an
interactive, guided process. The headline capabilities the user asked for:

- **Live lighting/alignment preview** — see the camera frame while positioning the gem and backlight.
- **Interactive exposure/gain tuning** — adjust and see the effect immediately.
- **Easier batch scanning** — a guided queue of gems, one operator loop.

The GUI **wraps** existing library code. It does not reimplement reconstruction, calibration, or scan
orchestration. The existing `reconstruct` / `view` / `scan` CLI commands and the `scripts/` bring-up
tools remain fully working; the GUI is additive.

### Out of scope (YAGNI)

- Scan-history database or re-scan browser.
- Multi-user / remote / web access.
- A camera streaming API — live preview is polled `grab()`.
- Changes to the unused `OpenCvCamera.grab` / neoAPI `BaumerCamera` paths.

## 2. Architecture — Three Layers

### a. Service layer (Qt-free, unit-testable) — `gemscanner/gui/session.py`

A `ScanSession` owns exactly one opened camera and one stage, and exposes coarse operations that reuse
existing code:

- `grab()` — one frame.
- `analyze_frame(frame, threshold, holder_mask_rows)` — returns silhouette mask + `min/max/mean` +
  intensity histogram + FoV/eccentricity status. Built on existing `vision.silhouette.extract_silhouette`
  and `acquisition.prescan`.
- `calibrate_axis(n_probe, progress, cancel)` — rotates a revolution, fits `axis_column`.
- `run_scan(params, progress, cancel)` — drives the scan, writes the dataset.
- `reconstruct(out_dir, smooth)` — builds + smooths the mesh, returns watertight/extents.

This layer has no Qt imports and is fully testable headless with `MockCamera` / `SceneCamera` +
`FakeFirmware`.

### b. Project model — `gemscanner/gui/project.py`

Dataclasses:

- `GemJob`: `name`, `holder_mask_rows`, `axis_column`, optional `exposure_us` / `gain` overrides,
  `out` (output dir).
- `Project`: shared camera settings + serial config + project-level `mm_per_px` and `steps_per_rev`
  (these carry across gems on the same pedestal/motor), plus an ordered `gems: [GemJob, ...]` list.

Load/save to `project.yaml`, which is a **superset of the current `ScannerConfig` schema**. A single-gem
project therefore remains runnable by the existing `scan` CLI, and `calibration.json` semantics are
preserved.

### c. Qt UI layer — `gemscanner/gui/app.py` + widgets

- `LivePreviewWidget` — a `QGraphicsView` showing the frame with overlays:
  - Silhouette (Otsu-threshold) tint, so the operator sees exactly what reconstruction will "see"
    (reveals refracted-light leak holes, edge blur, uneven backlight). Threshold selectable Otsu/manual.
  - Draggable horizontal **holder-mask line**; everything below is greyed. Sets `holder_mask_rows`.
  - **FoV/eccentricity warning** — red when the silhouette touches an image border or is badly off
    the calibrated axis; green "ready to scan" when clear.
  - **Exposure stats + histogram** panel — live `min/max/mean` and an intensity histogram to confirm
    the gem hits ~0 and the background is bright/uniform.
- `WizardPanel` — the per-gem step sequence (Section 5).
- `QueuePanel` — add / remove / reorder gems.

## 3. Threading

The primary implementation risk. A **single `HardwareWorker` `QThread` is the only owner of the camera
and stage** — this mirrors the physical constraint that only one consumer can hold the GigE camera (and
the single serial port). The UI thread posts commands; the worker executes and emits Qt signals
(`frame_ready`, `progress`, `done`, `error`).

- **Live preview** = the worker polling `grab()` in a loop while idle, downscaling for display, emitting
  at whatever rate the 5 MP EXG50 sustains (a few fps is fine for alignment). It **auto-pauses** during
  moves, scans, and calibration because those run on the same single thread.
- **Cancellation** = a flag checked between scan views and between calibration probes.

No `CameraBackend` change is needed; polled preview works with `MockCamera` / `SceneCamera` for
hardware-free development and testing.

## 4. Required Refactor (small, removes duplication)

- Extract the axis-fit probe loop currently inline in `scripts/calibrate_axis.py:main` into
  `gemscanner/calibration/axis_probe.py` as a callable function with `progress` and `cancel` hooks.
- Add `progress` and `cancel` hooks to `ScanController.run` in
  `gemscanner/acquisition/scan_controller.py`.

`scripts/calibrate_axis.py` and the GUI then call the same `axis_probe` function; the scan path is shared
too. `run_scan_from_config` stays as the CLI entry point, but the GUI drives the finer-grained steps
directly since it already holds the camera and stage open.

## 5. Guided Wizard Flow (per gem)

0. **Connect** (once per session): choose project file, camera backend / exposure / gain, COM port →
   connect; live preview starts.
1. **Mount** — prompt operator to mount the gem → confirm.
2. **Align** — live preview + exposure/gain sliders + histogram. Tune until the gem is solid black
   (`min≈0`), the background is bright and uniform, the silhouette overlay is solid (no leak holes), and
   the FoV indicator is green.
3. **Holder mask** — drag the mask line to the gem/pedestal junction → `holder_mask_rows`.
4. **Calibrate axis** — [Run] rotates one revolution over `n_probe` steps, fits `axis_column`, shows the
   centroid-swing amplitude, with live progress. Writes into the gem's calibration.
5. **Scan** — runs `n_views` with a progress bar and cancel; the preview updates per view.
6. **Reconstruct + smooth** — builds the mesh, reports watertight + extents; [View] opens the Open3D
   viewer in a background window (offscreen render is unavailable on this machine — no EGL headless).
7. **Advance** — prompt "swap to `<next gem>`" → loop back to step 1 for the next queued gem.

## 6. Persistence

`project.yaml`, a superset of the current config schema:

```yaml
camera_backend: gentl
camera: { cti_path: ..., exposure_us: 500, gain: 5, pixel_format: Mono8 }
serial_port: COM3
serial_baud: 115200
mm_per_px: 0.0170          # project-level; carries across gems on the same pedestal/motor
steps_per_rev: 90000       # project-level
gems:
  - name: ruby-01
    holder_mask_rows: 660
    axis_column: 1214
    out: scans/ruby-01
    # optional per-gem exposure_us / gain overrides
  - name: emerald-02
    holder_mask_rows: 705
    axis_column: 1216
    out: scans/emerald-02
```

The GUI reads and writes this file. `calibration.json` semantics (axis_column / mm_per_px /
steps_per_rev / axis_tilt_rad) are preserved for CLI compatibility.

## 7. Error Handling

- Camera-open failure (e.g. GigE camera still held by Baumer Camera Explorer `bexplorer`) → clear
  non-fatal dialog telling the operator to close the other app.
- `StageError` timeouts → non-fatal dialog; the ESP32 reset-on-serial-open quirk is already handled by
  `SerialTransport` (settle + flush after open, fix `a1cba1f`).
- FoV-clip failure at the Scan step blocks scanning with an explicit message ("silhouette clips; re-seat
  the gem").
- Cancel stops between views and leaves the partial dataset flagged.

## 8. Testing

- Service layer (`ScanSession`) and project model (`Project` / `GemJob` load/save) unit-tested headless
  with `MockCamera` / `SceneCamera` + `FakeFirmware`, extending the existing 53-test suite.
- The end-to-end mock scan→reconstruct path (via `SceneCamera`) is reused to test `run_scan` /
  `reconstruct` wiring through the session.
- UI kept thin — logic lives in the tested service layer. Optional `pytest-qt` smoke test for widget
  construction and the mask-line → `holder_mask_rows` binding.

## 9. Dependencies

- New: **PySide6** (Qt for Python). Optional dev dep: `pytest-qt`.
- Existing venv is Python 3.12 (open3d has no 3.13 wheel) — PySide6 has 3.12 wheels.

## 10. Open Questions / Deferred

None blocking. Deferred to future work: scan history, unattended multi-gem (blocked by the physical swap
requirement anyway), and finishing/removing the unused OpenCV/neoAPI camera backends.
