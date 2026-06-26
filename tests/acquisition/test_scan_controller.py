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
