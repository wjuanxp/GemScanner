# Bench scripts

Guided bring-up / calibration scripts. Run each from the repo root with the venv:

```powershell
.venv\Scripts\python.exe scripts\<name>.py --help
```

They all read `config.example.yaml` (`-c` to override) and read/write the
`calibration.json` named by `calibration_path` in that config.

## Recommended order

1. **Motion** — confirm the stage turns:
   ```powershell
   .venv\Scripts\python.exe scripts\smoke_motion.py --res 50000
   ```
2. **Camera** — grab a frame, eyeball exposure:
   ```powershell
   .venv\Scripts\python.exe scripts\grab.py -e 470000 -o grab.png ; Invoke-Item grab.png
   ```
3. **steps_per_rev** — empirical is most reliable (command N steps, measure degrees):
   ```powershell
   .venv\Scripts\python.exe scripts\calibrate_steps.py --empirical 50000 360
   # or directly:        --value 50000
   # or computed:        --compute 500 10 18     (motorSteps microstep gear)
   ```
4. **mm_per_px** — from a gauge of known length imaged by the camera:
   ```powershell
   .venv\Scripts\python.exe scripts\calibrate_scale.py --px 1000 --mm 28.8 --write
   ```
5. **axis_column** — fit the rotation axis from silhouette centroids:
   ```powershell
   .venv\Scripts\python.exe scripts\calibrate_axis.py -n 12 --write
   ```
6. **FoV check** — confirm the gem never clips over a revolution:
   ```powershell
   .venv\Scripts\python.exe scripts\check_fov.py -n 12
   ```

After 3-5, `calibration.json` holds `steps_per_rev`, `mm_per_px`, `axis_column`
(+ `axis_tilt_rad=0`, `eccentricity_mm`). Then run the full pipeline:

```powershell
.venv\Scripts\python.exe -m gemscanner.cli scan -c config.example.yaml -o scans\gem01
.venv\Scripts\python.exe -m gemscanner.cli view scans\gem01\gem.stl
```

## Notes
- Only one app can hold the GigE camera at once - close Camera Explorer before running these.
- `calibrate_steps`/`calibrate_scale`/`calibrate_axis` use `--write` to persist into
  `calibration.json`; without it they just print the value.
- Long camera exposure (e.g. 470 ms with no dedicated light) makes scans slow; lower it
  once the collimated backlight is installed.
