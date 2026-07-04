import numpy as np
from gemscanner.gui.analysis import analyze_frame


def _bg(h=100, w=100):
    return np.full((h, w), 255, np.uint8)


def test_interior_object_not_touching_border():
    img = _bg()
    img[30:70, 40:60] = 0            # dark object well inside
    a = analyze_frame(img)
    assert a.min == 0 and a.max == 255
    assert a.mean > 200
    assert len(a.histogram) == 256
    assert a.touches_border is False
    assert a.bbox == (30, 69, 40, 59)
    assert abs(a.centroid_col - 49.5) < 1.0


def test_object_touching_left_border_flagged():
    img = _bg()
    img[30:70, 0:20] = 0             # touches left edge
    a = analyze_frame(img)
    assert a.touches_border is True


def test_empty_silhouette_when_all_background():
    a = analyze_frame(_bg())
    assert a.bbox is None
    assert a.centroid_col is None
    assert a.touches_border is False


def test_holder_mask_excludes_bottom_rows():
    img = _bg()
    img[80:100, 40:60] = 0           # object only in bottom rows
    a = analyze_frame(img, holder_mask_rows=25)
    assert a.bbox is None            # masked away
