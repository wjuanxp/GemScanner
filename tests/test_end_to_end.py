# tests/test_end_to_end.py
import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.reconstruction.pipeline import reconstruct_dataset

TOL = 0.3   # mm; ~6 px at 0.05 mm/px, covers discretization + radial resampling

def _extents(out):
    return reconstruct_dataset(out).bounding_box.extents

def test_centered_dimensions(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "c"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ext = _extents(out)
    assert abs(ext[0] - 8.0) < TOL
    assert abs(ext[1] - 6.0) < TOL
    assert abs(ext[2] - 10.0) < TOL

def test_off_center_recovers_size_and_offset(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "o"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400,
                                  center_offset=(2.0, 1.0))
    mesh = reconstruct_dataset(out)
    ext = mesh.bounding_box.extents
    assert abs(ext[0] - 8.0) < TOL and abs(ext[1] - 6.0) < TOL
    # reconstruction is in the object frame: center recovered at the offset
    cx, cy, _ = mesh.bounding_box.centroid
    assert abs(cx - 2.0) < TOL and abs(cy - 1.0) < TOL

def test_asymmetric_shape(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "a"), rx=5, ry=2, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ext = _extents(out)
    assert abs(ext[0] - 10.0) < TOL
    assert abs(ext[1] - 4.0) < TOL
