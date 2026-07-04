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
