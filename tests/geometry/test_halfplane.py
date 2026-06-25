import numpy as np
from gemscanner.geometry.halfplane import clip_convex_polygon

SQUARE = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)

def test_clip_keeps_left_half():
    # keep x <= 0  => normal (1,0), offset 0
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], 0.0)
    assert out[:, 0].max() <= 1e-9
    assert np.isclose(out[:, 0].min(), -1.0)

def test_clip_empty_when_fully_outside():
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], -5.0)
    assert out.shape == (0, 2)

def test_clip_noop_when_fully_inside():
    out = clip_convex_polygon(SQUARE, [1.0, 0.0], 5.0)
    assert len(out) == 4
