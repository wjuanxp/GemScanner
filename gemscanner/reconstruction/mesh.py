# gemscanner/reconstruction/mesh.py
import numpy as np
import trimesh
from gemscanner.geometry.polygon import polygon_centroid, polygon_area, ray_radius


def median_smooth_axial(rad, window):
    """Median-filter an (M, n_radial) ring-radius field along the axial (z) axis.

    Edge-preserving: removes per-row terracing (rank-rejection of outlier rows)
    while keeping real facet steps crisp. window<2 is identity.
    """
    rad = np.asarray(rad, dtype=float)
    if not window or window < 2:
        return rad
    M = rad.shape[0]
    half = window // 2
    out = np.empty_like(rad)
    for i in range(M):
        lo = max(0, i - half)
        hi = min(M, i + half + 1)
        out[i] = np.median(rad[lo:hi], axis=0)
    return out


def _largest_contiguous(slices):
    best = (0, 0)
    cur_start = None
    for i, s in enumerate(slices):
        if s.polygon is not None and polygon_area(s.polygon) > 1e-9:
            if cur_start is None:
                cur_start = i
            if i - cur_start + 1 > best[1] - best[0]:
                best = (cur_start, i + 1)
        else:
            cur_start = None
    return slices[best[0]:best[1]]


def loft_slices_to_mesh(slices, n_radial=180, axial_median_rows=0):
    run = _largest_contiguous(slices)
    if len(run) < 2:
        raise ValueError("need at least two non-empty slices to build a mesh")

    angles = np.linspace(0, 2 * np.pi, n_radial, endpoint=False)
    dirs = np.column_stack([np.cos(angles), np.sin(angles)])
    centroids = [polygon_centroid(s.polygon) for s in run]
    rad = np.array([[ray_radius(s.polygon, c, a) for a in angles]
                    for s, c in zip(run, centroids)])   # (M, n_radial)
    rad = median_smooth_axial(rad, axial_median_rows)    # de-terrace, facet-safe
    rings = []
    for k, s in enumerate(run):
        pts = centroids[k] + rad[k][:, None] * dirs
        rings.append(np.column_stack([pts[:, 0], pts[:, 1],
                                      np.full(n_radial, s.z_mm)]))
    rings = np.array(rings)               # (M, n_radial, 3)
    M = len(rings)
    vertices = rings.reshape(-1, 3)

    faces = []
    for k in range(M - 1):
        for j in range(n_radial):
            j2 = (j + 1) % n_radial
            a = k * n_radial + j
            b = k * n_radial + j2
            c = (k + 1) * n_radial + j
            d = (k + 1) * n_radial + j2
            faces.append([a, b, d])
            faces.append([a, d, c])

    bottom_c = len(vertices)
    top_c = bottom_c + 1
    bc = polygon_centroid(run[0].polygon)
    bottom_center = np.array([bc[0], bc[1], rings[0, 0, 2]])
    tc = polygon_centroid(run[-1].polygon)
    top_center = np.array([tc[0], tc[1], rings[-1, 0, 2]])
    vertices = np.vstack([vertices, bottom_center, top_center])

    base = (M - 1) * n_radial
    for j in range(n_radial):
        j2 = (j + 1) % n_radial
        faces.append([bottom_c, j2, j])               # bottom cap
        faces.append([top_c, base + j, base + j2])    # top cap

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=True)
    mesh.fix_normals(multibody=False)
    return mesh
