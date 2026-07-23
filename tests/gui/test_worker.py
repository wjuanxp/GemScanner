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


def test_reconstruct_op_forwards_recon_kwargs(qtbot):
    class RecSession:
        def __init__(self):
            self.kw = None
        def reconstruct(self, out_dir, **kw):
            self.kw = kw
            return (None, True, (1.0, 2.0, 3.0))

    w = HardwareWorker(RecSession())
    w.start()
    try:
        with qtbot.waitSignal(w.result, timeout=3000):
            w.post("reconstruct", out_dir="x", holder_mask_rows=2,
                   method="soft_hull", edge_median_rows=9, axial_median_rows=0,
                   subpixel_edges=False)
        assert w._session.kw["method"] == "soft_hull"
        assert w._session.kw["edge_median_rows"] == 9
        assert w._session.kw["subpixel_edges"] is False
    finally:
        w.shutdown()
        w.wait(3000)


def test_worker_applies_pending_exposure_before_grab(qtbot):
    from gemscanner.camera.base import CameraBackend

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
