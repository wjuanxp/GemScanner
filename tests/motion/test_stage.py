import pytest
from gemscanner.motion.fake_firmware import FakeFirmware
from gemscanner.motion.stage import RotaryStage, StageError


def test_step_and_status_roundtrip():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(20000)
    stage.step(5000)
    st = stage.status()
    assert st["steps"] == 5000
    assert st["res"] == 20000
    assert abs(st["angle"] - 90.0) < 1e-6


def test_move_deg_before_setres_raises():
    stage = RotaryStage(FakeFirmware())
    with pytest.raises(StageError):
        stage.move_deg(90)


def test_move_deg_after_setres():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(36000)
    stage.move_deg(45)
    assert stage.status()["steps"] == 4500


def test_home_zeroes():
    stage = RotaryStage(FakeFirmware())
    stage.set_resolution(20000); stage.step(1234); stage.home()
    assert stage.status()["steps"] == 0
