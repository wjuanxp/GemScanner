import numpy as np
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.strip_intersection import (
    StripIntersectionReconstructor, median_smooth_spans)
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.geometry.polygon import polygon_area


def test_reconstruct_edge_median_is_wired(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "s"), rx=4, ry=3, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    r = StripIntersectionReconstructor()
    base = r.reconstruct(ds, ReconstructionParams())
    boxed = r.reconstruct(ds, ReconstructionParams(edge_median_rows=999))
    assert abs(boxed.volume - base.volume) > 0.1 * base.volume   # param consumed


def test_reconstruct_axial_median_is_wired(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "s"), rx=4, ry=3, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    r = StripIntersectionReconstructor()
    base = r.reconstruct(ds, ReconstructionParams())
    flat = r.reconstruct(ds, ReconstructionParams(axial_median_rows=999))
    assert abs(flat.volume - base.volume) > 0.1 * base.volume     # param consumed


def test_median_smooth_spans_removes_edge_outlier():
    spans = np.array([[10, 20], [10, 20], [10, 50], [10, 20], [10, 20]], float)
    out = median_smooth_spans(spans, 3)
    assert out[2, 1] == 20         # right edge outlier pulled to neighbour median
    assert out[0, 0] == 10


def test_median_smooth_spans_leaves_invalid_rows_untouched():
    spans = np.array([[-1, -1], [10, 20], [12, 22], [10, 20], [-1, -1]], float)
    out = median_smooth_spans(spans, 3)
    assert (out[0] == -1).all() and (out[-1] == -1).all()


def test_median_smooth_spans_window_zero_is_identity():
    spans = np.array([[10, 20], [11, 21]], float)
    assert np.allclose(median_smooth_spans(spans, 0), spans)

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


def test_subpixel_edges_are_wired_into_the_strip_carve(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "s"), rx=4, ry=3, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    r = StripIntersectionReconstructor()
    base = r.reconstruct(ds, ReconstructionParams(threshold=128,
                                                  subpixel_edges=False))
    sub = r.reconstruct(ds, ReconstructionParams(threshold=128,
                                                 subpixel_edges=True))
    # generator renders the inscribed pixel run, so sub-pixel edges recover
    # volume rather than losing it -- but only by a fraction of a pixel
    assert sub.volume > base.volume
    assert sub.volume < 1.10 * base.volume
