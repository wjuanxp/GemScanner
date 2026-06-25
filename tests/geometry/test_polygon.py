# tests/geometry/test_polygon.py
import math
import numpy as np
from gemscanner.geometry.polygon import polygon_area, polygon_centroid, ray_radius

SQUARE = np.array([[-2, -2], [2, -2], [2, 2], [-2, 2]], dtype=float)

def test_area():
    assert math.isclose(polygon_area(SQUARE), 16.0, abs_tol=1e-9)

def test_centroid():
    c = polygon_centroid(SQUARE)
    assert np.allclose(c, [0.0, 0.0], atol=1e-9)

def test_ray_radius_hits_right_edge():
    r = ray_radius(SQUARE, [0.0, 0.0], 0.0)   # +x direction
    assert math.isclose(r, 2.0, abs_tol=1e-9)

def test_ray_radius_diagonal():
    r = ray_radius(SQUARE, [0.0, 0.0], math.radians(45))
    assert math.isclose(r, 2.0 * math.sqrt(2), abs_tol=1e-6)
