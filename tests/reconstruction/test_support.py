import numpy as np
from gemscanner.synthetic.generator import generate_polyhedron_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.support import support_maps
from gemscanner.reconstruction.base import ReconstructionParams

def _box(hx, hy, hz):
    return np.array([[sx*hx, sy*hy, sz*hz]
                     for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)

def test_support_of_box_is_half_width_at_theta0(tmp_path):
    out = generate_polyhedron_scan(str(tmp_path / "box"), _box(4, 2, 5),
                                   n_views=4, mm_per_px=0.05, width=400, height=400)
    sm = support_maps(load_dataset(out))
    # theta=0 view: support in +x is hx = 4 mm, over the box's z-range
    col = np.nanmedian(sm.h_right[:, 0])
    assert abs(col - 4.0) <= 0.05        # within one pixel (mm_per_px)
    # rows outside the box are invalid
    assert sm.valid.any() and not sm.valid.all()


def test_subpixel_edges_reduce_the_half_width_bias(tmp_path):
    """Integer spans report the inscribed pixel run, under-measuring the box.
    Sub-pixel edge placement must land closer to the true 4 mm half-width."""
    out = generate_polyhedron_scan(str(tmp_path / "box"), _box(4, 2, 5),
                                   n_views=4, mm_per_px=0.05, width=400, height=400)
    ds = load_dataset(out)
    coarse = support_maps(ds, ReconstructionParams(threshold=128,
                                                   subpixel_edges=False))
    fine = support_maps(ds, ReconstructionParams(threshold=128,
                                                 subpixel_edges=True))
    e_coarse = abs(np.nanmedian(coarse.h_right[:, 0]) - 4.0)
    e_fine = abs(np.nanmedian(fine.h_right[:, 0]) - 4.0)
    assert e_fine < e_coarse


def test_subpixel_edges_are_not_quantised_to_whole_pixels(tmp_path):
    out = generate_polyhedron_scan(str(tmp_path / "box"), _box(4, 2, 5),
                                   n_views=4, mm_per_px=0.05, width=400, height=400)
    sm = support_maps(load_dataset(out),
                      ReconstructionParams(threshold=128, subpixel_edges=True))
    cols = sm.h_right[sm.valid] / 0.05          # back to pixel units
    assert not np.allclose(cols, np.round(cols))
