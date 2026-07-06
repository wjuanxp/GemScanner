# tests/reconstruction/test_mesh.py
import numpy as np
import pytest
from gemscanner.reconstruction.base import SliceResult
from gemscanner.reconstruction.mesh import loft_slices_to_mesh, median_smooth_axial


def test_median_smooth_axial_removes_outlier_ring():
    rad = np.ones((5, 4))
    rad[2] = 5.0                       # one anomalous ring (terracing bump)
    out = median_smooth_axial(rad, window=3)
    assert np.allclose(out[2], 1.0)    # median of neighbours pulls it back
    assert np.allclose(out[0], 1.0)    # endpoints preserved


def test_median_smooth_axial_window_zero_is_identity():
    rad = np.arange(20.0).reshape(5, 4)
    assert np.allclose(median_smooth_axial(rad, 0), rad)


def test_median_smooth_axial_preserves_facet_step():
    rad = np.vstack([np.full((5, 4), 2.0), np.full((5, 4), 4.0)])  # sharp step
    out = median_smooth_axial(rad, window=3)
    assert np.allclose(out, rad)       # median keeps the step crisp

def square(half):
    return np.array([[-half, -half], [half, -half], [half, half], [-half, half]], float)

def test_lofts_watertight_box():
    slices = [SliceResult(z_mm=z, polygon=square(2.0)) for z in (0.0, 1.0, 2.0)]
    mesh = loft_slices_to_mesh(slices, n_radial=64)
    assert mesh.is_watertight
    assert mesh.volume > 0
    ext = mesh.bounding_box.extents
    assert abs(ext[0] - 4.0) < 0.2 and abs(ext[1] - 4.0) < 0.2
    assert abs(ext[2] - 2.0) < 1e-6

def test_loft_axial_median_smooths_outlier_slice():
    slices = [SliceResult(z_mm=z, polygon=square(2.0)) for z in (0., 1., 2., 3., 4.)]
    slices[2] = SliceResult(z_mm=2.0, polygon=square(5.0))   # terracing bulge
    raw = loft_slices_to_mesh(slices, n_radial=64)
    smoothed = loft_slices_to_mesh(slices, n_radial=64, axial_median_rows=3)
    assert smoothed.bounding_box.extents[0] < raw.bounding_box.extents[0] - 1.0


def test_raises_with_too_few_slices():
    with pytest.raises(ValueError):
        loft_slices_to_mesh([SliceResult(z_mm=0.0, polygon=square(2.0))])
