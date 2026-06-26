# GemScanner

A gemstone **outline scanner**: a telecentric lens + machine-vision camera image a
backlit gemstone on a motorized rotary stage; the silhouettes are fused into a 3-D
mesh by **shape-from-silhouette** (per-slice visual hull). The project ships as three
independently-buildable plans:

- **Plan A — reconstruction + vision core** (`gemscanner/`): pure-Python visual hull,
  silhouette extraction, dataset/mesh storage. No hardware.
- **Plan B — ESP-IDF firmware** (`firmware/`): the ESP32-C6 motion controller (USB-CDC
  line protocol driving a 5-phase stepper). See `firmware/README.md`.
- **Plan C — hardware integration (this PC app)**: camera abstraction, a motion client
  that speaks the Plan B protocol, a step-and-settle scan controller, pre-scan FoV
  check, calibration, and a CLI with an Open3D viewer.

## Install

The project targets **Python 3.12** on Windows (Open3D has no 3.13 wheel yet).

```bash
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Runtime deps: `numpy`, `opencv-python`, `trimesh`, `pyserial`, `open3d`, `pyyaml`.
The Baumer **neoAPI** SDK is optional and installed separately; `BaumerCamera`
imports it lazily, so everything else works without it.

## CLI

```bash
# Reconstruct a mesh from an existing scan dataset (host, no hardware)
.venv/Scripts/python.exe -m gemscanner.cli reconstruct scans/gem01 -o gem.stl

# View a mesh in an interactive Open3D window
.venv/Scripts/python.exe -m gemscanner.cli view gem.stl

# Full bench scan: config -> prescan -> capture 360° -> reconstruct -> gem.stl
.venv/Scripts/python.exe -m gemscanner.cli scan -c config.example.yaml -o scans/gem01
```

`config.example.yaml` selects the camera backend (`mock` | `opencv` | `baumer`),
the serial port for the controller, scan parameters, and the calibration file.
Swapping the GigE Baumer camera for a USB one is a one-line config change.

## Tests

```bash
.venv/Scripts/python.exe -m pytest -q
```

All orchestration and protocol logic is host-tested in-process via `FakeFirmware`
(the Plan B protocol contract), `MockCamera`, and `SceneCamera` (which links the fake
motion angle to a rendered ellipsoid silhouette). Real serial I/O, the OpenCV/Baumer
cameras, and the Open3D window are **bench-verified** on hardware.

## Bench bring-up

With the camera + collimated backlight, the stage/driver/ESP32 powered, and a
`calibration.json` (axis column, mm/px, steps-per-rev) produced from the calibration
routines, run the `scan` subcommand above. The pre-scan FoV check aborts (naming the
clipping angle) if the gem leaves the frame at any rotation; otherwise it captures the
revolution, reconstructs, and writes a watertight `gem.stl`. Compare the bounding-box
extents against caliper measurements within the calibrated tolerance.
