import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.soft_hull import SoftHullReconstructor, _fill_holes


def test_fill_holes_fills_internal_hole():
    mask = np.ones((20, 20), np.uint8)
    mask[8:12, 8:12] = 0                 # caustic hole inside the silhouette
    filled = _fill_holes(mask)
    assert filled[10, 10] == 1           # hole filled
    assert filled.sum() == 400


def test_fill_holes_keeps_background():
    mask = np.zeros((20, 20), np.uint8)
    mask[5:15, 5:15] = 1
    filled = _fill_holes(mask)
    assert filled[0, 0] == 0             # outside stays outside
    assert filled[10, 10] == 1


def test_soft_hull_reconstructs_watertight_ellipsoid(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "s"), rx=4, ry=3, rz=5,
                                  n_views=90, mm_per_px=0.08, width=260, height=260)
    ds = load_dataset(out)
    mesh = SoftHullReconstructor().reconstruct(ds, vox_mm=0.15)
    assert mesh.is_watertight
    assert mesh.body_count == 1
    Vtrue = 4.0 / 3.0 * np.pi * 4 * 3 * 5
    assert abs(mesh.volume - Vtrue) < 0.06 * Vtrue
    ext = mesh.bounding_box.extents
    assert abs(ext[2] - 10.0) < 0.4      # height ~ 2*rz
