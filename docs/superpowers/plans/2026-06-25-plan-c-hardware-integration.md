# Plan C — Hardware Integration (PC App) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Python PC application that ties the project together — a camera abstraction, a motion client that speaks the Plan B firmware protocol, a step-and-settle `ScanController` with a pre-scan FoV/eccentricity check, calibration routines, and a CLI with an Open3D 3D viewer — producing a scan dataset that Plan A reconstructs into a mesh.

**Architecture:** Extends the existing `gemscanner` package (Plan A). Hardware is hidden behind small interfaces so the orchestration is host-testable without a camera or board: a `CameraBackend` (mock / OpenCV / Baumer) and a serial `Transport` (real pyserial / in-process `FakeFirmware` that emulates the Plan B controller). The `ScanController` drives `stage.move_deg → wait READY → camera.grab → save`, writing a Plan A `ScanManifest`; reconstruction reuses `reconstruction.pipeline.reconstruct_dataset`. Pure logic + fakes are unit-tested; real serial, real cameras, and the Open3D window are bench-verified.

**Tech Stack:** Python 3.11+, NumPy, OpenCV, trimesh (Plan A), **pyserial**, **open3d**, **pyyaml** (new). Baumer **neoAPI** is an optional, separately-installed SDK (not on PyPI), imported lazily.

## Global Constraints

- Python **3.11+**, Windows. Build on the existing `gemscanner` package; reuse `storage.ScanManifest`/`ScanDataset`, `vision.extract_silhouette`, `reconstruction.pipeline.reconstruct_dataset`, `storage.mesh_io.export_mesh` — do **not** reimplement them.
- New runtime deps: `pyserial`, `open3d`, `pyyaml`. `neoapi` is **optional** and separately installed (Baumer); `BaumerCamera` imports it lazily so `import gemscanner` works without it.
- The venv is at `.venv`; run everything via `.venv/Scripts/python.exe -m ...` (Windows, Git Bash).
- The motion client MUST speak the **Plan B firmware protocol exactly** (see `firmware/README.md`): line commands `STEP/MOVEDEG/SETV/SETACC/SETSETTLE/SETRES/HOME/STATUS`; a move replies `OK` then `READY` after move+settle; errors are `ERR nores|badarg|unknown`; `STATUS` returns `STATUS angle=… steps=… state=idle v=… a=… settle=… res=…`; **steps-per-360° is set at runtime via `SETRES`** and `MOVEDEG` returns `ERR nores` until it is. The in-process `FakeFirmware` test double emulates this and is the contract.
- **Frames are registered to the calibrated rotation axis and never re-centered** (Plan A constraint), so the manifest carries `axis_column`/`axis_tilt_rad` and `ScanController` does no per-frame cropping.
- Hardware-touching code (real `SerialTransport`, `OpenCvCamera.grab`, `BaumerCamera`, the Open3D window) is **bench-verified**; everything else is host-tested with pytest. Tasks 10–12 require hardware and are marked **BENCH**.

---

### Task 1: Dependencies + configuration

**Files:**
- Modify: `pyproject.toml` (add deps + `gemscanner` console entry point)
- Create: `gemscanner/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `pyyaml`.
- Produces: `ScannerConfig` dataclass (`camera_backend: str`, `camera: dict`, `serial_port: str`, `serial_baud: int = 115200`, `scan: dict`, `calibration_path: str`) with `@classmethod load(path)` and `save(path)` (YAML); `default_config() -> ScannerConfig`.

- [ ] **Step 1: Install new deps and write the failing test**

```bash
.venv/Scripts/python.exe -m pip install pyserial open3d pyyaml
```

```python
# tests/test_config.py
from gemscanner.config import ScannerConfig, default_config

def test_roundtrip(tmp_path):
    c = default_config()
    c.serial_port = "COM7"
    c.scan["n_views"] = 360
    p = tmp_path / "cfg.yaml"
    c.save(p)
    loaded = ScannerConfig.load(p)
    assert loaded.serial_port == "COM7"
    assert loaded.scan["n_views"] == 360
    assert loaded.camera_backend == "mock"

def test_defaults():
    c = default_config()
    assert c.serial_baud == 115200
    assert c.camera_backend in ("mock", "opencv", "baumer")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: gemscanner.config`).

- [ ] **Step 3: Implement**

```python
# gemscanner/config.py
from dataclasses import dataclass, field, asdict
import yaml


@dataclass
class ScannerConfig:
    camera_backend: str = "mock"
    camera: dict = field(default_factory=dict)
    serial_port: str = "COM3"
    serial_baud: int = 115200
    scan: dict = field(default_factory=lambda: {"n_views": 180, "settle_ms": 150})
    calibration_path: str = "calibration.json"

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(asdict(self), f, sort_keys=False)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


def default_config():
    return ScannerConfig()
```

Add to `pyproject.toml` `[project].dependencies`: `"pyserial"`, `"open3d"`, `"pyyaml"`. Add:
```toml
[project.scripts]
gemscanner = "gemscanner.cli:main"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pip install -e . && .venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml gemscanner/config.py tests/test_config.py
git commit -m "feat: scanner config (YAML) and Plan C dependencies"
```

---

### Task 2: Camera backend interface + MockCamera

**Files:**
- Create: `gemscanner/camera/__init__.py`
- Create: `gemscanner/camera/base.py`
- Create: `gemscanner/camera/mock.py`
- Test: `tests/camera/test_mock.py`

**Interfaces:**
- Consumes: nothing (numpy).
- Produces:
  - `CameraBackend` (ABC): `open()`, `close()`, `set_exposure(us: float)`, `grab() -> np.ndarray` (grayscale `uint8`). Context-manager support via `__enter__/__exit__`.
  - `MockCamera(frames=None, frame_provider=None)`: returns successive `frames`, or calls `frame_provider()` per `grab()`. Host-testable stand-in.

- [ ] **Step 1: Write the failing test**

```python
# tests/camera/test_mock.py
import numpy as np
from gemscanner.camera.mock import MockCamera

def test_returns_frames_in_order():
    f0 = np.zeros((4, 4), np.uint8)
    f1 = np.ones((4, 4), np.uint8)
    cam = MockCamera(frames=[f0, f1])
    cam.open()
    assert np.array_equal(cam.grab(), f0)
    assert np.array_equal(cam.grab(), f1)
    cam.close()

def test_frame_provider_called():
    calls = {"n": 0}
    def provider():
        calls["n"] += 1
        return np.full((2, 2), calls["n"], np.uint8)
    cam = MockCamera(frame_provider=provider)
    assert cam.grab()[0, 0] == 1
    assert cam.grab()[0, 0] == 2

def test_context_manager():
    with MockCamera(frames=[np.zeros((2, 2), np.uint8)]) as cam:
        assert cam.grab().shape == (2, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/camera/test_mock.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/camera/__init__.py
```

```python
# gemscanner/camera/base.py
from abc import ABC, abstractmethod


class CameraBackend(ABC):
    @abstractmethod
    def open(self): ...
    @abstractmethod
    def close(self): ...
    @abstractmethod
    def grab(self): ...

    def set_exposure(self, us):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False
```

```python
# gemscanner/camera/mock.py
from gemscanner.camera.base import CameraBackend


class MockCamera(CameraBackend):
    def __init__(self, frames=None, frame_provider=None):
        self._frames = list(frames) if frames is not None else None
        self._provider = frame_provider
        self._i = 0

    def open(self):
        self._i = 0

    def close(self):
        pass

    def grab(self):
        if self._provider is not None:
            return self._provider()
        frame = self._frames[self._i]
        self._i = min(self._i + 1, len(self._frames) - 1)
        return frame
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/camera/test_mock.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/camera/__init__.py gemscanner/camera/base.py gemscanner/camera/mock.py tests/camera/test_mock.py
git commit -m "feat: camera backend interface and MockCamera"
```

---

### Task 3: Serial transport + FakeFirmware test double

**Files:**
- Create: `gemscanner/motion/__init__.py`
- Create: `gemscanner/motion/transport.py`
- Create: `gemscanner/motion/fake_firmware.py`
- Test: `tests/motion/test_fake_firmware.py`

**Interfaces:**
- Consumes: `pyserial` (only in `SerialTransport`).
- Produces:
  - `Transport` (Protocol/ABC): `write_line(s: str)`, `read_line(timeout: float | None = None) -> str | None`, `close()`.
  - `SerialTransport(port, baud=115200, timeout=2.0)` — pyserial-backed (bench).
  - `FakeFirmware()` — in-process `Transport` that emulates the Plan B controller: tracks `pos_steps`, `steps_per_rev`, `v/a/settle`; on a written command queues the exact reply lines (`OK` then `READY` for moves; `ERR nores` for `MOVEDEG` before `SETRES`; `STATUS …`; `ERR badarg`/`ERR unknown`). `read_line` pops queued replies.

- [ ] **Step 1: Write the failing test**

```python
# tests/motion/test_fake_firmware.py
from gemscanner.motion.fake_firmware import FakeFirmware

def drain(fw):
    out = []
    while True:
        line = fw.read_line(timeout=0)
        if line is None:
            break
        out.append(line)
    return out

def test_step_replies_ok_then_ready():
    fw = FakeFirmware()
    fw.write_line("STEP 100")
    assert drain(fw) == ["OK", "READY"]

def test_movedeg_blocked_until_setres():
    fw = FakeFirmware()
    fw.write_line("MOVEDEG 90")
    assert drain(fw) == ["ERR nores"]
    fw.write_line("SETRES 20000")
    assert drain(fw) == ["OK"]
    fw.write_line("MOVEDEG 90")
    assert drain(fw) == ["OK", "READY"]

def test_status_tracks_position_and_res():
    fw = FakeFirmware()
    fw.write_line("SETRES 20000"); drain(fw)
    fw.write_line("STEP 5000"); drain(fw)
    fw.write_line("STATUS")
    line = drain(fw)[0]
    assert line.startswith("STATUS ")
    assert "steps=5000" in line
    assert "res=20000" in line
    assert "angle=90.000" in line   # 5000/20000*360

def test_unknown_and_badarg():
    fw = FakeFirmware()
    fw.write_line("WIGGLE"); assert drain(fw) == ["ERR unknown"]
    fw.write_line("SETV abc"); assert drain(fw) == ["ERR badarg"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/motion/test_fake_firmware.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/motion/__init__.py
```

```python
# gemscanner/motion/transport.py
class SerialTransport:
    """pyserial-backed transport (bench)."""
    def __init__(self, port, baud=115200, timeout=2.0):
        import serial
        self._ser = serial.Serial(port, baud, timeout=timeout)

    def write_line(self, s):
        self._ser.write((s + "\n").encode("ascii"))

    def read_line(self, timeout=None):
        if timeout is not None:
            self._ser.timeout = timeout
        raw = self._ser.readline()
        if not raw:
            return None
        return raw.decode("ascii", "replace").strip()

    def close(self):
        self._ser.close()
```

```python
# gemscanner/motion/fake_firmware.py
from collections import deque


class FakeFirmware:
    """In-process Transport emulating the Plan B controller protocol."""
    def __init__(self):
        self._out = deque()
        self.pos_steps = 0
        self.steps_per_rev = 0
        self.v, self.a, self.settle = 4000, 20000, 150

    def write_line(self, s):
        parts = s.strip().split()
        if not parts:
            self._out.append("ERR unknown"); return
        verb, args = parts[0].upper(), parts[1:]

        def as_int():
            return int(args[0])

        try:
            if verb == "STEP":
                self.pos_steps += as_int(); self._out += ["OK", "READY"]
            elif verb == "MOVEDEG":
                deg = float(args[0])
                if self.steps_per_rev <= 0:
                    self._out.append("ERR nores")
                else:
                    self.pos_steps += round(deg / 360.0 * self.steps_per_rev)
                    self._out += ["OK", "READY"]
            elif verb == "SETRES":
                n = as_int()
                if n > 0:
                    self.steps_per_rev = n; self._out.append("OK")
                else:
                    self._out.append("ERR badarg")
            elif verb == "SETV":
                self.v = as_int(); self._out.append("OK")
            elif verb == "SETACC":
                self.a = as_int(); self._out.append("OK")
            elif verb == "SETSETTLE":
                self.settle = as_int(); self._out.append("OK")
            elif verb == "HOME":
                self.pos_steps = 0; self._out += ["OK", "READY"]
            elif verb == "STATUS":
                angle = (self.pos_steps / self.steps_per_rev * 360.0) % 360.0 if self.steps_per_rev else 0.0
                self._out.append(
                    f"STATUS angle={angle:.3f} steps={self.pos_steps} state=idle "
                    f"v={self.v} a={self.a} settle={self.settle} res={self.steps_per_rev}")
            else:
                self._out.append("ERR unknown")
        except (ValueError, IndexError):
            self._out.append("ERR badarg")

    def read_line(self, timeout=None):
        return self._out.popleft() if self._out else None

    def close(self):
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/motion/test_fake_firmware.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/motion/__init__.py gemscanner/motion/transport.py gemscanner/motion/fake_firmware.py tests/motion/test_fake_firmware.py
git commit -m "feat: serial transport and FakeFirmware protocol double"
```

---

### Task 4: RotaryStage client

**Files:**
- Create: `gemscanner/motion/stage.py`
- Test: `tests/motion/test_stage.py`

**Interfaces:**
- Consumes: `motion.transport`/`fake_firmware` (any `Transport`).
- Produces:
  - `StageError(Exception)`.
  - `RotaryStage(transport, reply_timeout=2.0, move_timeout=60.0)` with:
    `set_resolution(steps_per_rev)`, `set_speed(v)`, `set_accel(a)`, `set_settle(ms)`,
    `step(microsteps)`, `move_deg(deg)`, `home()`, `status() -> dict`.
    Move methods send the command, require an `OK`, then block for `READY` (up to `move_timeout`). Any `ERR …` raises `StageError`. `status()` parses the `STATUS` line into a dict of typed fields.

- [ ] **Step 1: Write the failing test**

```python
# tests/motion/test_stage.py
import pytest
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage, StageError

def test_step_and_status_roundtrip():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(20000)
    stage.step(5000)
    st = stage.status()
    assert st["steps"] == 5000
    assert st["res"] == 20000
    assert abs(st["angle"] - 90.0) < 1e-6

def test_move_deg_before_setres_raises():
    stage = RotaryStage(FakeFirmware())
    with pytest.raises(StageError):
        stage.move_deg(90)

def test_move_deg_after_setres():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(36000)
    stage.move_deg(45)
    assert stage.status()["steps"] == 4500

def test_home_zeroes():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(20000); stage.step(1234); stage.home()
    assert stage.status()["steps"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/motion/test_stage.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/motion/stage.py
class StageError(Exception):
    pass


class RotaryStage:
    def __init__(self, transport, reply_timeout=2.0, move_timeout=60.0):
        self._t = transport
        self._reply_timeout = reply_timeout
        self._move_timeout = move_timeout

    def _send_ok(self, line, timeout):
        self._t.write_line(line)
        reply = self._t.read_line(timeout=timeout)
        if reply is None:
            raise StageError(f"timeout waiting for reply to {line!r}")
        if reply.startswith("ERR"):
            raise StageError(f"{line!r} -> {reply}")
        if reply != "OK":
            raise StageError(f"{line!r} -> unexpected {reply!r}")

    def _move(self, line):
        self._send_ok(line, self._reply_timeout)
        ready = self._t.read_line(timeout=self._move_timeout)
        if ready != "READY":
            raise StageError(f"{line!r} -> expected READY, got {ready!r}")

    def set_resolution(self, steps_per_rev):
        self._send_ok(f"SETRES {int(steps_per_rev)}", self._reply_timeout)

    def set_speed(self, v):
        self._send_ok(f"SETV {int(v)}", self._reply_timeout)

    def set_accel(self, a):
        self._send_ok(f"SETACC {int(a)}", self._reply_timeout)

    def set_settle(self, ms):
        self._send_ok(f"SETSETTLE {int(ms)}", self._reply_timeout)

    def step(self, microsteps):
        self._move(f"STEP {int(microsteps)}")

    def move_deg(self, deg):
        self._move(f"MOVEDEG {deg}")

    def home(self):
        self._move("HOME")

    def status(self):
        self._t.write_line("STATUS")
        line = self._t.read_line(timeout=self._reply_timeout)
        if not line or not line.startswith("STATUS "):
            raise StageError(f"bad STATUS reply: {line!r}")
        out = {}
        for tok in line[len("STATUS "):].split():
            k, _, v = tok.partition("=")
            if k == "angle":
                out[k] = float(v)
            elif k in ("steps", "v", "a", "settle", "res"):
                out[k] = int(v)
            else:
                out[k] = v
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/motion/test_stage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/motion/stage.py tests/motion/test_stage.py
git commit -m "feat: RotaryStage client speaking the firmware protocol"
```

---

### Task 5: ScanController (step-and-settle)

**Files:**
- Create: `gemscanner/acquisition/__init__.py`
- Create: `gemscanner/acquisition/scan_controller.py`
- Test: `tests/acquisition/test_scan_controller.py`

**Interfaces:**
- Consumes: a `CameraBackend`, a `RotaryStage`, `storage.ScanManifest`, OpenCV (`cv2.imwrite`).
- Produces:
  - `ScanParams(n_views=180, mm_per_px=0.0288, axis_column=0.0, axis_tilt_rad=0.0, eccentricity_mm=None)`.
  - `ScanController(camera, stage)` with `run(out_dir, params) -> str` (returns `out_dir`). Captures `n_views` frames over 360° (frame 0 at the start angle, then `move_deg(360/n_views)` + capture, ×(n_views−1)), writes `out_dir/frames/NNNN.png` and `out_dir/manifest.json` via `ScanManifest`. **No per-frame re-centering.**

- [ ] **Step 1: Write the failing test**

```python
# tests/acquisition/test_scan_controller.py
import os
import numpy as np
from gemscanner.camera.mock import MockCamera
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.storage.dataset import load_dataset

def test_run_writes_dataset(tmp_path):
    counter = {"n": 0}
    def provider():
        counter["n"] += 1
        return np.full((40, 40), counter["n"] % 256, np.uint8)
    cam = MockCamera(frame_provider=provider)
    stage = RotaryStage(FakeFirmware()); stage.set_resolution(36000)
    ctrl = ScanController(cam, stage)
    out = ctrl.run(str(tmp_path / "scan"),
                   ScanParams(n_views=12, mm_per_px=0.05, axis_column=20.0))
    ds = load_dataset(out)
    assert ds.frame_count() == 12
    assert ds.manifest.mm_per_px == 0.05
    assert ds.manifest.axis_column == 20.0
    assert len(ds.manifest.angles_deg) == 12
    assert abs(ds.manifest.angles_deg[1] - 30.0) < 1e-6   # 360/12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_scan_controller.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/acquisition/__init__.py
```

```python
# gemscanner/acquisition/scan_controller.py
import os
from dataclasses import dataclass
import cv2
from gemscanner.storage.manifest import ScanManifest


@dataclass
class ScanParams:
    n_views: int = 180
    mm_per_px: float = 0.0288
    axis_column: float = 0.0
    axis_tilt_rad: float = 0.0
    eccentricity_mm: float = None


class ScanController:
    def __init__(self, camera, stage):
        self.camera = camera
        self.stage = stage

    def run(self, out_dir, params):
        os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
        inc = 360.0 / params.n_views
        angles, files = [], []
        h = w = 0
        with self.camera:
            for i in range(params.n_views):
                if i > 0:
                    self.stage.move_deg(inc)
                frame = self.camera.grab()
                h, w = frame.shape[:2]
                fname = f"{i:04d}.png"
                cv2.imwrite(os.path.join(out_dir, "frames", fname), frame)
                files.append(f"frames/{fname}")
                angles.append(round(i * inc, 6))
        ScanManifest(
            angles_deg=angles, mm_per_px=params.mm_per_px,
            axis_column=params.axis_column, axis_tilt_rad=params.axis_tilt_rad,
            eccentricity_mm=params.eccentricity_mm,
            image_width=w, image_height=h, frame_files=files,
            metadata={"source": "ScanController"},
        ).save(os.path.join(out_dir, "manifest.json"))
        return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_scan_controller.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/acquisition/__init__.py gemscanner/acquisition/scan_controller.py tests/acquisition/test_scan_controller.py
git commit -m "feat: step-and-settle ScanController writing a Plan A dataset"
```

---

### Task 6: Pre-scan FoV / eccentricity check

**Files:**
- Create: `gemscanner/acquisition/prescan.py`
- Test: `tests/acquisition/test_prescan.py`

**Interfaces:**
- Consumes: a `CameraBackend`, a `RotaryStage`, `vision.silhouette.extract_silhouette`, `coords.column_to_projection`.
- Produces:
  - `PrescanResult(ok: bool, offending_angle: float | None, eccentricity_mm: float, touched_border: bool)`.
  - `prescan_fov_check(camera, stage, axis_column, mm_per_px, n_probe=12, threshold=None, margin_px=2) -> PrescanResult`. Rotates through `n_probe` equal steps over 360°, extracts each silhouette, flags clipping if the silhouette's bounding columns/rows come within `margin_px` of any frame border (records the first offending angle), and estimates eccentricity from the half-swing of the silhouette-centroid column about `axis_column` (in mm). Restores the stage to start with a final complementary move.

- [ ] **Step 1: Write the failing test**

```python
# tests/acquisition/test_prescan.py
import numpy as np
from gemscanner.camera.mock import MockCamera
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.acquisition.prescan import prescan_fov_check

def _disc(w, h, cx, r):
    img = np.full((h, w), 255, np.uint8)
    yy, xx = np.ogrid[:h, :w]
    img[(xx - cx) ** 2 + (yy - h // 2) ** 2 <= r * r] = 0
    return img

def test_centered_object_passes():
    frames = [_disc(200, 200, 100, 20) for _ in range(6)]
    cam = MockCamera(frames=frames)
    stage = RotaryStage(FakeFirmware()); stage.set_resolution(36000)
    res = prescan_fov_check(cam, stage, axis_column=100.0, mm_per_px=0.05, n_probe=6)
    assert res.ok and not res.touched_border

def test_object_touching_border_flags():
    frames = [_disc(200, 200, 195, 20)]   # disc runs off the right edge
    cam = MockCamera(frames=frames)
    stage = RotaryStage(FakeFirmware()); stage.set_resolution(36000)
    res = prescan_fov_check(cam, stage, axis_column=100.0, mm_per_px=0.05, n_probe=1)
    assert not res.ok and res.touched_border
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_prescan.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/acquisition/prescan.py
from dataclasses import dataclass
import numpy as np
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.coords import column_to_projection


@dataclass
class PrescanResult:
    ok: bool
    offending_angle: float
    eccentricity_mm: float
    touched_border: bool


def prescan_fov_check(camera, stage, axis_column, mm_per_px,
                      n_probe=12, threshold=None, margin_px=2):
    inc = 360.0 / n_probe
    touched = False
    offending = None
    centroid_cols = []
    with camera:
        for i in range(n_probe):
            if i > 0:
                stage.move_deg(inc)
            mask = extract_silhouette(camera.grab(), threshold)
            ys, xs = np.where(mask)
            if xs.size == 0:
                continue
            h, w = mask.shape
            if (xs.min() <= margin_px or xs.max() >= w - 1 - margin_px or
                    ys.min() <= margin_px or ys.max() >= h - 1 - margin_px):
                touched = True
                if offending is None:
                    offending = round(i * inc, 3)
            centroid_cols.append(xs.mean())
        if n_probe > 1:
            stage.move_deg(inc)   # complete the revolution back to start
    if centroid_cols:
        swing_px = (max(centroid_cols) - min(centroid_cols)) / 2.0
        ecc = abs(column_to_projection(axis_column + swing_px, axis_column, mm_per_px))
    else:
        ecc = 0.0
    return PrescanResult(ok=not touched, offending_angle=offending,
                         eccentricity_mm=ecc, touched_border=touched)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/acquisition/test_prescan.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/acquisition/prescan.py tests/acquisition/test_prescan.py
git commit -m "feat: pre-scan FoV/eccentricity check"
```

---

### Task 7: Calibration math + persistence

**Files:**
- Create: `gemscanner/calibration/__init__.py`
- Create: `gemscanner/calibration/fit.py`
- Create: `gemscanner/calibration/calibration.py`
- Test: `tests/calibration/test_fit.py`
- Test: `tests/calibration/test_calibration.py`

**Interfaces:**
- Consumes: numpy.
- Produces:
  - `fit_rotation_axis(angles_deg, centroid_cols) -> (axis_column, amplitude)` — least-squares fit of `u(θ) = c + a·cosθ + b·sinθ`; returns `c` and `hypot(a, b)`.
  - `mm_per_px_from_gauge(measured_px, known_mm) -> float`.
  - `steps_per_rev_from(motor_steps, microstep, gear_ratio) -> int`.
  - `Calibration` dataclass (`mm_per_px`, `axis_column`, `axis_tilt_rad=0.0`, `steps_per_rev=0`, `eccentricity_mm=None`) with `save(path)`/`load(path)` (JSON).

- [ ] **Step 1: Write the failing tests**

```python
# tests/calibration/test_fit.py
import numpy as np
from gemscanner.calibration.fit import (
    fit_rotation_axis, mm_per_px_from_gauge, steps_per_rev_from)

def test_fit_recovers_axis_and_amplitude():
    angles = np.arange(0, 360, 10.0)
    c, A, phase = 128.5, 7.0, 0.6
    cols = c + A * np.cos(np.radians(angles) - phase)
    axis, amp = fit_rotation_axis(angles, cols)
    assert abs(axis - c) < 1e-6
    assert abs(amp - A) < 1e-6

def test_scale_and_steps():
    assert abs(mm_per_px_from_gauge(200, 10.0) - 0.05) < 1e-9
    assert steps_per_rev_from(500, 10, 18) == 90000
```

```python
# tests/calibration/test_calibration.py
from gemscanner.calibration.calibration import Calibration

def test_roundtrip(tmp_path):
    c = Calibration(mm_per_px=0.0288, axis_column=1223.5, steps_per_rev=90000)
    p = tmp_path / "cal.json"
    c.save(p)
    loaded = Calibration.load(p)
    assert loaded.steps_per_rev == 90000
    assert abs(loaded.mm_per_px - 0.0288) < 1e-12
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/calibration -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/calibration/__init__.py
```

```python
# gemscanner/calibration/fit.py
import numpy as np


def fit_rotation_axis(angles_deg, centroid_cols):
    th = np.radians(np.asarray(angles_deg, float))
    u = np.asarray(centroid_cols, float)
    A = np.column_stack([np.ones_like(th), np.cos(th), np.sin(th)])
    c, a, b = np.linalg.lstsq(A, u, rcond=None)[0]
    return float(c), float(np.hypot(a, b))


def mm_per_px_from_gauge(measured_px, known_mm):
    return known_mm / measured_px


def steps_per_rev_from(motor_steps, microstep, gear_ratio):
    return int(round(motor_steps * microstep * gear_ratio))
```

```python
# gemscanner/calibration/calibration.py
from dataclasses import dataclass, asdict
import json


@dataclass
class Calibration:
    mm_per_px: float
    axis_column: float
    axis_tilt_rad: float = 0.0
    steps_per_rev: int = 0
    eccentricity_mm: float = None

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(**json.load(f))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/calibration -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/calibration tests/calibration
git commit -m "feat: calibration math (axis fit, scale, steps-per-rev) and persistence"
```

---

### Task 8: CLI + Open3D viewer

**Files:**
- Create: `gemscanner/viewer.py`
- Create: `gemscanner/cli.py`
- Test: `tests/test_viewer.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `open3d`, `trimesh`, `reconstruction.pipeline.reconstruct_dataset`, `storage.mesh_io.export_mesh`.
- Produces:
  - `viewer.trimesh_to_open3d(mesh) -> o3d.geometry.TriangleMesh` (headless-constructible); `viewer.show_mesh(mesh_or_path)` (opens a window — bench).
  - `cli.main(argv=None) -> int` with subcommands: `reconstruct <dataset> -o <mesh>` (host), `view <mesh>` (bench window), `scan -c <config>` / `calibrate` (bench).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_viewer.py
import trimesh
from gemscanner.viewer import trimesh_to_open3d

def test_conversion_preserves_counts():
    box = trimesh.creation.box(extents=(2, 2, 2))
    o3d_mesh = trimesh_to_open3d(box)
    assert len(o3d_mesh.vertices) == len(box.vertices)
    assert len(o3d_mesh.triangles) == len(box.faces)
```

```python
# tests/test_cli.py
import os
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.cli import main

def test_reconstruct_subcommand(tmp_path):
    ds = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                 n_views=60, mm_per_px=0.05, width=200, height=200)
    out = tmp_path / "gem.stl"
    rc = main(["reconstruct", ds, "-o", str(out)])
    assert rc == 0
    assert os.path.exists(out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_viewer.py tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/viewer.py
import numpy as np


def trimesh_to_open3d(mesh):
    import open3d as o3d
    m = o3d.geometry.TriangleMesh()
    m.vertices = o3d.utility.Vector3dVector(np.asarray(mesh.vertices, float))
    m.triangles = o3d.utility.Vector3iVector(np.asarray(mesh.faces, np.int32))
    m.compute_vertex_normals()
    return m


def show_mesh(mesh_or_path):
    import trimesh
    import open3d as o3d
    mesh = mesh_or_path if hasattr(mesh_or_path, "vertices") else trimesh.load(mesh_or_path)
    o3d.visualization.draw_geometries([trimesh_to_open3d(mesh)])
```

```python
# gemscanner/cli.py
import argparse
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def main(argv=None):
    p = argparse.ArgumentParser(prog="gemscanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconstruct")
    r.add_argument("dataset")
    r.add_argument("-o", "--out", required=True)

    v = sub.add_parser("view")
    v.add_argument("mesh")

    s = sub.add_parser("scan")
    s.add_argument("-c", "--config", required=True)
    s.add_argument("-o", "--out", required=True)

    args = p.parse_args(argv)

    if args.cmd == "reconstruct":
        mesh = reconstruct_dataset(args.dataset)
        export_mesh(mesh, args.out)
        print(f"wrote {args.out}: watertight={mesh.is_watertight}")
        return 0
    if args.cmd == "view":
        from gemscanner.viewer import show_mesh
        show_mesh(args.mesh)
        return 0
    if args.cmd == "scan":
        from gemscanner.run_scan import run_scan_from_config   # Task 12
        return run_scan_from_config(args.config, args.out)
    return 1
```

> Note: `gemscanner.run_scan` is created in Task 12 (bench wiring). The `scan` branch imports it lazily so `reconstruct`/`view` work before Task 12 exists.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_viewer.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/viewer.py gemscanner/cli.py tests/test_viewer.py tests/test_cli.py
git commit -m "feat: CLI (reconstruct/view/scan) and Open3D viewer"
```

---

### Task 9: End-to-end mock integration (scan → reconstruct)

**Files:**
- Create: `gemscanner/testing/scene_camera.py`
- Test: `tests/test_end_to_end_scan.py`

**Interfaces:**
- Consumes: `motion.fake_firmware.FakeFirmware`, `motion.stage.RotaryStage`, `acquisition.scan_controller`, `reconstruction.pipeline.reconstruct_dataset`, the Plan A ellipsoid projection math.
- Produces: `SceneCamera(stage_fw, rx, ry, rz, mm_per_px, width, height, center_offset=(0,0))` — a `CameraBackend` whose `grab()` renders the orthographic silhouette of a fixed ellipsoid **at the FakeFirmware's current angle** (`pos_steps / steps_per_rev`), so a `ScanController` run produces a physically-consistent silhouette stack.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_end_to_end_scan.py
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.reconstruction.pipeline import reconstruct_dataset

def test_mock_scan_reconstructs_ellipsoid(tmp_path):
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    stage.set_resolution(36000)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=400, height=400)
    params = ScanParams(n_views=180, mm_per_px=0.05, axis_column=(400 - 1) / 2.0)
    out = ScanController(cam, stage).run(str(tmp_path / "scan"), params)
    mesh = reconstruct_dataset(out)
    ext = mesh.bounding_box.extents
    assert mesh.is_watertight
    assert abs(ext[0] - 8.0) < 0.4 and abs(ext[1] - 6.0) < 0.4 and abs(ext[2] - 10.0) < 0.4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_end_to_end_scan.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/testing/scene_camera.py
import math
import numpy as np
from gemscanner.camera.base import CameraBackend
from gemscanner.coords import projection_to_column


class SceneCamera(CameraBackend):
    """Renders the orthographic silhouette of an ellipsoid at the firmware's
    current rotation angle. Test double linking motion to imaging."""
    def __init__(self, stage_fw, rx, ry, rz, mm_per_px, width, height,
                 center_offset=(0.0, 0.0)):
        self._fw = stage_fw
        self.rx, self.ry, self.rz = rx, ry, rz
        self.mm_per_px = mm_per_px
        self.width, self.height = width, height
        self.cx, self.cy = center_offset
        self.axis_column = (width - 1) / 2.0
        self.v0 = (height - 1) / 2.0

    def open(self): pass
    def close(self): pass

    def _angle_rad(self):
        spr = self._fw.steps_per_rev or 1
        return math.radians(self._fw.pos_steps / spr * 360.0)

    def grab(self):
        th = self._angle_rad()
        img = np.full((self.height, self.width), 255, np.uint8)
        p_c = self.cx * math.cos(th) - self.cy * math.sin(th)
        for v in range(self.height):
            z = (self.v0 - v) * self.mm_per_px
            if abs(z) >= self.rz:
                continue
            s = math.sqrt(max(0.0, 1.0 - (z / self.rz) ** 2))
            half = s * math.sqrt((self.rx * math.cos(th)) ** 2 + (self.ry * math.sin(th)) ** 2)
            left = projection_to_column(p_c - half, self.axis_column, self.mm_per_px)
            right = projection_to_column(p_c + half, self.axis_column, self.mm_per_px)
            lo = max(0, int(math.ceil(left)))
            hi = min(self.width - 1, int(math.floor(right)))
            if hi >= lo:
                img[v, lo:hi + 1] = 0
        return img
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_end_to_end_scan.py -v`
Expected: PASS. Then run the whole suite: `.venv/Scripts/python.exe -m pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/testing/scene_camera.py tests/test_end_to_end_scan.py
git commit -m "test: end-to-end mock scan -> reconstruct integration"
```

---

### Task 10: OpenCV camera backend + factory (BENCH for grab)

**Files:**
- Create: `gemscanner/camera/opencv_camera.py`
- Create: `gemscanner/camera/factory.py`
- Test: `tests/camera/test_factory.py`

**Interfaces:**
- Consumes: `cv2`, `config.ScannerConfig`.
- Produces:
  - `OpenCvCamera(index=0, exposure=None)` — `open()` opens `cv2.VideoCapture(index)`, `grab()` reads a frame and returns it as grayscale, raises `RuntimeError` on failure.
  - `create_camera(config) -> CameraBackend` — returns `MockCamera`/`OpenCvCamera`/`BaumerCamera` per `config.camera_backend`.

- [ ] **Step 1: Write the failing test (factory selection — host)**

```python
# tests/camera/test_factory.py
from gemscanner.config import ScannerConfig
from gemscanner.camera.factory import create_camera
from gemscanner.camera.mock import MockCamera

def test_factory_mock():
    cam = create_camera(ScannerConfig(camera_backend="mock",
                                      camera={"frames": []}))
    assert isinstance(cam, MockCamera)

def test_factory_opencv_type_without_opening():
    cam = create_camera(ScannerConfig(camera_backend="opencv",
                                      camera={"index": 0}))
    assert cam.__class__.__name__ == "OpenCvCamera"   # not opened, no device needed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/camera/test_factory.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# gemscanner/camera/opencv_camera.py
import cv2
from gemscanner.camera.base import CameraBackend


class OpenCvCamera(CameraBackend):
    def __init__(self, index=0, exposure=None):
        self.index = index
        self.exposure = exposure
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera index {self.index}")
        if self.exposure is not None:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def grab(self):
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("frame grab failed")
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame
```

```python
# gemscanner/camera/factory.py
from gemscanner.camera.mock import MockCamera


def create_camera(config):
    backend = config.camera_backend
    cam = config.camera or {}
    if backend == "mock":
        return MockCamera(frames=cam.get("frames"))
    if backend == "opencv":
        from gemscanner.camera.opencv_camera import OpenCvCamera
        return OpenCvCamera(index=cam.get("index", 0), exposure=cam.get("exposure"))
    if backend == "baumer":
        from gemscanner.camera.baumer_camera import BaumerCamera
        return BaumerCamera(**{k: v for k, v in cam.items()})
    raise ValueError(f"unknown camera_backend {backend!r}")
```

- [ ] **Step 4: Run test (host) to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/camera/test_factory.py -v`
Expected: PASS.

- [ ] **Step 5: Bench verification (USB webcam)**

With any USB webcam connected:
```python
from gemscanner.camera.opencv_camera import OpenCvCamera
with OpenCvCamera(0) as c:
    f = c.grab(); print(f.shape, f.dtype)
```
Expect a 2-D `uint8` grayscale frame.

- [ ] **Step 6: Commit**

```bash
git add gemscanner/camera/opencv_camera.py gemscanner/camera/factory.py tests/camera/test_factory.py
git commit -m "feat: OpenCV camera backend and camera factory"
```

---

### Task 11: Baumer camera backend (BENCH)

> **BENCH FINDING (2026-06-28): the EXG50 needs the GenTL/Harvesters path, NOT neoAPI.**
> neoAPI only supports Baumer's newer CX/X families. Connecting it to the legacy
> EXG50 yields a stripped GigE-Vision fallback node map (~54 features, `Gain`/auto
> throw `FeatureAccessException`) and the real sensor streams flat black (only the
> on-camera test image streams). The EXG50's native SDK is GAPI/bgapi2 — what Camera
> Explorer uses. The working Python path is **Harvesters + Baumer's `bgapi2_gige.cti`
> GenTL producer** (`C:\Program Files\Baumer Camera Explorer\bgapi2_gige.cti`), which
> exposes the real node map. That camera uses **legacy node names**: `ExposureTimeAbs`
> (µs), `GainAbs`/`GainRaw`/`GainSelector`, `TestImageSelector` (no `ExposureAuto`/
> `GainAuto`). Network prereq: camera + NIC on the same subnet (set a Persistent IP),
> and disable VPN/Hyper-V virtual adapters that break GigE discovery.

**Files:**
- Create: `gemscanner/camera/gentl_camera.py` (primary — `GenTLCamera`, Harvesters + .cti).
- Create: `gemscanner/camera/baumer_camera.py` (neoAPI; kept for CX-series cameras only).

**Interfaces:**
- `GenTLCamera(cti_path, index=0, serial=None, exposure_us=None, gain=None, pixel_format="Mono8", fetch_timeout=5.0)` implementing `CameraBackend`; `open()` loads the `.cti` via Harvesters, creates the image acquirer, forces `TestImageSelector/TestPattern=Off`, sets pixel format/exposure/gain (modern→legacy node-name fallback), and starts acquisition; `grab()` fetches a buffer and returns a `uint8` 2-D array, **raising on an all-zero frame**. Harvesters imported lazily. Factory backend key: `gentl` (config carries `cti_path`, `exposure_us`, `gain`, `serial`, `pixel_format`). `harvesters` added to deps.
- `BaumerCamera(serial=None, exposure_us=None, pixel_format="Mono8")` (neoAPI) implementing `CameraBackend`; lazy `neoapi` import. Use only for cameras neoAPI supports.

- [ ] **Step 1: Implement**

```python
# gemscanner/camera/baumer_camera.py
import numpy as np
from gemscanner.camera.base import CameraBackend


class BaumerCamera(CameraBackend):
    def __init__(self, serial=None, exposure_us=None, pixel_format="Mono8"):
        self.serial = serial
        self.exposure_us = exposure_us
        self.pixel_format = pixel_format
        self._cam = None

    def open(self):
        import neoapi
        self._cam = neoapi.Cam()
        self._cam.Connect(self.serial) if self.serial else self._cam.Connect()
        self._cam.f.PixelFormat.SetString(self.pixel_format)
        if self.exposure_us is not None:
            self._cam.f.ExposureTime.Set(float(self.exposure_us))

    def set_exposure(self, us):
        if self._cam is not None:
            self._cam.f.ExposureTime.Set(float(us))

    def close(self):
        if self._cam is not None:
            self._cam.Disconnect()
            self._cam = None

    def grab(self):
        img = self._cam.GetImage()
        arr = img.GetNPArray()
        if arr.ndim == 3:
            arr = arr[..., 0]
        return np.ascontiguousarray(arr, dtype=np.uint8)
```

- [ ] **Step 2: Bench verification (Baumer EXG50 + neoAPI installed)**

Install Baumer neoAPI Python wheel, then with the EXG50 connected (GigE):
```python
from gemscanner.camera.baumer_camera import BaumerCamera
with BaumerCamera(exposure_us=5000) as c:
    f = c.grab(); print(f.shape, f.dtype, f.min(), f.max())
```
Expect a full-resolution `uint8` grayscale frame; confirm the backlit gem shows as dark on bright.

- [ ] **Step 3: Commit**

```bash
git add gemscanner/camera/baumer_camera.py
git commit -m "feat: Baumer neoAPI camera backend (lazy import)"
```

---

### Task 12: Bench integration — calibrate, scan, reconstruct, view (BENCH)

**Files:**
- Create: `gemscanner/run_scan.py`
- Create: `config.example.yaml`
- Modify: `README.md` (project-level usage section)

**Interfaces:**
- Consumes: everything above — `config`, `camera.factory`, `motion.transport.SerialTransport`, `motion.stage.RotaryStage`, `calibration`, `acquisition.scan_controller`, `acquisition.prescan`, `reconstruction.pipeline`.
- Produces: `run_scan_from_config(config_path, out_dir) -> int` — opens the camera + serial stage, loads `Calibration`, pushes `SETRES`/speed/settle to the firmware, runs the pre-scan FoV check (abort on clip), runs the `ScanController`, reconstructs, and exports `out_dir/gem.stl`. Wired to the CLI `scan` subcommand (Task 8).

- [ ] **Step 1: Implement the bench wiring**

```python
# gemscanner/run_scan.py
import os
from gemscanner.config import ScannerConfig
from gemscanner.camera.factory import create_camera
from gemscanner.motion.transport import SerialTransport
from gemscanner.motion.stage import RotaryStage
from gemscanner.calibration.calibration import Calibration
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.acquisition.prescan import prescan_fov_check
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def run_scan_from_config(config_path, out_dir):
    cfg = ScannerConfig.load(config_path)
    cal = Calibration.load(cfg.calibration_path)
    cam = create_camera(cfg)
    stage = RotaryStage(SerialTransport(cfg.serial_port, cfg.serial_baud))
    stage.set_resolution(cal.steps_per_rev)
    stage.set_settle(cfg.scan.get("settle_ms", 150))

    pre = prescan_fov_check(cam, stage, cal.axis_column, cal.mm_per_px)
    if not pre.ok:
        print(f"FoV check FAILED: silhouette clips at {pre.offending_angle}°; re-seat the gem.")
        return 2
    print(f"FoV ok; eccentricity ~ {pre.eccentricity_mm:.3f} mm")

    params = ScanParams(n_views=cfg.scan.get("n_views", 180),
                        mm_per_px=cal.mm_per_px, axis_column=cal.axis_column,
                        axis_tilt_rad=cal.axis_tilt_rad,
                        eccentricity_mm=pre.eccentricity_mm)
    ScanController(cam, stage).run(out_dir, params)
    mesh = reconstruct_dataset(out_dir)
    out_mesh = os.path.join(out_dir, "gem.stl")
    export_mesh(mesh, out_mesh)
    print(f"wrote {out_mesh}: watertight={mesh.is_watertight}, extents={mesh.bounding_box.extents}")
    return 0
```

```yaml
# config.example.yaml
camera_backend: baumer        # mock | opencv | baumer
camera:
  exposure_us: 5000
serial_port: COM7
serial_baud: 115200
scan:
  n_views: 180
  settle_ms: 150
calibration_path: calibration.json
```

- [ ] **Step 2: Bench verification (full hardware)**

With the EXG50 + collimated backlight, the stage/driver/ESP32 powered, and a `calibration.json` produced from the Task 7 routines (axis column, mm/px, steps-per-rev):
```bash
.venv/Scripts/python.exe -m gemscanner.cli scan -c config.example.yaml -o scans/gem01
.venv/Scripts/python.exe -m gemscanner.cli view scans/gem01/gem.stl
```
Expect: the FoV check passes (or names the clipping angle), the stage steps through 360° capturing frames, a watertight `gem.stl` is written, and the Open3D window shows the reconstructed gem. Compare bounding-box extents against caliper measurements within the calibrated tolerance.

- [ ] **Step 3: Commit**

```bash
git add gemscanner/run_scan.py config.example.yaml README.md
git commit -m "feat: bench scan pipeline (config -> calibrate -> prescan -> scan -> reconstruct -> view)"
```

---

## Self-Review

**Spec coverage (design spec §5 software architecture, §4.4 pre-scan, §7 calibration, §8 phasing):**
- Camera abstraction (`CameraBackend` + Mock/OpenCV/Baumer + factory; Baumer→USB is a config change) → Tasks 2, 10, 11.
- Motion client over serial speaking the Plan B protocol → Tasks 3, 4 (with `FakeFirmware` as the contract/double).
- Step-and-settle `ScanController` writing a Plan A `ScanManifest` → Task 5.
- Pre-scan FoV/eccentricity check (§4.4) → Task 6.
- Calibration (scale, rotation axis, steps-per-360 via `SETRES`, eccentricity) → Tasks 7, 12.
- CLI + Open3D viewer (Phase-1 UI) → Task 8.
- Reuses Plan A reconstruction/storage/vision (no reimplementation); off-center never re-centered (Task 5 note; proven end-to-end in Task 9).
- End-to-end host integration via `SceneCamera` (motion↔imaging↔reconstruction) → Task 9.
- Bench end-to-end (real camera + serial) → Task 12.

**Placeholder scan:** No TBD/TODO. Host tasks (1–9, plus the factory in 10) carry complete code + assertive tests. Hardware tasks (10 grab, 11, 12) carry complete implementation code plus concrete bench procedures, as marked.

**Type/interface consistency:** `CameraBackend.{open,close,grab,set_exposure}` is implemented identically by `MockCamera`, `SceneCamera`, `OpenCvCamera`, `BaumerCamera`. `Transport.{write_line,read_line,close}` is satisfied by `SerialTransport` and `FakeFirmware`; `RotaryStage` consumes only that interface and is tested against `FakeFirmware`. `FakeFirmware`'s replies mirror the Plan B firmware (`OK`/`READY`, `ERR nores` pre-`SETRES`, `STATUS …`), so the client validated in tests is the same client used on hardware. `ScanParams`/`ScanManifest` field names match Plan A. The CLI `scan` branch and Task 12's `run_scan_from_config` agree on signature.

**Testability boundary:** host coverage stops at real I/O — `SerialTransport`, `OpenCvCamera.grab`, `BaumerCamera`, and the Open3D window are bench-verified; all orchestration and protocol logic is exercised in-process via `FakeFirmware`/`MockCamera`/`SceneCamera`.

---

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Tasks 1–9 (and the factory in 10) are fully host-testable and can be driven start-to-finish with no hardware; Tasks 10 (grab) /11/12 need a webcam or the Baumer camera + the ESP32 board on the bench.
2. **Inline Execution** — implement tasks here with checkpoints.

Which approach? (And shall I run this on a `plan-c-integration` branch off `main`?)
