from gemscanner.calibration.calibration import Calibration


def test_roundtrip(tmp_path):
    c = Calibration(mm_per_px=0.0288, axis_column=1223.5, steps_per_rev=90000)
    p = tmp_path / "cal.json"
    c.save(p)
    loaded = Calibration.load(p)
    assert loaded.steps_per_rev == 90000
    assert abs(loaded.mm_per_px - 0.0288) < 1e-12
