import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gemscanner.gui.analysis import analyze_frame
from gemscanner.gui.preview_widget import LivePreviewWidget
from gemscanner.gui.project import GemJob
from gemscanner.gui.queue_panel import QueuePanel
from gemscanner.gui.wizard_panel import WizardPanel


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


def test_gem_switch_updates_worker_mask(qtbot):
    """Regression: switching gems must update the worker's analysis mask (Fix 1)."""
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05, width=200, height=200)
    session = ScanSession(ScannerConfig(camera_backend="mock"), camera=cam, stage=stage)
    project = Project(gems=[
        GemJob(name="ruby-01", holder_mask_rows=30),
        GemJob(name="emerald-02", holder_mask_rows=55),
    ])
    win = MainWindow(project, session)
    qtbot.addWidget(win)
    # Select the second gem — worker must pick up its mask
    win._on_gem_selected(1)
    assert win.worker._holder == 55, (
        f"worker._holder={win.worker._holder!r}, expected 55 — "
        "set_view not called after gem switch"
    )
    win.close()


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
    fw = FakeFirmware()
    stage = RotaryStage(fw)
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


def test_wizard_cancel_signal(qtbot):
    from gemscanner.gui.wizard_panel import WizardPanel
    w = WizardPanel()
    qtbot.addWidget(w)
    fired = []
    w.cancelRequested.connect(lambda: fired.append("x"))
    w.cancelRequested.emit()
    assert fired == ["x"]
