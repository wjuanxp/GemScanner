# GemScanner GUI Increment: Exposure/Gain Controls + Wizard Sequencing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the two design-spec gaps the final review surfaced: live exposure/gain adjustment (spec §1) and the guided wizard sequencing + in-UI cancel (spec §3, §5).

**Architecture:** Extends the existing three-layer GUI. Camera gains a live `set_gain` (mirroring `set_exposure`) and both setters now persist onto the camera object so the worker's close/reopen between preview and ops keeps the tuned values. The `HardwareWorker` applies pending exposure/gain on its own thread before the next preview grab. A new `ControlsPanel` widget drives the sliders; `MainWindow` wires them (with per-gem persistence) and drives step progression + cancel.

**Tech Stack:** PySide6, existing `gemscanner` package. Tests: pytest + pytest-qt (headless `QT_QPA_PLATFORM=offscreen`).

## Global Constraints

- Base branch for this increment is the tip of `feat/gui-over-cli` AFTER the final-review defect fix commit (`fix(gui): update worker mask on gem switch; ...`). Confirm `git log --oneline -1` shows that fix before starting Task I1.
- Qt-free layers (`camera/*.py`, `gui/session.py`) MUST NOT import PySide6. Only `worker.py`, widgets, `main_window.py`, `app.py` use Qt.
- Qt tests headless: `QT_QPA_PLATFORM=offscreen`, guarded with `pytest.importorskip("PySide6")`, use `qtbot`. Add Qt tests to `tests/gui/test_widgets.py`; add worker tests to `tests/gui/test_worker.py`.
- Tests run via `.venv/Scripts/python.exe -m pytest`.
- Reuse existing signatures:
  - `CameraBackend.set_exposure(us)` (base no-op; GenTL live via `_set_first(self._EXPOSURE, float(us))`).
  - `GenTLCamera._set_first(names, value)`, `GenTLCamera._GAIN = ("Gain","GainAbs","GainRaw")`, fields `self.exposure_us`, `self.gain`, `self._ia`.
  - `ScanSession.set_exposure(us)` → `self.camera.set_exposure(us)`.
  - `HardwareWorker`: `_preview_frame` polls `self._session.camera.grab()` + `self._session.analyze(...)`; UI-thread setters store state read on the worker thread (pattern of `set_view`).
  - `WizardPanel` signals `mountConfirmed`, `calibrateRequested`, `scanRequested`, `reconstructRequested`, `nextGemRequested`; `set_step(index)`, `step()`; `progress` QProgressBar; `STEPS` list has 7 entries (0 Mount … 6 Next gem).
  - `MainWindow` handlers `_on_gem_selected`, `_on_mask_changed`, `_on_progress`, `_on_result`, `_on_failed`; `self.worker`, `self.preview`, `self.queue`, `self.wizard`, `self._current`, `self._current_gem()`.
  - `GemJob` has `exposure_us: float | None` and `gain: float | None` fields already.
- Spec: `docs/superpowers/specs/2026-07-03-gui-over-cli-design.md`.

---

## File Structure

- Modify: `gemscanner/camera/base.py` — add `set_gain` no-op.
- Modify: `gemscanner/camera/gentl_camera.py` — add live `set_gain`; make `set_exposure`/`set_gain` persist onto `self.exposure_us`/`self.gain`.
- Modify: `gemscanner/gui/session.py` — add `set_gain`.
- Modify: `gemscanner/gui/worker.py` — pending exposure/gain applied before preview grab.
- Create: `gemscanner/gui/controls_panel.py` — `ControlsPanel` (exposure + gain sliders).
- Modify: `gemscanner/gui/main_window.py` — add ControlsPanel, wire exposure/gain with per-gem persistence, wizard step progression, cancel.
- Modify: `gemscanner/gui/wizard_panel.py` — add Cancel button + `cancelRequested` signal.
- Modify: `gemscanner/gui/style.qss` — style the sliders/controls (minor; reuse existing slider rules).
- Tests: `tests/gui/test_session.py`, `tests/gui/test_worker.py`, `tests/gui/test_widgets.py`.

---

## Task I1: Camera + session gain control (Qt-free)

**Files:**
- Modify: `gemscanner/camera/base.py`
- Modify: `gemscanner/camera/gentl_camera.py`
- Modify: `gemscanner/gui/session.py`
- Test: `tests/gui/test_session.py` (add a test)

**Interfaces:**
- Produces: `CameraBackend.set_gain(gain)` (no-op default); `GenTLCamera.set_gain(gain)` (live + persists `self.gain`); `GenTLCamera.set_exposure` now also persists `self.exposure_us`; `ScanSession.set_gain(g)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/gui/test_session.py`:

```python
from gemscanner.camera.base import CameraBackend


class _RecordingCamera(CameraBackend):
    def __init__(self):
        self.exposures = []
        self.gains = []
    def open(self): pass
    def close(self): pass
    def grab(self):
        import numpy as np
        return np.full((10, 10), 255, np.uint8)
    def set_exposure(self, us): self.exposures.append(us)
    def set_gain(self, gain): self.gains.append(gain)


def test_session_forwards_exposure_and_gain():
    from gemscanner.config import ScannerConfig
    from gemscanner.gui.session import ScanSession
    cam = _RecordingCamera()
    s = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=object())
    s.set_exposure(750.0)
    s.set_gain(3.0)
    assert cam.exposures == [750.0]
    assert cam.gains == [3.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_session.py::test_session_forwards_exposure_and_gain -v`
Expected: FAIL — `AttributeError: 'ScanSession' object has no attribute 'set_gain'`.

- [ ] **Step 3: Implement**

In `gemscanner/camera/base.py`, add after `set_exposure`:

```python
    def set_gain(self, gain):
        pass
```

In `gemscanner/gui/session.py`, add after `set_exposure`:

```python
    def set_gain(self, g):
        self.camera.set_gain(g)
```

In `gemscanner/camera/gentl_camera.py`, replace the existing `set_exposure` method with:

```python
    def set_exposure(self, us):
        self.exposure_us = float(us)
        if self._ia is not None:
            self._set_first(self._EXPOSURE, float(us))

    def set_gain(self, gain):
        self.gain = float(gain)
        if self._ia is not None:
            self._set_first(self._GAIN, float(gain))
```

(Persisting onto `self.exposure_us`/`self.gain` means the worker's close/reopen between preview and ops re-applies the tuned values in `open()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_session.py -v`
Expected: PASS (all session tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/camera/base.py gemscanner/camera/gentl_camera.py gemscanner/gui/session.py tests/gui/test_session.py
git commit -m "feat(camera): live set_gain and persistent set_exposure/set_gain; session.set_gain"
```

---

## Task I2: Worker applies pending exposure/gain

**Files:**
- Modify: `gemscanner/gui/worker.py`
- Test: `tests/gui/test_worker.py` (add a test)

**Interfaces:**
- Consumes: `ScanSession.set_exposure`/`set_gain` (Task I1).
- Produces: `HardwareWorker.set_exposure(us)`, `HardwareWorker.set_gain(gain)` (UI-thread; stored as pending and applied on the worker thread before the next preview grab).

- [ ] **Step 1: Write the failing test**

Add to `tests/gui/test_worker.py` (reuse the file's existing offscreen/importorskip header):

```python
def test_worker_applies_pending_exposure_before_grab(qtbot):
    import numpy as np
    from gemscanner.config import ScannerConfig
    from gemscanner.camera.base import CameraBackend
    from gemscanner.gui.session import ScanSession
    from gemscanner.gui.worker import HardwareWorker

    class RecCam(CameraBackend):
        def __init__(self): self.exposures = []; self.gains = []
        def open(self): pass
        def close(self): pass
        def grab(self): return np.full((20, 20), 255, np.uint8)
        def set_exposure(self, us): self.exposures.append(us)
        def set_gain(self, gain): self.gains.append(gain)

    cam = RecCam()
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=object())
    w = HardwareWorker(session)
    w.start()
    try:
        w.set_view(threshold=None, holder_mask_rows=0)
        w.set_exposure(900.0)
        w.set_gain(4.0)
        with qtbot.waitSignal(w.frameReady, timeout=3000):
            w.start_preview()
        assert cam.exposures and cam.exposures[-1] == 900.0
        assert cam.gains and cam.gains[-1] == 4.0
    finally:
        w.shutdown()
        w.wait(3000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_worker.py::test_worker_applies_pending_exposure_before_grab -v`
Expected: FAIL — `AttributeError: 'HardwareWorker' object has no attribute 'set_exposure'`.

- [ ] **Step 3: Implement**

In `gemscanner/gui/worker.py`, add pending fields in `__init__` (next to `self._threshold`/`self._holder`):

```python
        self._pending_exposure = None
        self._pending_gain = None
```

Add UI-thread setters (next to `set_view`):

```python
    def set_exposure(self, us):
        self._pending_exposure = float(us)

    def set_gain(self, gain):
        self._pending_gain = float(gain)
```

In `_preview_frame`, apply pending values on the worker thread right after ensuring the camera is open and before `grab()`:

```python
    def _preview_frame(self):
        try:
            if not self._cam_open:
                self._session.camera.open()
                self._cam_open = True
            if self._pending_exposure is not None:
                self._session.set_exposure(self._pending_exposure)
                self._pending_exposure = None
            if self._pending_gain is not None:
                self._session.set_gain(self._pending_gain)
                self._pending_gain = None
            frame = self._session.camera.grab()
            analysis = self._session.analyze(frame, self._threshold, self._holder)
            self.frameReady.emit(frame, analysis)
        except Exception as exc:
            self._pause_preview()
            self.failed.emit("preview", str(exc))
```

(The `except` calls `_pause_preview()` — this matches the final-review fix already applied to the base worker; keep it consistent.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_worker.py -v`
Expected: PASS (all worker tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/worker.py tests/gui/test_worker.py
git commit -m "feat(gui): worker applies pending exposure/gain before preview grab"
```

---

## Task I3: ControlsPanel (exposure/gain sliders) + MainWindow wiring

**Files:**
- Create: `gemscanner/gui/controls_panel.py`
- Modify: `gemscanner/gui/main_window.py`
- Modify: `gemscanner/gui/style.qss` (optional; existing QSlider rules already apply)
- Test: `tests/gui/test_widgets.py` (add tests)

**Interfaces:**
- Consumes: `HardwareWorker.set_exposure`/`set_gain` (Task I2), `GemJob` fields `exposure_us`/`gain`.
- Produces: `ControlsPanel(QWidget)` with `set_values(exposure_us, gain)`, signals `exposureChanged(float)`, `gainChanged(float)`, `exposure_us()`, `gain()`. MainWindow shows it, persists changes to the current gem, and initialises it on gem selection.

- [ ] **Step 1: Write the failing tests**

Add to `tests/gui/test_widgets.py`:

```python
def test_controls_panel_signals_and_values(qtbot):
    from gemscanner.gui.controls_panel import ControlsPanel
    c = ControlsPanel()
    qtbot.addWidget(c)
    c.set_values(500.0, 5.0)
    assert c.exposure_us() == 500.0
    assert c.gain() == 5.0
    seen = []
    c.exposureChanged.connect(seen.append)
    c.set_exposure_us(750.0)
    c.exposureChanged.emit(c.exposure_us())   # simulate slider commit
    assert seen[-1] == 750.0


def test_main_window_gem_select_updates_controls_and_worker(qtbot):
    import numpy as np
    from gemscanner.config import ScannerConfig
    from gemscanner.motion.fake_firmware import FakeFirmware
    from gemscanner.motion.stage import RotaryStage
    from gemscanner.testing.scene_camera import SceneCamera
    from gemscanner.gui.session import ScanSession
    from gemscanner.gui.project import Project, GemJob
    from gemscanner.gui.main_window import MainWindow

    fw = FakeFirmware(); stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=200, height=200)
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=stage)
    project = Project(gems=[
        GemJob(name="a", holder_mask_rows=30, exposure_us=400.0, gain=2.0),
        GemJob(name="b", holder_mask_rows=55, exposure_us=800.0, gain=6.0),
    ])
    win = MainWindow(project, session)
    qtbot.addWidget(win)
    win.queue.select(1)
    assert win.controls.exposure_us() == 800.0
    assert win.controls.gain() == 6.0
    win.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v -k "controls or gem_select_updates_controls"`
Expected: FAIL — `ModuleNotFoundError: No module named 'gemscanner.gui.controls_panel'`.

- [ ] **Step 3: Implement**

Create `gemscanner/gui/controls_panel.py`:

```python
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider


class ControlsPanel(QWidget):
    """Exposure and gain sliders for live camera tuning."""

    exposureChanged = Signal(float)
    gainChanged = Signal(float)

    # slider integer ranges map 1:1 to device units
    EXPOSURE_MIN, EXPOSURE_MAX = 50, 20000     # microseconds
    GAIN_MIN, GAIN_MAX = 0, 24                  # dB-ish, device dependent

    def __init__(self, parent=None):
        super().__init__(parent)
        self._exp = QSlider(Qt.Horizontal)
        self._exp.setRange(self.EXPOSURE_MIN, self.EXPOSURE_MAX)
        self._exp_val = QLabel(objectName="statsLabel")
        self._gain = QSlider(Qt.Horizontal)
        self._gain.setRange(self.GAIN_MIN, self.GAIN_MAX)
        self._gain_val = QLabel(objectName="statsLabel")
        self._exp.valueChanged.connect(self._on_exposure)
        self._gain.valueChanged.connect(self._on_gain)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Camera", objectName="panelTitle"))
        for label, slider, val in (("Exposure (us)", self._exp, self._exp_val),
                                   ("Gain", self._gain, self._gain_val)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(slider, 1)
            row.addWidget(val)
            layout.addLayout(row)
        self.set_values(self.EXPOSURE_MIN, self.GAIN_MIN)

    def exposure_us(self):
        return float(self._exp.value())

    def gain(self):
        return float(self._gain.value())

    def set_exposure_us(self, us):
        self._exp.blockSignals(True)
        self._exp.setValue(int(us))
        self._exp.blockSignals(False)
        self._exp_val.setText(str(int(us)))

    def set_gain(self, gain):
        self._gain.blockSignals(True)
        self._gain.setValue(int(gain))
        self._gain.blockSignals(False)
        self._gain_val.setText(str(int(gain)))

    def set_values(self, exposure_us, gain):
        self.set_exposure_us(exposure_us)
        self.set_gain(gain)

    def _on_exposure(self, value):
        self._exp_val.setText(str(int(value)))
        self.exposureChanged.emit(float(value))

    def _on_gain(self, value):
        self._gain_val.setText(str(int(value)))
        self.gainChanged.emit(float(value))
```

Now wire it into `gemscanner/gui/main_window.py`. Add the import at the top with the other widget imports:

```python
from gemscanner.gui.controls_panel import ControlsPanel
```

In `MainWindow.__init__`, after `self.wizard = WizardPanel()` and before the layout is assembled, create the panel and read the project camera defaults:

```python
        self.controls = ControlsPanel()
        cam_cfg = project.camera or {}
        self._default_exposure = float(cam_cfg.get("exposure_us", ControlsPanel.EXPOSURE_MIN))
        self._default_gain = float(cam_cfg.get("gain", ControlsPanel.GAIN_MIN))
```

Add `self.controls` to the left column layout, below the wizard (adjust the existing `left.addWidget(...)` block):

```python
        left.addWidget(self.wizard)
        left.addWidget(self.controls)
        left.addWidget(self.queue, 1)
```

Wire the signals (in the "# wiring" block):

```python
        self.controls.exposureChanged.connect(self._on_exposure_changed)
        self.controls.gainChanged.connect(self._on_gain_changed)
```

Initialise the worker with the starting exposure/gain (after `self.worker.set_view(...)`, before/after `start_preview`):

```python
        self.worker.set_exposure(self._default_exposure)
        self.worker.set_gain(self._default_gain)
```

Add the handlers and extend `_on_gem_selected` to initialise the controls per gem. Add these methods:

```python
    def _on_exposure_changed(self, us):
        self.worker.set_exposure(us)
        gem = self._current_gem()
        if gem is not None:
            gem.exposure_us = us

    def _on_gain_changed(self, gain):
        self.worker.set_gain(gain)
        gem = self._current_gem()
        if gem is not None:
            gem.gain = gain
```

In the existing `_on_gem_selected`, after setting the preview mask, initialise the controls to the gem's values (falling back to project defaults) and push them to the worker:

```python
    def _on_gem_selected(self, index):
        self._current = index
        gem = self._current_gem()
        if gem is not None:
            self.preview.set_holder_mask_rows(gem.holder_mask_rows)
            self.worker.set_view(None, gem.holder_mask_rows)
            exposure = gem.exposure_us if gem.exposure_us is not None else self._default_exposure
            gain = gem.gain if gem.gain is not None else self._default_gain
            self.controls.set_values(exposure, gain)
            self.worker.set_exposure(exposure)
            self.worker.set_gain(gain)
```

(This also carries the final-review `set_view` fix; keep it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: PASS (all widget tests incl. the two new).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/controls_panel.py gemscanner/gui/main_window.py tests/gui/test_widgets.py
git commit -m "feat(gui): exposure/gain sliders wired to worker with per-gem persistence"
```

---

## Task W1: WizardPanel cancel button + signal

**Files:**
- Modify: `gemscanner/gui/wizard_panel.py`
- Test: `tests/gui/test_widgets.py` (add a test)

**Interfaces:**
- Produces: `WizardPanel.cancelRequested` signal + a "Cancel" button that emits it.

- [ ] **Step 1: Write the failing test**

Add to `tests/gui/test_widgets.py`:

```python
def test_wizard_cancel_signal(qtbot):
    from gemscanner.gui.wizard_panel import WizardPanel
    w = WizardPanel()
    qtbot.addWidget(w)
    fired = []
    w.cancelRequested.connect(lambda: fired.append("x"))
    w.cancelRequested.emit()
    assert fired == ["x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py::test_wizard_cancel_signal -v`
Expected: FAIL — `AttributeError: 'WizardPanel' object has no attribute 'cancelRequested'`.

- [ ] **Step 3: Implement**

In `gemscanner/gui/wizard_panel.py`, add the signal with the others:

```python
    cancelRequested = Signal()
```

Add a Cancel button in `__init__` alongside the other buttons and connect it:

```python
        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self.cancelRequested)
```

Add it to the `buttons` layout (after `self._btn_next`) and include it in the styling loop tuple:

```python
        for b in (self._btn_mount, self._btn_cal, self._btn_scan,
                  self._btn_recon, self._btn_next, self._btn_cancel):
            buttons.addWidget(b)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v -k wizard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/wizard_panel.py tests/gui/test_widgets.py
git commit -m "feat(gui): WizardPanel cancel button and cancelRequested signal"
```

---

## Task W2: MainWindow wizard sequencing + cancel wiring

**Files:**
- Modify: `gemscanner/gui/main_window.py`
- Test: `tests/gui/test_widgets.py` (add a test)

**Interfaces:**
- Consumes: `WizardPanel` signals (`mountConfirmed`, `nextGemRequested`, `cancelRequested`), `set_step`; `worker.cancel()`; `queue.select`.
- Produces: step progression across the flow and queue advance; `mountConfirmed`→Align(1), `maskChanged` while on Align→Holder(2), `calibrateRequested`→Calibrate(3), result `calibrate`→Scan(4), result `scan`→Reconstruct(5), result `reconstruct`→Next gem(6), `nextGemRequested`→select next gem + Mount(0), `cancelRequested`→`worker.cancel()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/gui/test_widgets.py`:

```python
def test_main_window_wizard_sequencing(qtbot):
    from gemscanner.config import ScannerConfig
    from gemscanner.motion.fake_firmware import FakeFirmware
    from gemscanner.motion.stage import RotaryStage
    from gemscanner.testing.scene_camera import SceneCamera
    from gemscanner.gui.session import ScanSession
    from gemscanner.gui.project import Project, GemJob
    from gemscanner.gui.main_window import MainWindow

    fw = FakeFirmware(); stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=200, height=200)
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=stage)
    project = Project(gems=[GemJob(name="a"), GemJob(name="b")])
    win = MainWindow(project, session)
    qtbot.addWidget(win)

    win.wizard.mountConfirmed.emit()
    assert win.wizard.step() == 1                      # Align

    win._on_result("calibrate", (99.5, 0.0))
    assert win.wizard.step() == 4                      # Scan

    win._on_result("scan", "scans/a")
    assert win.wizard.step() == 5                      # Reconstruct

    win.wizard.nextGemRequested.emit()
    assert win._current == 1                           # advanced to gem b
    assert win.wizard.step() == 0                      # back to Mount
    win.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py::test_main_window_wizard_sequencing -v`
Expected: FAIL — `mountConfirmed` does not change the step (assert `step() == 1` fails, stays 0).

- [ ] **Step 3: Implement**

In `gemscanner/gui/main_window.py` "# wiring" block, connect the newly-wired signals:

```python
        self.wizard.mountConfirmed.connect(lambda: self.wizard.set_step(1))
        self.wizard.nextGemRequested.connect(self._on_next_gem)
        self.wizard.cancelRequested.connect(self.worker.cancel)
```

Change the calibrate connection so requesting calibrate also shows the Calibrate step. Replace the existing:

```python
        self.wizard.calibrateRequested.connect(lambda: self.worker.post("calibrate", n_probe=12))
```

with:

```python
        def _calibrate():
            self.wizard.set_step(3)
            self.worker.post("calibrate", n_probe=12)
        self.wizard.calibrateRequested.connect(_calibrate)
```

Extend `_on_mask_changed` so dragging the mask while on the Align step advances to Holder mask (step 2). Add at the end of `_on_mask_changed`:

```python
        if self.wizard.step() == 1:
            self.wizard.set_step(2)
```

Extend `_on_result` to advance the wizard by op. In `_on_result`, after the existing per-op handling, add step transitions:

```python
        if op == "calibrate":
            self.wizard.set_step(4)          # -> Scan
        elif op == "scan":
            self.wizard.set_step(5)          # -> Reconstruct
        elif op == "reconstruct":
            self.wizard.set_step(6)          # -> Next gem
```

Add the next-gem handler:

```python
    def _on_next_gem(self):
        nxt = self._current + 1
        if nxt < len(self.project.gems):
            self.queue.select(nxt)           # drives _on_gem_selected
        self.wizard.set_step(0)              # back to Mount for the next gem
```

Note: `_on_result` already calls `self.worker.start_preview()` at its end — keep that; the step transitions run before it.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/gui/test_widgets.py -v`
Expected: PASS (all widget tests).

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — prior tests + all new increment tests, no regressions.

- [ ] **Step 6: Commit**

```bash
git add gemscanner/gui/main_window.py tests/gui/test_widgets.py
git commit -m "feat(gui): wizard step sequencing, queue advance, and cancel wiring"
```

---

## Self-Review Notes

- **Spec coverage:** §1 interactive exposure/gain tuning → Tasks I1–I3 (live setters, worker application, sliders + persistence); §3 cancel → Task W1 (button/signal) + W2 (wired to `worker.cancel`); §5 guided step sequence + swap advance → Task W2.
- **Persistence across reopen:** Task I1 persists tuned exposure/gain onto the camera object so the worker's close/reopen between preview and ops (`GenTLCamera.open()` re-applies `self.exposure_us`/`self.gain`) keeps the operator's tuning for the actual scan.
- **Threading:** exposure/gain are applied on the worker thread inside `_preview_frame` (never from the UI thread), consistent with the single-hardware-thread invariant. Ops reopen the camera which re-applies persisted values.
- **Deferred (tracked, not in this increment):** histogram *display* (data already computed in `FrameAnalysis`), and a scan-completion toast. Both Minor; record in roadmap memory.
- **Type consistency:** `exposure_us`/`gain` are floats end-to-end (GemJob fields, ControlsPanel signals `Signal(float)`, worker setters cast to float, session/camera cast to float).
