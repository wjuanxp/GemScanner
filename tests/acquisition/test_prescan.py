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
