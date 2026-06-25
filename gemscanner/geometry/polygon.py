# gemscanner/geometry/polygon.py
import numpy as np


def polygon_area(polygon):
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def polygon_centroid(polygon):
    x = polygon[:, 0]
    y = polygon[:, 1]
    x1 = np.roll(x, -1)
    y1 = np.roll(y, -1)
    cross = x * y1 - x1 * y
    a = cross.sum() / 2.0
    if abs(a) < 1e-12:
        return polygon.mean(axis=0)
    cx = ((x + x1) * cross).sum() / (6 * a)
    cy = ((y + y1) * cross).sum() / (6 * a)
    return np.array([cx, cy])


def ray_radius(polygon, center, angle):
    """Distance from interior `center` to the boundary along (cos, sin)."""
    d = np.array([np.cos(angle), np.sin(angle)])
    center = np.asarray(center, dtype=float)
    n = len(polygon)
    best = None
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        e = b - a
        # solve center + t*d = a + s*e  =>  [d | -e] [t, s]^T = a - center
        denom = d[0] * (-e[1]) - d[1] * (-e[0])
        if abs(denom) < 1e-12:
            continue
        diff = a - center
        t = (diff[0] * (-e[1]) - diff[1] * (-e[0])) / denom
        s = (d[0] * diff[1] - d[1] * diff[0]) / denom
        if t >= -1e-9 and -1e-9 <= s <= 1 + 1e-9:
            if best is None or t < best:
                best = t
    return float(best) if best is not None else 0.0
