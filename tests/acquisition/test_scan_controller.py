import numpy as np
from gemscanner.camera.mock import MockCamera
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.storage.dataset import load_dataset
from gemscanner.storage.manifest import ScanManifest


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
