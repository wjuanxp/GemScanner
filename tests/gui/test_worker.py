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
