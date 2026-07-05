# GemScanner GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 desktop GUI that wraps the existing GemScanner library with a live alignment/exposure preview and a guided per-gem batch-scan wizard.

**Architecture:** Three layers. (1) A Qt-free **service layer** (`ScanSession`, `analyze_frame`, `probe_axis`) that reuses the existing camera/stage/reconstruction code and is unit-tested headless with `SceneCamera` + `FakeFirmware`. (2) A **Qt worker** (`HardwareWorker`, one QThread owning camera+stage) that polls `grab()` for live preview and runs long operations off the UI thread. (3) **Qt widgets** (preview, wizard, queue, main window) kept thin, styled by a single dark-theme QSS.

**Tech Stack:** Python 3.12, PySide6 (Qt for Python), numpy, opencv-python, existing `gemscanner` package. Tests: pytest + pytest-qt.

## Global Constraints

- Python floor stays `>=3.11`; the working venv is **Python 3.12** (open3d has no 3.13 wheel). PySide6 has 3.12 wheels.
- New runtime dependency: **PySide6**. New dev dependency: **pytest-qt**. Add both to `pyproject.toml`.
- Qt-free layers (`project.py`, `analysis.py`, `session.py`, `axis_probe.py`) MUST NOT import PySide6 — they are unit-tested without a display.
- Widget/worker tests run headless: set `QT_QPA_PLATFORM=offscreen`. Guard every Qt test file with `pytest.importorskip("PySide6")`.
- Reuse existing code — do NOT reimplement silhouette extraction, axis fitting, prescan, scan, or reconstruction. Exact reused signatures:
  - `extract_silhouette(image, threshold=None, holder_mask_rows=0) -> bool ndarray` (`gemscanner/vision/silhouette.py`)
  - `fit_rotation_axis(angles_deg, centroid_cols) -> (axis_column, amplitude)` (`gemscanner/calibration/fit.py`)
  - `prescan_fov_check(camera, stage, axis_column, mm_per_px, n_probe=12, threshold=None, margin_px=2, holder_mask_rows=0) -> PrescanResult(ok, offending_angle, eccentricity_mm, touched_border)` (`gemscanner/acquisition/prescan.py`)
  - `ScanController(camera, stage).run(out_dir, params) -> out_dir` (`gemscanner/acquisition/scan_controller.py`)
  - `ScanParams(n_views, mm_per_px, axis_column, axis_tilt_rad, eccentricity_mm)`
  - `reconstruct_dataset(dataset_path, params=None) -> trimesh.Trimesh` with `ReconstructionParams(n_radial, holder_mask_rows, threshold, bbox_mm)`
  - `smooth_mesh(mesh, iterations=10) -> mesh`; `export_mesh(mesh, path)`; `show_mesh(mesh_or_path)`
  - `create_camera(config)` where `config` has `.camera_backend` (str) and `.camera` (dict) — `gemscanner/camera/factory.py`
  - `RotaryStage(transport)` with `.set_resolution(steps)`, `.set_settle(ms)`, `.move_deg(deg)`; `SerialTransport(port, baud)`
  - `Calibration(mm_per_px, axis_column, axis_tilt_rad=0.0, steps_per_rev=0, eccentricity_mm=None)` with `.load(path)`/`.save(path)`
  - `ScannerConfig(camera_backend, camera, serial_port, serial_baud, scan, calibration_path)` with `.load(path)`/`.save(path)`
- Test doubles: `SceneCamera(stage_fw, rx, ry, rz, mm_per_px, width, height, center_offset=(0,0))` and `FakeFirmware()` used as a `RotaryStage` transport (see `tests/test_end_to_end_scan.py`).
- Design spec: `docs/superpowers/specs/2026-07-03-gui-over-cli-design.md`.

---

## File Structure

New package `gemscanner/gui/`:

- `gemscanner/gui/__init__.py` — package marker.
- `gemscanner/gui/project.py` — `GemJob`, `Project` dataclasses; `project.yaml` load/save (Qt-free).
- `gemscanner/gui/analysis.py` — `FrameAnalysis` dataclass + `analyze_frame(...)` (Qt-free, pure CPU).
- `gemscanner/gui/session.py` — `ScanSession` owns camera+stage; grab/analyze/calibrate/prescan/scan/reconstruct (Qt-free).
- `gemscanner/gui/worker.py` — `HardwareWorker(QThread)`: preview polling + command queue + signals (Qt).
- `gemscanner/gui/preview_widget.py` — `LivePreviewWidget` (Qt): frame + silhouette tint + draggable mask line + FoV/histogram.
- `gemscanner/gui/wizard_panel.py` — `WizardPanel` (Qt): the per-gem step sequence.
- `gemscanner/gui/queue_panel.py` — `QueuePanel` (Qt): gem list add/remove/reorder.
- `gemscanner/gui/main_window.py` — `MainWindow` (Qt): wires panels + worker.
- `gemscanner/gui/app.py` — `main()`: QApplication, load QSS, show window (Qt).
- `gemscanner/gui/style.qss` — dark-theme minimalist stylesheet.

New library module:

- `gemscanner/calibration/axis_probe.py` — `probe_axis(...)` (extracted from `scripts/calibrate_axis.py`).

Modified:

- `gemscanner/acquisition/scan_controller.py` — add `progress`/`cancel` to `run`.
- `scripts/calibrate_axis.py` — call `probe_axis`.
- `gemscanner/cli.py` — add `gui` subcommand.
- `pyproject.toml` — add PySide6 + pytest-qt.

New tests:

- `tests/gui/test_project.py`, `tests/gui/test_analysis.py`, `tests/gui/test_session.py`
- `tests/calibration/test_axis_probe.py`
- `tests/acquisition/test_scan_controller.py` (extend existing)
- `tests/gui/test_worker.py`, `tests/gui/test_widgets.py` (Qt smoke, importorskip)

---

## Task 1: Project model (persistence)

**Files:**
- Create: `gemscanner/gui/__init__.py` (empty)
- Create: `gemscanner/gui/project.py`
- Test: `tests/gui/__init__.py` (empty), `tests/gui/test_project.py`

**Interfaces:**
- Produces:
  - `GemJob(name: str, holder_mask_rows: int = 0, axis_column: float = 0.0, exposure_us: float | None = None, gain: float | None = None, out: str = "")`
  - `Project(camera_backend: str, camera: dict, serial_port: str, serial_baud: int, mm_per_px: float, steps_per_rev: int, gems: list[GemJob], calibration_path: str)`
  - `Project.load(path) -> Project`, `Project.save(path)`
  - `Project.to_scanner_config(gem: GemJob) -> ScannerConfig` — builds a single-gem `ScannerConfig` so the existing CLI/functions can consume it.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/__init__.py` (empty) and `tests/gui/test_project.py`:

```python
from gemscanner.gui.project import GemJob, Project


def test_project_roundtrip(tmp_path):
    p = Project(
        camera_backend="gentl",
        camera={"cti_path": "x.cti", "exposure_us": 500, "gain": 5},
        serial_port="COM3", serial_baud=115200,
        mm_per_px=0.017, steps_per_rev=90000,
        gems=[
            GemJob(name="ruby-01", holder_mask_rows=660, axis_column=1214.0, out="scans/ruby-01"),
            GemJob(name="emerald-02", holder_mask_rows=705, axis_column=1216.0,
                   exposure_us=400.0, out="scans/emerald-02"),
        ],
        calibration_path="calibration.json",
    )
    path = tmp_path / "project.yaml"
    p.save(str(path))
    q = Project.load(str(path))
    assert q.mm_per_px == 0.017
    assert q.steps_per_rev == 90000
    assert [g.name for g in q.gems] == ["ruby-01", "emerald-02"]
    assert q.gems[1].exposure_us == 400.0
    assert isinstance(q.gems[0], GemJob)


def test_to_scanner_config_merges_gem_overrides():
    p = Project(
        camera_backend="gentl", camera={"exposure_us": 500, "gain": 5},
        serial_port="COM3", serial_baud=115200,
        mm_per_px=0.017, steps_per_rev=90000,
        gems=[GemJob(name="g", holder_mask_rows=660, axis_column=1214.0,
                     exposure_us=400.0, out="scans/g")],
        calibration_path="calibration.json",
    )
    cfg = p.to_scanner_config(p.gems[0])
    assert cfg.camera_backend == "gentl"
    assert cfg.camera["exposure_us"] == 400.0   # gem override wins
    assert cfg.camera["gain"] == 5              # project value kept
    assert cfg.scan["holder_mask_rows"] == 660
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_project.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/__init__.py` (empty file). Create `gemscanner/gui/project.py`:

```python
from dataclasses import dataclass, field, asdict
import yaml
from gemscanner.config import ScannerConfig


@dataclass
class GemJob:
    name: str
    holder_mask_rows: int = 0
    axis_column: float = 0.0
    exposure_us: float | None = None
    gain: float | None = None
    out: str = ""


@dataclass
class Project:
    camera_backend: str = "mock"
    camera: dict = field(default_factory=dict)
    serial_port: str = "COM3"
    serial_baud: int = 115200
    mm_per_px: float = 0.0
    steps_per_rev: int = 0
    gems: list = field(default_factory=list)
    calibration_path: str = "calibration.json"

    def save(self, path):
        data = asdict(self)  # dataclass GemJob -> dict recursively
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        gems = [GemJob(**g) for g in data.pop("gems", [])]
        return cls(gems=gems, **data)

    def to_scanner_config(self, gem: GemJob) -> ScannerConfig:
        camera = dict(self.camera)
        if gem.exposure_us is not None:
            camera["exposure_us"] = gem.exposure_us
        if gem.gain is not None:
            camera["gain"] = gem.gain
        return ScannerConfig(
            camera_backend=self.camera_backend,
            camera=camera,
            serial_port=self.serial_port,
            serial_baud=self.serial_baud,
            scan={"n_views": 180, "settle_ms": 150,
                  "holder_mask_rows": gem.holder_mask_rows},
            calibration_path=self.calibration_path,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_project.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/__init__.py gemscanner/gui/project.py tests/gui/__init__.py tests/gui/test_project.py
git commit -m "feat(gui): project model with per-gem jobs and config export"
```

---

## Task 2: Frame analysis (preview overlays data)

**Files:**
- Create: `gemscanner/gui/analysis.py`
- Test: `tests/gui/test_analysis.py`

**Interfaces:**
- Consumes: `extract_silhouette` (see Global Constraints).
- Produces:
  - `FrameAnalysis(min: int, max: int, mean: float, histogram: list[int], mask: np.ndarray, touches_border: bool, bbox: tuple | None, centroid_col: float | None)` where `histogram` has 256 ints and `bbox` is `(rmin, rmax, cmin, cmax)`.
  - `analyze_frame(frame, threshold=None, holder_mask_rows=0, margin_px=2) -> FrameAnalysis`

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_analysis.py`:

```python
import numpy as np
from gemscanner.gui.analysis import analyze_frame


def _bg(h=100, w=100):
    return np.full((h, w), 255, np.uint8)


def test_interior_object_not_touching_border():
    img = _bg()
    img[30:70, 40:60] = 0            # dark object well inside
    a = analyze_frame(img)
    assert a.min == 0 and a.max == 255
    assert a.mean > 200
    assert len(a.histogram) == 256
    assert a.touches_border is False
    assert a.bbox == (30, 69, 40, 59)
    assert abs(a.centroid_col - 49.5) < 1.0


def test_object_touching_left_border_flagged():
    img = _bg()
    img[30:70, 0:20] = 0             # touches left edge
    a = analyze_frame(img)
    assert a.touches_border is True


def test_empty_silhouette_when_all_background():
    a = analyze_frame(_bg())
    assert a.bbox is None
    assert a.centroid_col is None
    assert a.touches_border is False


def test_holder_mask_excludes_bottom_rows():
    img = _bg()
    img[80:100, 40:60] = 0           # object only in bottom rows
    a = analyze_frame(img, holder_mask_rows=25)
    assert a.bbox is None            # masked away
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.analysis'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/analysis.py`:

```python
from dataclasses import dataclass
import numpy as np
import cv2
from gemscanner.vision.silhouette import extract_silhouette


@dataclass
class FrameAnalysis:
    min: int
    max: int
    mean: float
    histogram: list
    mask: object
    touches_border: bool
    bbox: object          # (rmin, rmax, cmin, cmax) or None
    centroid_col: object  # float or None


def analyze_frame(frame, threshold=None, holder_mask_rows=0, margin_px=2):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    hist = np.bincount(gray.ravel(), minlength=256)[:256].astype(int).tolist()
    mask = extract_silhouette(frame, threshold, holder_mask_rows)
    ys, xs = np.where(mask)
    if xs.size == 0:
        return FrameAnalysis(int(gray.min()), int(gray.max()), float(gray.mean()),
                             hist, mask, False, None, None)
    h, w = mask.shape
    touches = bool(xs.min() <= margin_px or xs.max() >= w - 1 - margin_px or
                   ys.min() <= margin_px or ys.max() >= h - 1 - margin_px)
    bbox = (int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max()))
    return FrameAnalysis(int(gray.min()), int(gray.max()), float(gray.mean()),
                         hist, mask, touches, bbox, float(xs.mean()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_analysis.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/analysis.py tests/gui/test_analysis.py
git commit -m "feat(gui): analyze_frame for live preview overlays and stats"
```

---

## Task 3: Extract `probe_axis` (shared axis calibration)

**Files:**
- Create: `gemscanner/calibration/axis_probe.py`
- Modify: `scripts/calibrate_axis.py:42-63` (replace the inline probe loop with a call)
- Test: `tests/calibration/test_axis_probe.py`

**Interfaces:**
- Consumes: `extract_silhouette`, `fit_rotation_axis`.
- Produces:
  - `probe_axis(camera, stage, n_probe=12, threshold=None, holder_mask_rows=0, progress=None, cancel=None) -> (axis_column: float, amplitude: float)`
  - `progress(done: int, total: int)` called once per probe; `cancel() -> bool` checked before each probe. Raises `ValueError` if fewer than 3 silhouettes.

- [ ] **Step 1: Write the failing test**

Create `tests/calibration/test_axis_probe.py`:

```python
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.calibration.axis_probe import probe_axis


def _rig(offset=(0.0, 0.0)):
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    stage.set_resolution(36000)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05,
                      width=400, height=400, center_offset=offset)
    return stage, cam


def test_probe_axis_fits_center_with_progress():
    stage, cam = _rig(offset=(2.0, 0.0))   # off-center -> centroid swings
    seen = []
    axis, amp = probe_axis(cam, stage, n_probe=12,
                           progress=lambda d, n: seen.append((d, n)))
    assert abs(axis - (400 - 1) / 2.0) < 2.0
    assert amp > 1.0                        # real swing detected
    assert seen[-1] == (12, 12)


def test_probe_axis_cancel_stops_early():
    stage, cam = _rig(offset=(2.0, 0.0))
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2               # cancel after 2 probes -> <3 silhouettes

    import pytest
    # cancelling before 3 silhouettes are collected interrupts the loop, so the
    # fit has too few points and raises -- proof the cancel actually stopped it.
    with pytest.raises(ValueError):
        probe_axis(cam, stage, n_probe=12, cancel=cancel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/calibration/test_axis_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.calibration.axis_probe'`.

- [ ] **Step 3: Implement**

Create `gemscanner/calibration/axis_probe.py`:

```python
import numpy as np
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.calibration.fit import fit_rotation_axis


def probe_axis(camera, stage, n_probe=12, threshold=None, holder_mask_rows=0,
               progress=None, cancel=None):
    """Rotate one revolution, fit the rotation-axis column from silhouette centroids.

    Returns (axis_column, amplitude). Raises ValueError with < 3 usable silhouettes.
    """
    inc = 360.0 / n_probe
    angles, cols = [], []
    cancelled = False
    with camera:
        for k in range(n_probe):
            if cancel is not None and cancel():
                cancelled = True
                break
            if k:
                stage.move_deg(inc)
            mask = extract_silhouette(camera.grab(), threshold, holder_mask_rows)
            xs = np.where(mask)[1]
            if xs.size:
                cols.append(float(xs.mean()))
                angles.append(k * inc)
            if progress is not None:
                progress(k + 1, n_probe)
        if not cancelled:
            stage.move_deg(inc)   # complete the revolution back to start
    if len(cols) < 3:
        raise ValueError("not enough silhouettes to fit axis (need >= 3)")
    return fit_rotation_axis(angles, cols)
```

Then update `scripts/calibrate_axis.py`. Replace the block currently at lines 42-63 (the `inc = ...` loop through `C.save_cal(...)`) with:

```python
    from gemscanner.calibration.axis_probe import probe_axis
    cam = C.build_camera(cfg)
    stage = C.build_stage(cfg)
    stage.set_resolution(res)

    def _progress(done, total):
        print(f"  probe {done}/{total}")

    axis, amp = probe_axis(cam, stage, n_probe=a.n_probe, threshold=a.threshold,
                           holder_mask_rows=holder, progress=_progress)
    print(f"axis_column = {axis:.2f}   (centroid swing amplitude {amp:.2f} px)")
    if a.write:
        cal["axis_column"] = axis
        C.save_cal(cal, cfg.calibration_path)
```

Remove the now-unused `import numpy as np`, `from gemscanner.vision.silhouette import extract_silhouette`, and `from gemscanner.calibration.fit import fit_rotation_axis` lines at the top of `scripts/calibrate_axis.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/calibration/test_axis_probe.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/calibration/axis_probe.py scripts/calibrate_axis.py tests/calibration/test_axis_probe.py
git commit -m "refactor(calibration): extract probe_axis; share with calibrate_axis script"
```

---

## Task 4: Add progress/cancel to `ScanController.run`

**Files:**
- Modify: `gemscanner/acquisition/scan_controller.py:24-46` (the `run` method)
- Test: `tests/acquisition/test_scan_controller.py` (add two tests)

**Interfaces:**
- Produces: `ScanController.run(out_dir, params, progress=None, cancel=None) -> out_dir`. `progress(done, total)` fires once per captured view; `cancel() -> bool` checked before each view; on cancel the manifest reflects only captured frames. Existing 2-arg callers keep working.

- [ ] **Step 1: Write the failing test**

Add to `tests/acquisition/test_scan_controller.py`:

```python
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.storage.manifest import ScanManifest


def _rig():
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    stage.set_resolution(36000)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=120, height=120)
    return stage, cam


def test_run_reports_progress_per_view(tmp_path):
    stage, cam = _rig()
    seen = []
    ScanController(cam, stage).run(
        str(tmp_path / "s"), ScanParams(n_views=10, mm_per_px=0.05, axis_column=59.5),
        progress=lambda d, n: seen.append((d, n)))
    assert seen[0] == (1, 10) and seen[-1] == (10, 10)


def test_run_cancel_captures_partial(tmp_path):
    stage, cam = _rig()
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 4     # stop before the 5th view

    out = ScanController(cam, stage).run(
        str(tmp_path / "s"), ScanParams(n_views=180, mm_per_px=0.05, axis_column=59.5),
        cancel=cancel)
    m = ScanManifest.load(str(tmp_path / "s" / "manifest.json"))
    assert len(m.frame_files) == 4
```

Note: if `ScanManifest` has no `load`, load the JSON directly:
```python
import json
with open(tmp_path / "s" / "manifest.json") as f:
    assert len(json.load(f)["frame_files"]) == 4
```
Use whichever matches the existing `ScanManifest` API (check `gemscanner/storage/manifest.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_scan_controller.py -v -k "progress or cancel"`
Expected: FAIL — `run()` got an unexpected keyword argument `progress`.

- [ ] **Step 3: Implement**

Replace the `run` method in `gemscanner/acquisition/scan_controller.py` with:

```python
    def run(self, out_dir, params, progress=None, cancel=None):
        os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
        inc = 360.0 / params.n_views
        angles, files = [], []
        h = w = 0
        with self.camera:
            for i in range(params.n_views):
                if cancel is not None and cancel():
                    break
                if i > 0:
                    self.stage.move_deg(inc)
                frame = self.camera.grab()
                h, w = frame.shape[:2]
                fname = f"{i:04d}.png"
                cv2.imwrite(os.path.join(out_dir, "frames", fname), frame)
                files.append(f"frames/{fname}")
                angles.append(round(i * inc, 6))
                if progress is not None:
                    progress(i + 1, params.n_views)
        ScanManifest(
            angles_deg=angles, mm_per_px=params.mm_per_px,
            axis_column=params.axis_column, axis_tilt_rad=params.axis_tilt_rad,
            eccentricity_mm=params.eccentricity_mm,
            image_width=w, image_height=h, frame_files=files,
            metadata={"source": "ScanController"},
        ).save(os.path.join(out_dir, "manifest.json"))
        return out_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_scan_controller.py -v`
Expected: PASS (existing tests + 2 new).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/acquisition/scan_controller.py tests/acquisition/test_scan_controller.py
git commit -m "feat(acquisition): progress and cancel hooks on ScanController.run"
```

---

## Task 5: `ScanSession` service layer

**Files:**
- Create: `gemscanner/gui/session.py`
- Test: `tests/gui/test_session.py`

**Interfaces:**
- Consumes: `create_camera`, `RotaryStage`, `SerialTransport`, `probe_axis` (Task 3), `analyze_frame` (Task 2), `prescan_fov_check`, `ScanController`, `ScanParams`, `reconstruct_dataset`, `ReconstructionParams`, `smooth_mesh`, `export_mesh`, `Calibration`.
- Produces:
  - `ScanSession(config, camera=None, stage=None)` — `config` is a `ScannerConfig`; camera/stage injectable for tests.
  - `configure_stage(steps_per_rev, settle_ms=150)`
  - `grab() -> np.ndarray` (one-shot, opens+closes the camera)
  - `analyze(frame, threshold=None, holder_mask_rows=0) -> FrameAnalysis`
  - `calibrate_axis(n_probe=12, threshold=None, holder_mask_rows=0, progress=None, cancel=None) -> (axis, amp)`
  - `prescan(axis_column, mm_per_px, holder_mask_rows=0, n_probe=12) -> PrescanResult`
  - `scan(out_dir, params, progress=None, cancel=None) -> out_dir`
  - `reconstruct(out_dir, holder_mask_rows=0, smooth=0) -> (mesh, watertight: bool, extents: tuple)` — also writes `<out_dir>/gem.stl`.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_session.py`:

```python
from gemscanner.config import ScannerConfig
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.acquisition.scan_controller import ScanParams
from gemscanner.gui.session import ScanSession


def _session():
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=400, height=400)
    cfg = ScannerConfig(camera_backend="mock")
    s = ScanSession(cfg, camera=cam, stage=stage)
    s.configure_stage(36000, settle_ms=0)
    return s


def test_session_grab_and_analyze():
    s = _session()
    frame = s.grab()
    a = s.analyze(frame)
    assert a.bbox is not None                 # ellipsoid silhouette present


def test_session_calibrate_scan_reconstruct(tmp_path):
    s = _session()
    axis, amp = s.calibrate_axis(n_probe=12)
    assert abs(axis - (400 - 1) / 2.0) < 2.0

    prog = []
    out = s.scan(str(tmp_path / "scan"),
                 ScanParams(n_views=180, mm_per_px=0.05, axis_column=axis),
                 progress=lambda d, n: prog.append(d))
    assert len(prog) == 180

    mesh, watertight, extents = s.reconstruct(out, holder_mask_rows=0, smooth=0)
    assert watertight
    assert abs(extents[2] - 10.0) < 0.4        # 2*rz
    assert (tmp_path / "scan" / "gem.stl").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.session'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/session.py`:

```python
import os
from gemscanner.camera.factory import create_camera
from gemscanner.motion.transport import SerialTransport
from gemscanner.motion.stage import RotaryStage
from gemscanner.acquisition.scan_controller import ScanController
from gemscanner.acquisition.prescan import prescan_fov_check
from gemscanner.calibration.axis_probe import probe_axis
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.smoothing import smooth_mesh
from gemscanner.storage.mesh_io import export_mesh
from gemscanner.gui.analysis import analyze_frame


class ScanSession:
    """Owns one camera + one stage and exposes the operations the GUI drives.

    Qt-free so it can be unit-tested headless with SceneCamera + FakeFirmware.
    """

    def __init__(self, config, camera=None, stage=None):
        self.config = config
        self.camera = camera if camera is not None else create_camera(config)
        self.stage = stage if stage is not None else RotaryStage(
            SerialTransport(config.serial_port, config.serial_baud))

    def configure_stage(self, steps_per_rev, settle_ms=150):
        self.stage.set_resolution(steps_per_rev)
        self.stage.set_settle(settle_ms)

    def set_exposure(self, us):
        self.camera.set_exposure(us)

    def grab(self):
        with self.camera:
            return self.camera.grab()

    def analyze(self, frame, threshold=None, holder_mask_rows=0):
        return analyze_frame(frame, threshold, holder_mask_rows)

    def calibrate_axis(self, n_probe=12, threshold=None, holder_mask_rows=0,
                       progress=None, cancel=None):
        return probe_axis(self.camera, self.stage, n_probe=n_probe,
                          threshold=threshold, holder_mask_rows=holder_mask_rows,
                          progress=progress, cancel=cancel)

    def prescan(self, axis_column, mm_per_px, holder_mask_rows=0, n_probe=12):
        return prescan_fov_check(self.camera, self.stage, axis_column, mm_per_px,
                                 n_probe=n_probe, holder_mask_rows=holder_mask_rows)

    def scan(self, out_dir, params, progress=None, cancel=None):
        return ScanController(self.camera, self.stage).run(
            out_dir, params, progress=progress, cancel=cancel)

    def reconstruct(self, out_dir, holder_mask_rows=0, smooth=0):
        mesh = reconstruct_dataset(
            out_dir, ReconstructionParams(holder_mask_rows=holder_mask_rows))
        mesh = smooth_mesh(mesh, smooth)
        export_mesh(mesh, os.path.join(out_dir, "gem.stl"))
        return mesh, bool(mesh.is_watertight), tuple(mesh.bounding_box.extents)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_session.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/session.py tests/gui/test_session.py
git commit -m "feat(gui): ScanSession service layer wrapping camera+stage ops"
```

---

## Task 6: PySide6 dependency + `HardwareWorker` thread

**Files:**
- Modify: `pyproject.toml:9,12`
- Create: `gemscanner/gui/worker.py`
- Test: `tests/gui/test_worker.py`

**Interfaces:**
- Consumes: `ScanSession` (Task 5), `analyze_frame` (Task 2).
- Produces: `HardwareWorker(QThread)` owning the session. It serialises all camera/stage access on its own thread.
  - Signals: `frameReady(object, object)` = `(frame, FrameAnalysis)`; `progress(str, int, int)` = `(op, done, total)`; `result(str, object)` = `(op, payload)`; `failed(str, str)` = `(op, message)`.
  - Methods (thread-safe, called from UI thread): `set_view(threshold, holder_mask_rows)`, `start_preview()`, `stop_preview()`, `cancel()`, `post(op, **kwargs)`, `shutdown()`.
  - Supported ops: `"calibrate"` → `result("calibrate", (axis, amp))`; `"scan"` → `result("scan", out_dir)`; `"reconstruct"` → `result("reconstruct", (watertight, extents))`.

- [ ] **Step 1: Add dependencies**

Edit `pyproject.toml`. Change line 9 to add PySide6:

```toml
dependencies = ["numpy", "opencv-python", "trimesh", "pyserial", "open3d", "pyyaml", "harvesters", "PySide6"]
```

Change line 12 to add pytest-qt:

```toml
dev = ["pytest", "pytest-qt"]
```

Install into the venv:

```bash
.venv/Scripts/python.exe -m pip install PySide6 pytest-qt
```

- [ ] **Step 2: Write the failing test**

Create `tests/gui/test_worker.py`:

```python
import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gemscanner.config import ScannerConfig
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.gui.session import ScanSession
from gemscanner.gui.worker import HardwareWorker


def _worker():
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=200, height=200)
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=stage)
    session.configure_stage(36000, settle_ms=0)
    return HardwareWorker(session)


def test_preview_emits_frame_and_analysis(qtbot):
    w = _worker()
    w.start()
    try:
        w.set_view(threshold=None, holder_mask_rows=0)
        with qtbot.waitSignal(w.frameReady, timeout=3000) as sig:
            w.start_preview()
        frame, analysis = sig.args
        assert isinstance(frame, np.ndarray)
        assert analysis.bbox is not None
    finally:
        w.shutdown()
        w.wait(3000)


def test_calibrate_op_emits_result(qtbot):
    w = _worker()
    w.start()
    try:
        with qtbot.waitSignal(w.result, timeout=5000) as sig:
            w.post("calibrate", n_probe=12)
        op, payload = sig.args
        assert op == "calibrate"
        axis, amp = payload
        assert abs(axis - (200 - 1) / 2.0) < 2.0
    finally:
        w.shutdown()
        w.wait(3000)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.worker'`.

- [ ] **Step 4: Implement**

Create `gemscanner/gui/worker.py`:

```python
import queue
from PySide6.QtCore import QThread, Signal


class HardwareWorker(QThread):
    """The single owner of camera + stage. Polls grab() for live preview and
    runs long ops (calibrate/scan/reconstruct) off the UI thread.

    Preview auto-pauses (camera closed) whenever a queued op runs, so the
    existing `with camera:` blocks inside those ops never overlap the preview.
    """

    frameReady = Signal(object, object)   # frame, FrameAnalysis
    progress = Signal(str, int, int)      # op, done, total
    result = Signal(str, object)          # op, payload
    failed = Signal(str, str)             # op, message

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._cmds = queue.Queue()
        self._preview = False
        self._cam_open = False
        self._cancel = False
        self._running = True
        self._threshold = None
        self._holder = 0

    # ---- called from the UI thread ----
    def set_view(self, threshold, holder_mask_rows):
        self._threshold = threshold
        self._holder = int(holder_mask_rows)

    def start_preview(self):
        self._preview = True

    def stop_preview(self):
        self._preview = False

    def cancel(self):
        self._cancel = True

    def post(self, op, **kwargs):
        self._cmds.put((op, kwargs))

    def shutdown(self):
        self._running = False
        self._cmds.put(("_stop", {}))

    # ---- runs on this thread ----
    def run(self):
        while self._running:
            try:
                op, kwargs = self._cmds.get(timeout=0.03)
            except queue.Empty:
                if self._preview:
                    self._preview_frame()
                continue
            if op == "_stop":
                break
            self._pause_preview()
            self._cancel = False
            handler = getattr(self, f"_op_{op}", None)
            if handler is None:
                self.failed.emit(op, f"unknown op {op!r}")
                continue
            try:
                handler(**kwargs)
            except Exception as exc:                     # surface, don't crash
                self.failed.emit(op, str(exc))
        self._pause_preview()

    def _pause_preview(self):
        self._preview = False
        if self._cam_open:
            try:
                self._session.camera.close()
            finally:
                self._cam_open = False

    def _preview_frame(self):
        try:
            if not self._cam_open:
                self._session.camera.open()
                self._cam_open = True
            frame = self._session.camera.grab()
            analysis = self._session.analyze(frame, self._threshold, self._holder)
            self.frameReady.emit(frame, analysis)
        except Exception as exc:
            self._preview = False
            self.failed.emit("preview", str(exc))

    def _op_calibrate(self, n_probe=12):
        axis, amp = self._session.calibrate_axis(
            n_probe=n_probe, threshold=self._threshold, holder_mask_rows=self._holder,
            progress=lambda d, n: self.progress.emit("calibrate", d, n),
            cancel=lambda: self._cancel)
        self.result.emit("calibrate", (axis, amp))

    def _op_scan(self, out_dir, params):
        self._session.scan(
            out_dir, params,
            progress=lambda d, n: self.progress.emit("scan", d, n),
            cancel=lambda: self._cancel)
        self.result.emit("scan", out_dir)

    def _op_reconstruct(self, out_dir, holder_mask_rows=0, smooth=0):
        _, watertight, extents = self._session.reconstruct(
            out_dir, holder_mask_rows=holder_mask_rows, smooth=smooth)
        self.result.emit("reconstruct", (watertight, extents))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_worker.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml gemscanner/gui/worker.py tests/gui/test_worker.py
git commit -m "feat(gui): HardwareWorker thread for preview polling and off-UI ops"
```

---

## Task 7: `LivePreviewWidget` (frame + overlays)

**Files:**
- Create: `gemscanner/gui/preview_widget.py`
- Test: `tests/gui/test_widgets.py`

**Interfaces:**
- Consumes: `FrameAnalysis` (Task 2).
- Produces: `LivePreviewWidget(QWidget)`
  - `set_frame(frame: np.ndarray, analysis: FrameAnalysis)` — draws the frame, silhouette tint, FoV state, and updates the stats label.
  - `holder_mask_rows() -> int` — current draggable-line value (rows from the bottom).
  - `set_holder_mask_rows(rows: int)`
  - Signal `maskChanged(int)` emitted when the user drags the mask line.

- [ ] **Step 1: Write the failing test**

Create `tests/gui/test_widgets.py`:

```python
import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gemscanner.gui.analysis import analyze_frame
from gemscanner.gui.preview_widget import LivePreviewWidget


def test_preview_widget_accepts_frame_and_mask(qtbot):
    w = LivePreviewWidget()
    qtbot.addWidget(w)
    img = np.full((100, 100), 255, np.uint8)
    img[30:70, 40:60] = 0
    w.set_frame(img, analyze_frame(img))          # must not raise

    w.set_holder_mask_rows(25)
    assert w.holder_mask_rows() == 25

    received = []
    w.maskChanged.connect(received.append)
    w.set_holder_mask_rows(40)
    w.maskChanged.emit(w.holder_mask_rows())       # simulate drag commit
    assert received[-1] == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.preview_widget'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/preview_widget.py`:

```python
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSlider, QHBoxLayout


class LivePreviewWidget(QWidget):
    """Live camera frame with silhouette tint, a draggable holder-mask line,
    a FoV state chip, and min/max/mean stats."""

    maskChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QLabel(alignment=Qt.AlignCenter)
        self._image.setMinimumSize(320, 240)
        self._image.setObjectName("previewImage")
        self._stats = QLabel("—", objectName="statsLabel")
        self._fov = QLabel("no frame", objectName="fovChip")
        self._slider = QSlider(Qt.Vertical)
        self._slider.setRange(0, 100)
        self._slider.valueChanged.connect(self._on_slider)

        row = QHBoxLayout()
        row.addWidget(self._image, 1)
        row.addWidget(self._slider)
        top = QVBoxLayout(self)
        top.addLayout(row, 1)
        info = QHBoxLayout()
        info.addWidget(self._fov)
        info.addWidget(self._stats, 1)
        top.addLayout(info)

        self._img_h = 100
        self._holder = 0

    def holder_mask_rows(self):
        return int(self._holder)

    def set_holder_mask_rows(self, rows):
        self._holder = int(rows)
        self._slider.blockSignals(True)
        self._slider.setValue(int(rows))
        self._slider.blockSignals(False)

    def _on_slider(self, value):
        self._holder = int(value)
        self.maskChanged.emit(self._holder)

    def set_frame(self, frame, analysis):
        gray = frame if frame.ndim == 2 else frame[..., 0]
        h, w = gray.shape
        self._img_h = h
        self._slider.setRange(0, h)
        rgb = np.stack([gray, gray, gray], axis=-1).copy()
        if analysis.mask is not None:
            rgb[analysis.mask, 0] = 220           # red tint on silhouette
            rgb[analysis.mask, 1] = 40
            rgb[analysis.mask, 2] = 40
        if self._holder > 0:
            rgb[h - self._holder:, :, :] = (rgb[h - self._holder:, :, :] * 0.35).astype(np.uint8)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self._image.setPixmap(QPixmap.fromImage(qimg).scaled(
            self._image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        ok = analysis.bbox is not None and not analysis.touches_border
        self._fov.setText("ready" if ok else ("clips border" if analysis.touches_border else "no gem"))
        self._fov.setProperty("state", "ok" if ok else "warn")
        self._fov.style().unpolish(self._fov)
        self._fov.style().polish(self._fov)
        self._stats.setText(
            f"min {analysis.min}  max {analysis.max}  mean {analysis.mean:.1f}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/preview_widget.py tests/gui/test_widgets.py
git commit -m "feat(gui): LivePreviewWidget with silhouette tint and holder-mask line"
```

---

## Task 8: `QueuePanel` and `WizardPanel`

**Files:**
- Create: `gemscanner/gui/queue_panel.py`
- Create: `gemscanner/gui/wizard_panel.py`
- Test: `tests/gui/test_widgets.py` (add tests)

**Interfaces:**
- Consumes: `GemJob`, `Project` (Task 1).
- Produces:
  - `QueuePanel(QWidget)`: `set_gems(list[GemJob])`, `gems() -> list[GemJob]`, `add_gem(GemJob)`, `current_index() -> int`, `select(index)`, signal `gemSelected(int)`.
  - `WizardPanel(QWidget)`: `set_step(index: int)`, `step() -> int`, signals `mountConfirmed()`, `calibrateRequested()`, `scanRequested()`, `reconstructRequested()`, `nextGemRequested()`. Steps: 0 Mount, 1 Align, 2 Holder mask, 3 Calibrate, 4 Scan, 5 Reconstruct, 6 Advance.

- [ ] **Step 1: Write the failing tests**

Add to `tests/gui/test_widgets.py`:

```python
from gemscanner.gui.project import GemJob
from gemscanner.gui.queue_panel import QueuePanel
from gemscanner.gui.wizard_panel import WizardPanel


def test_queue_panel_add_and_select(qtbot):
    q = QueuePanel()
    qtbot.addWidget(q)
    q.set_gems([GemJob(name="ruby-01"), GemJob(name="emerald-02")])
    assert [g.name for g in q.gems()] == ["ruby-01", "emerald-02"]
    q.add_gem(GemJob(name="sapphire-03"))
    assert len(q.gems()) == 3

    seen = []
    q.gemSelected.connect(seen.append)
    q.select(2)
    assert q.current_index() == 2
    assert seen[-1] == 2


def test_wizard_panel_steps_and_signals(qtbot):
    w = WizardPanel()
    qtbot.addWidget(w)
    w.set_step(3)
    assert w.step() == 3
    fired = []
    w.calibrateRequested.connect(lambda: fired.append("cal"))
    w.calibrateRequested.emit()
    assert fired == ["cal"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v -k "queue or wizard"`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.queue_panel'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/queue_panel.py`:

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel


class QueuePanel(QWidget):
    """Ordered list of gems to scan."""

    gemSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gems = []
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Scan queue", objectName="panelTitle"))
        layout.addWidget(self._list, 1)

    def set_gems(self, gems):
        self._gems = list(gems)
        self._list.clear()
        for g in self._gems:
            self._list.addItem(QListWidgetItem(g.name))

    def gems(self):
        return list(self._gems)

    def add_gem(self, gem):
        self._gems.append(gem)
        self._list.addItem(QListWidgetItem(gem.name))

    def current_index(self):
        return self._list.currentRow()

    def select(self, index):
        self._list.setCurrentRow(index)

    def _on_row(self, row):
        if row >= 0:
            self.gemSelected.emit(row)
```

Create `gemscanner/gui/wizard_panel.py`:

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QProgressBar)

STEPS = ["Mount gem", "Align lighting", "Holder mask",
         "Calibrate axis", "Scan", "Reconstruct", "Next gem"]


class WizardPanel(QWidget):
    """The per-gem guided step sequence."""

    mountConfirmed = Signal()
    calibrateRequested = Signal()
    scanRequested = Signal()
    reconstructRequested = Signal()
    nextGemRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self._heading = QLabel(objectName="panelTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        buttons = QHBoxLayout()
        self._btn_mount = QPushButton("Mounted")
        self._btn_cal = QPushButton("Calibrate axis")
        self._btn_scan = QPushButton("Scan")
        self._btn_recon = QPushButton("Reconstruct")
        self._btn_next = QPushButton("Next gem")
        self._btn_mount.clicked.connect(self.mountConfirmed)
        self._btn_cal.clicked.connect(self.calibrateRequested)
        self._btn_scan.clicked.connect(self.scanRequested)
        self._btn_recon.clicked.connect(self.reconstructRequested)
        self._btn_next.clicked.connect(self.nextGemRequested)
        for b in (self._btn_mount, self._btn_cal, self._btn_scan,
                  self._btn_recon, self._btn_next):
            buttons.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addWidget(self._heading)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        self.set_step(0)

    def step(self):
        return self._step

    def set_step(self, index):
        self._step = int(index)
        self._heading.setText(f"Step {self._step + 1}/{len(STEPS)} — {STEPS[self._step]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: PASS (all widget tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/queue_panel.py gemscanner/gui/wizard_panel.py tests/gui/test_widgets.py
git commit -m "feat(gui): QueuePanel and WizardPanel for the guided batch flow"
```

---

## Task 9: `MainWindow`, dark-theme QSS, app entry, and CLI `gui` command

**Files:**
- Create: `gemscanner/gui/style.qss`
- Create: `gemscanner/gui/main_window.py`
- Create: `gemscanner/gui/app.py`
- Modify: `gemscanner/cli.py:20-42` (add the `gui` subcommand)
- Test: `tests/gui/test_widgets.py` (add a MainWindow smoke test)

**Interfaces:**
- Consumes: `Project` (Task 1), `ScanSession` (Task 5), `HardwareWorker` (Task 6), `LivePreviewWidget` (Task 7), `QueuePanel`/`WizardPanel` (Task 8).
- Produces:
  - `MainWindow(project: Project, session: ScanSession)` — wires the worker to the panels.
  - `gemscanner.gui.app.main(argv=None) -> int` — builds `QApplication`, loads QSS, shows the window.
  - CLI: `gemscanner gui -p project.yaml` routes to `app.main`.

- [ ] **Step 1: Write the failing test**

Add to `tests/gui/test_widgets.py`:

```python
from gemscanner.config import ScannerConfig
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.gui.session import ScanSession
from gemscanner.gui.project import Project, GemJob
from gemscanner.gui.main_window import MainWindow


def test_main_window_builds_and_shows_gems(qtbot):
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=200, height=200)
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=stage)
    project = Project(gems=[GemJob(name="ruby-01"), GemJob(name="emerald-02")])
    win = MainWindow(project, session)
    qtbot.addWidget(win)
    assert [g.name for g in win.queue.gems()] == ["ruby-01", "emerald-02"]
    win.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v -k main_window`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.main_window'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/style.qss` (dark-theme minimalism):

```css
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: #e6e6e6; }
QWidget { background: #14161a; }
QLabel#panelTitle { font-size: 15px; font-weight: 600; color: #f2f2f2; padding: 6px 0; }
QLabel#statsLabel { font-family: "Cascadia Mono", "Consolas", monospace; color: #9aa0a6; }
QLabel#previewImage { background: #060708; border-radius: 6px; }
QLabel#fovChip { padding: 3px 10px; border-radius: 10px; background: #23262c; }
QLabel#fovChip[state="ok"] { background: #16351f; color: #4ade80; }
QLabel#fovChip[state="warn"] { background: #3a1d1d; color: #f87171; }
QPushButton {
    background: #23262c; border: none; border-radius: 6px; padding: 8px 14px; color: #e6e6e6;
}
QPushButton:hover { background: #2c3038; }
QPushButton:default { background: #2f6feb; color: #ffffff; }
QPushButton:disabled { color: #5c6169; }
QListWidget { background: #0f1114; border: none; border-radius: 6px; padding: 4px; }
QListWidget::item:selected { background: #2f6feb; border-radius: 4px; }
QProgressBar { background: #0f1114; border: none; border-radius: 6px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #2f6feb; border-radius: 6px; }
QSlider::groove:vertical { width: 4px; background: #23262c; border-radius: 2px; }
QSlider::handle:vertical { height: 16px; background: #2f6feb; border-radius: 4px; margin: 0 -6px; }
```

Create `gemscanner/gui/main_window.py`:

```python
import os
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QMessageBox
from gemscanner.acquisition.scan_controller import ScanParams
from gemscanner.gui.preview_widget import LivePreviewWidget
from gemscanner.gui.queue_panel import QueuePanel
from gemscanner.gui.wizard_panel import WizardPanel
from gemscanner.gui.worker import HardwareWorker


class MainWindow(QMainWindow):
    def __init__(self, project, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GemScanner")
        self.project = project
        self.session = session
        self.worker = HardwareWorker(session)

        self.preview = LivePreviewWidget()
        self.queue = QueuePanel()
        self.wizard = WizardPanel()
        self.queue.set_gems(project.gems)

        central = QWidget()
        root = QHBoxLayout(central)
        left = QVBoxLayout()
        left.addWidget(self.wizard)
        left.addWidget(self.queue, 1)
        root.addLayout(left, 0)
        root.addWidget(self.preview, 1)
        self.setCentralWidget(central)

        # wiring
        self.preview.maskChanged.connect(self._on_mask_changed)
        self.queue.gemSelected.connect(self._on_gem_selected)
        self.wizard.calibrateRequested.connect(lambda: self.worker.post("calibrate", n_probe=12))
        self.wizard.scanRequested.connect(self._start_scan)
        self.wizard.reconstructRequested.connect(self._start_reconstruct)
        self.worker.frameReady.connect(self.preview.set_frame)
        self.worker.progress.connect(self._on_progress)
        self.worker.result.connect(self._on_result)
        self.worker.failed.connect(self._on_failed)

        self._current = 0
        if project.gems:
            self.queue.select(0)
        self.worker.start()
        self.worker.set_view(None, self.preview.holder_mask_rows())
        self.worker.start_preview()

    # ---- slots ----
    def _current_gem(self):
        gems = self.project.gems
        return gems[self._current] if gems else None

    def _on_mask_changed(self, rows):
        self.worker.set_view(None, rows)
        gem = self._current_gem()
        if gem is not None:
            gem.holder_mask_rows = rows

    def _on_gem_selected(self, index):
        self._current = index
        gem = self._current_gem()
        if gem is not None:
            self.preview.set_holder_mask_rows(gem.holder_mask_rows)

    def _start_scan(self):
        gem = self._current_gem()
        if gem is None:
            return
        params = ScanParams(n_views=180, mm_per_px=self.project.mm_per_px,
                            axis_column=gem.axis_column)
        out = gem.out or os.path.join("scans", gem.name)
        self.worker.post("scan", out_dir=out, params=params)

    def _start_reconstruct(self):
        gem = self._current_gem()
        if gem is None:
            return
        out = gem.out or os.path.join("scans", gem.name)
        self.worker.post("reconstruct", out_dir=out,
                         holder_mask_rows=gem.holder_mask_rows, smooth=10)

    def _on_progress(self, op, done, total):
        self.wizard.progress.setValue(int(done * 100 / max(total, 1)))

    def _on_result(self, op, payload):
        gem = self._current_gem()
        if op == "calibrate" and gem is not None:
            gem.axis_column = payload[0]
        elif op == "reconstruct":
            watertight, extents = payload
            QMessageBox.information(self, "Reconstruct",
                                    f"watertight={watertight}\nextents={extents}")
        self.worker.set_view(None, self.preview.holder_mask_rows())
        self.worker.start_preview()

    def _on_failed(self, op, message):
        QMessageBox.warning(self, f"{op} failed", message)
        self.worker.start_preview()

    def closeEvent(self, event):
        self.worker.shutdown()
        self.worker.wait(3000)
        super().closeEvent(event)
```

Create `gemscanner/gui/app.py`:

```python
import os
import sys
from PySide6.QtWidgets import QApplication
from gemscanner.gui.project import Project
from gemscanner.gui.session import ScanSession
from gemscanner.gui.main_window import MainWindow

_STYLE = os.path.join(os.path.dirname(__file__), "style.qss")


def main(argv=None):
    argv = list(sys.argv if argv is None else [sys.argv[0], *argv])
    project_path = "project.yaml"
    if "-p" in argv:
        project_path = argv[argv.index("-p") + 1]
    project = Project.load(project_path)
    config = project.to_scanner_config(project.gems[0]) if project.gems else \
        project.to_scanner_config_default()
    session = ScanSession(config)
    session.configure_stage(project.steps_per_rev)

    app = QApplication.instance() or QApplication(argv)
    if os.path.exists(_STYLE):
        with open(_STYLE, encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    win = MainWindow(project, session)
    win.resize(1100, 720)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

Add `to_scanner_config_default` to `gemscanner/gui/project.py` (empty-queue fallback used by `app.main`):

```python
    def to_scanner_config_default(self):
        return self.to_scanner_config(GemJob(name="_", out=""))
```

Add the `gui` subcommand to `gemscanner/cli.py`. After the `scan` subparser block (line 24), add:

```python
    g = sub.add_parser("gui")
    g.add_argument("-p", "--project", default="project.yaml")
```

And in the dispatch section (before `return 1`), add:

```python
    if args.cmd == "gui":
        from gemscanner.gui.app import main as gui_main
        return gui_main(["-p", args.project])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: PASS (all widget + main-window tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — the original 53 + all new tests (~65+), no failures.

- [ ] **Step 6: Commit**

```bash
git add gemscanner/gui/style.qss gemscanner/gui/main_window.py gemscanner/gui/app.py gemscanner/gui/project.py gemscanner/cli.py tests/gui/test_widgets.py
git commit -m "feat(gui): MainWindow, dark QSS, app entry, and gui CLI command"
```

---

## Task 10: Manual bench smoke + docs

**Files:**
- Modify: `docs/usage.md` (add a GUI section)
- Create: `project.example.yaml`

**Interfaces:** none (documentation + example project file).

- [ ] **Step 1: Create the example project file**

Create `project.example.yaml`:

```yaml
camera_backend: gentl
camera:
  cti_path: C:\Program Files\Baumer Camera Explorer\bgapi2_gige.cti
  exposure_us: 500
  gain: 5
  pixel_format: Mono8
serial_port: COM3
serial_baud: 115200
mm_per_px: 0.0170
steps_per_rev: 90000
calibration_path: calibration.json
gems:
  - name: ruby-01
    holder_mask_rows: 660
    axis_column: 1214.0
    out: scans/ruby-01
  - name: emerald-02
    holder_mask_rows: 705
    axis_column: 1216.0
    out: scans/emerald-02
```

- [ ] **Step 2: Document the GUI**

Add a section to `docs/usage.md`:

```markdown
## GUI

Launch the guided GUI (dark theme; live preview + per-gem wizard + batch queue):

    .venv/Scripts/python.exe -m gemscanner.cli gui -p project.example.yaml

Per gem: mount → align (exposure/gain + silhouette overlay, aim for gem `min≈0`
on a bright background) → drag the holder-mask line to the gem/pedestal junction →
Calibrate axis → Scan → Reconstruct. Then select the next gem in the queue and
repeat. Close Camera Explorer (`bexplorer`) first — only one app can hold the GigE camera.
```

- [ ] **Step 3: Manual bench smoke (operator, on the rig)**

This step is a manual checklist — no automated test. With the rig connected and `bexplorer` closed:

1. `.venv/Scripts/python.exe -m gemscanner.cli gui -p project.example.yaml`
2. Confirm the live preview shows the backlit frame and the stats read `min≈0` on the mounted gem.
3. Drag the holder-mask line; confirm the greyed region and that `min/max/mean` update.
4. Click **Calibrate axis**; confirm the progress bar advances and no error dialog appears.
5. Click **Scan** then **Reconstruct**; confirm the watertight dialog reports extents within ~1% of calipers.

Record the result in the roadmap memory.

- [ ] **Step 4: Commit**

```bash
git add docs/usage.md project.example.yaml
git commit -m "docs(gui): usage section and example project file"
```

---

## Self-Review Notes

- **Spec coverage:** §2a service layer → Tasks 2/3/5; §2b project model → Task 1; §2c widgets → Tasks 7/8/9; §3 threading (single HardwareWorker, polled preview, cancel) → Tasks 4/6; §4 refactor (probe_axis + ScanController hooks) → Tasks 3/4; §5 wizard flow → Tasks 8/9; §6 persistence → Task 1; §7 error handling → Task 6 (`failed` signal) + Task 9 (dialogs); §8 testing → every task headless + Qt importorskip; §9 deps → Task 6; visual style (dark QSS) → Task 9.
- **Live FoV vs prescan:** the live preview uses a cheap single-frame border test (`analyze_frame.touches_border`); the full rotational eccentricity `prescan_fov_check` runs as part of the scan path — documented in Task 2 and the design spec §2c.
- **Camera open/close discipline:** the worker closes the preview camera before every queued op (`_pause_preview`), so the existing `with camera:` blocks inside `probe_axis`/`ScanController`/`prescan` never overlap the live grab loop.
- **Type consistency:** `holder_mask_rows` (int), `axis_column` (float), `mm_per_px` (float), `FrameAnalysis` fields, and worker signal signatures are used identically across Tasks 1–9.
