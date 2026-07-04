from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage
from gemscanner.testing.scene_camera import SceneCamera
from gemscanner.calibration.axis_probe import probe_axis


def _rig(offset=(0.0, 0.0)):
    fw = FakeFirmware()
    stage = RotaryStage(fw)
    stage.set_resolution(36000)
    cam = SceneCamera(fw, rx=4, ry=3, rz=5, mm_per_px=0.05,
                      width=400, height=400, center_offset=offset)
    return stage, cam


def test_probe_axis_fits_center_with_progress():
    stage, cam = _rig(offset=(2.0, 0.0))   # off-center -> centroid swings
    seen = []
    axis, amp = probe_axis(cam, stage, n_probe=12,
                           progress=lambda d, n: seen.append((d, n)))
    assert abs(axis - (400 - 1) / 2.0) < 2.0
    assert amp > 1.0                        # real swing detected
    assert seen[-1] == (12, 12)


def test_probe_axis_cancel_stops_early():
    stage, cam = _rig(offset=(2.0, 0.0))
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2               # cancel after 2 probes -> <3 silhouettes

    import pytest
    # cancelling before 3 silhouettes are collected interrupts the loop, so the
    # fit has too few points and raises -- proof the cancel actually stopped it.
    with pytest.raises(ValueError):
        probe_axis(cam, stage, n_probe=12, cancel=cancel)
