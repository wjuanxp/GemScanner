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
