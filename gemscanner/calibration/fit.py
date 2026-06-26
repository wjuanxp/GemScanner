import numpy as np


def fit_rotation_axis(angles_deg, centroid_cols):
    th = np.radians(np.asarray(angles_deg, float))
    u = np.asarray(centroid_cols, float)
    A = np.column_stack([np.ones_like(th), np.cos(th), np.sin(th)])
    c, a, b = np.linalg.lstsq(A, u, rcond=None)[0]
    return float(c), float(np.hypot(a, b))


def mm_per_px_from_gauge(measured_px, known_mm):
    return known_mm / measured_px


def steps_per_rev_from(motor_steps, microstep, gear_ratio):
    return int(round(motor_steps * microstep * gear_ratio))
