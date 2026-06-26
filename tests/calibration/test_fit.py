import numpy as np
from gemscanner.calibration.fit import (
    fit_rotation_axis, mm_per_px_from_gauge, steps_per_rev_from)


def test_fit_recovers_axis_and_amplitude():
    angles = np.arange(0, 360, 10.0)
    c, A, phase = 128.5, 7.0, 0.6
    cols = c + A * np.cos(np.radians(angles) - phase)
    axis, amp = fit_rotation_axis(angles, cols)
    assert abs(axis - c) < 1e-6
    assert abs(amp - A) < 1e-6


def test_scale_and_steps():
    assert abs(mm_per_px_from_gauge(200, 10.0) - 0.05) < 1e-9
    assert steps_per_rev_from(500, 10, 18) == 90000
