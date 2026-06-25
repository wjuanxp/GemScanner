# gemscanner/coords.py
import math


def row_to_z(v, height, mm_per_px):
    """Map image row v (0 at top) to object height z in mm (increasing upward).
    z=0 at the vertical centre of the image (row (height-1)/2)."""
    return ((height - 1) / 2.0 - v) * mm_per_px


def z_to_row(z, height, mm_per_px):
    return (height - 1) / 2.0 - z / mm_per_px


def axis_column_at_row(axis_column, axis_tilt_rad, v, height):
    """Rotation-axis pixel column at row v, accounting for small axis tilt."""
    v0 = (height - 1) / 2.0
    return axis_column + math.tan(axis_tilt_rad) * (v - v0)


def projection_to_column(p_mm, axis_col, mm_per_px):
    """Horizontal object coordinate (mm, relative to axis) -> pixel column."""
    return axis_col + p_mm / mm_per_px


def column_to_projection(u, axis_col, mm_per_px):
    """Pixel column -> horizontal object coordinate (mm, relative to axis)."""
    return (u - axis_col) * mm_per_px
