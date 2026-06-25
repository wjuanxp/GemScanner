# tests/test_coords.py
import math
from gemscanner.coords import (
    row_to_z, z_to_row, axis_column_at_row,
    projection_to_column, column_to_projection,
)

def test_row_z_roundtrip():
    z = row_to_z(120, height=400, mm_per_px=0.05)
    assert math.isclose(z_to_row(z, 400, 0.05), 120, abs_tol=1e-9)

def test_projection_roundtrip():
    u = projection_to_column(1.3, axis_col=199.5, mm_per_px=0.05)
    assert math.isclose(column_to_projection(u, 199.5, 0.05), 1.3, abs_tol=1e-9)

def test_axis_tilt_shifts_columns():
    # zero tilt => constant axis column
    assert axis_column_at_row(199.5, 0.0, v=0, height=400) == 199.5
    # positive tilt => columns shift linearly around vertical center
    v0 = (400 - 1) / 2
    expected = 199.5 + math.tan(0.01) * (10 - v0)
    assert math.isclose(axis_column_at_row(199.5, 0.01, 10, 400), expected, abs_tol=1e-9)
