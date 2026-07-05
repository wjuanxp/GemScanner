# GemScanner — day-to-day usage

Run everything from the repo root through the venv Python (`.venv\Scripts\python.exe`).
Config and calibration live in `config.example.yaml` (also the default working config)
and `calibration.json`.

> **Before any camera command:** close **Camera Explorer** (`bexplorer`) — only one
> app can hold the GigE camera at a time.

## Grab a single image

Grabbing is a bench *script* (not a CLI subcommand). It uses the camera settings from
the config (exposure, gain) unless overridden.

```powershell
.venv\Scripts\python.exe scripts\grab.py -o grab.png          # config exposure/gain
.venv\Scripts\python.exe scripts\grab.py -e 500 -o grab.png   # override exposure (us)
Invoke-Item grab.png
```

It prints `min/max/mean` so you can judge exposure — aim for a solid-black gem
(min near 0) on a bright background (~200–250).

## Start a new scan

```powershell
# prescan FoV check -> 180-view capture -> reconstruct -> scans\<name>\gem.stl
.venv\Scripts\python.exe -m gemscanner.cli scan -c config.example.yaml -o scans\gem03

# view the result
.venv\Scripts\python.exe -m gemscanner.cli view scans\gem03\gem.stl

# override mesh smoothing for this run (config default scan.smooth=10; 0 = raw hull)
.venv\Scripts\python.exe -m gemscanner.cli scan -c config.example.yaml -o scans\gem03 --smooth 0
```

## Reconstruct / view an existing dataset

```powershell
.venv\Scripts\python.exe -m gemscanner.cli reconstruct scans\gem03 -o out.stl --smooth 10
.venv\Scripts\python.exe -m gemscanner.cli view out.stl
```

## Scanning a *different* gem

`mm_per_px` and `steps_per_rev` carry over (same pedestal + motor), but the per-gem
geometry must be redone or the mesh will be skewed / include the pedestal:

```powershell
# 1. grab a frame; find the gem/pedestal junction row, then set
#    scan.holder_mask_rows = 1944 - junction_row  in config.example.yaml
.venv\Scripts\python.exe scripts\grab.py -o grab.png

# 2. re-fit the rotation axis for the new gem (one revolution)
.venv\Scripts\python.exe scripts\calibrate_axis.py -n 12 --write

# 3. scan (as above)
```

Full bench bring-up / calibration order is in [`scripts/README.md`](../scripts/README.md).

## Config knobs (`config.example.yaml`)

| Key | Meaning |
|-----|---------|
| `camera.exposure_us` | Exposure in µs. 500 with the collimated backlight (short avoids light leaking through the gem). |
| `camera.gain` | Sensor gain. |
| `scan.n_views` | Frames per 360° (180 default). More views only round the cross-sections; they don't fix vertical layering. |
| `scan.holder_mask_rows` | Bottom image rows to mask out (drops pedestal + stage below the gem). Per-gem: `1944 − junction_row`. |
| `scan.smooth` | Taubin smoothing iterations on the final mesh (0 = off; ~10 removes per-slice layering without shrinking). |
| `scan.settle_ms` | Post-move settle before capture. |

## GUI

Launch the guided GUI (dark theme; live preview + per-gem wizard + batch queue):

    .venv/Scripts/python.exe -m gemscanner.cli gui -p project.example.yaml

Per gem: mount → align (exposure/gain + silhouette overlay, aim for gem `min≈0`
on a bright background) → drag the holder-mask line to the gem/pedestal junction →
Calibrate axis → Scan → Reconstruct. Then select the next gem in the queue and
repeat. Close Camera Explorer (`bexplorer`) first — only one app can hold the GigE camera.
