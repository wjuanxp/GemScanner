import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import StripIntersectionReconstructor
from gemscanner.geometry.polygon import polygon_area

def test_midplane_cross_section_matches_ellipse_area(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=180, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    slices = StripIntersectionReconstructor().slice_cross_sections(ds)
    # mid-height slice (z ~ 0) should approximate the equatorial ellipse pi*rx*ry
    mids = [s for s in slices if s.polygon is not None and abs(s.z_mm) < 0.05]
    assert mids, "expected a near-equatorial non-empty slice"
    area = polygon_area(mids[0].polygon)
    assert abs(area - np.pi * 4 * 3) < 1.0     # within 1 mm^2

def test_slices_empty_above_top(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    slices = StripIntersectionReconstructor().slice_cross_sections(ds)
    tops = [s for s in slices if s.z_mm > 5.2]
    assert all(s.polygon is None for s in tops)
