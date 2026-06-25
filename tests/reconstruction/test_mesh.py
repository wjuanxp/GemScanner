# tests/reconstruction/test_mesh.py
import numpy as np
import pytest
from gemscanner.reconstruction.base import SliceResult
from gemscanner.reconstruction.mesh import loft_slices_to_mesh

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

def test_raises_with_too_few_slices():
    with pytest.raises(ValueError):
        loft_slices_to_mesh([SliceResult(z_mm=0.0, polygon=square(2.0))])
