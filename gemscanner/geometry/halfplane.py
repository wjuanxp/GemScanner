import numpy as np


def clip_convex_polygon(polygon, normal, offset):
    """Sutherland-Hodgman clip of a convex polygon by a single half-plane.

    Keeps the region where dot(normal, point) <= offset.
    Returns an (M,2) float array, or an empty (0,2) array if fully clipped.
    """
    polygon = np.asarray(polygon, dtype=float)
    if len(polygon) == 0:
        return np.empty((0, 2), dtype=float)
    normal = np.asarray(normal, dtype=float)
    result = []
    n = len(polygon)
    for i in range(n):
        cur = polygon[i]
        nxt = polygon[(i + 1) % n]
        cur_in = np.dot(normal, cur) <= offset
        nxt_in = np.dot(normal, nxt) <= offset
        if cur_in:
            result.append(cur)
        if cur_in != nxt_in:
            d = np.dot(normal, nxt - cur)
            if abs(d) > 1e-12:
                t = (offset - np.dot(normal, cur)) / d
                result.append(cur + t * (nxt - cur))
    if not result:
        return np.empty((0, 2), dtype=float)
    return np.array(result, dtype=float)
