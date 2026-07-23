import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.spatial import QhullError
from scipy.optimize import linprog


def affine_to_plane(theta_star, alpha, beta):
    m = 1.0 / np.sqrt(1.0 + alpha * alpha)
    a = m * np.cos(theta_star)
    b = -m * np.sin(theta_star)
    c = -alpha * m
    d = beta * m
    return float(a), float(b), float(c), float(d)


def plane_to_affine(plane):
    a, b, c, d = plane
    m = np.hypot(a, b)
    theta_star = np.arctan2(-b, a)          # (a,b)=(cos,-sin)*m
    alpha = -c / m
    beta = d / m
    return float(theta_star), float(alpha), float(beta)


def _interior_point(halfspaces):
    A = halfspaces[:, :-1]; b = -halfspaces[:, -1]
    norm = np.linalg.norm(A, axis=1, keepdims=True)
    A_ub = np.hstack([A, norm])
    c = np.zeros(A.shape[1] + 1); c[-1] = -1.0
    res = linprog(c, A_ub=A_ub, b_ub=b,
                  bounds=[(None, None)] * A.shape[1] + [(0, None)])
    if not res.success or res.x is None or res.x[-1] <= 0:
        raise ValueError("half-spaces do not bound an interior region")
    return res.x[:-1]


def planes_to_mesh(planes):
    hs = np.array([[a, b, c, -d] for (a, b, c, d) in planes], float)
    try:
        interior = _interior_point(hs)
        hi = HalfspaceIntersection(hs, interior)
        pts = hi.intersections
        hull = trimesh.Trimesh(vertices=pts).convex_hull
    except (QhullError, ValueError, IndexError) as exc:
        raise ValueError(f"half-spaces do not bound a closed region: {exc}")
    return hull, np.asarray(hull.vertices, float), np.asarray(hull.edges_unique, int)


def merge_planes(recs, merge_deg=6.0, d_reltol=0.02):
    cos_tol = np.cos(np.radians(merge_deg))
    scale = max((abs(r["plane"][3]) for r in recs), default=1.0) or 1.0
    d_tol = d_reltol * scale
    out = []
    for p in recs:
        a, b, c, d = p["plane"]; n = np.array([a, b, c])
        for q in out:
            qa, qb, qc, qd = q["plane"]
            if float(np.dot(n, [qa, qb, qc])) >= cos_tol and abs(d - qd) < d_tol:
                if p["rms"] < q["rms"]:
                    q.update(p)
                break
        else:
            out.append(dict(p))
    return out


def facet_rms(plane, samples, az_tol_deg=6.0, resid_tol_mm=0.05):
    """RMS of (beta+alpha*z) vs observed h over samples near the plane's
    azimuth where the plane is (nearly) the active tangent."""
    theta_star, alpha, beta = plane_to_affine(plane)
    dth = np.angle(np.exp(1j * (samples.theta - theta_star)))
    cols = np.where(np.abs(dth) <= np.radians(az_tol_deg))[0]
    resid = []
    for i in cols:
        sel = samples.valid[:, i]
        pred = beta + alpha * samples.z[sel]
        r = pred - samples.h[sel, i]
        resid.extend(r[np.abs(r) <= max(resid_tol_mm, 3*np.median(np.abs(r)) if r.size else resid_tol_mm)])
    if len(resid) < 4:
        return float("nan"), 0
    resid = np.asarray(resid)
    return float(np.sqrt(np.mean(resid**2))), int(resid.size)


def extremal_caps(samples, width_frac=0.3):
    """Table/culet caps: cap a z-extreme only if the silhouette there is wide
    (row radius > width_frac * girdle radius). A pointed culet (radius -> 0)
    gets no cap. Radius proxy = max right-edge support over all 360-deg views
    at that height; guarded so all-NaN (fully masked) rows emit no warning."""
    valid_row = samples.valid.any(axis=1)
    radius = np.full(samples.z.shape, np.nan)
    if valid_row.any():
        radius[valid_row] = np.nanmax(samples.h[valid_row], axis=1)
    ok = np.isfinite(radius) & valid_row
    if not ok.any():
        return []
    zv, rv = samples.z[ok], radius[ok]
    order = np.argsort(zv); zv, rv = zv[order], rv[order]
    girdle = float(np.max(rv))
    if girdle <= 0:
        return []
    dz = abs(zv[1] - zv[0]) if len(zv) > 1 else 1.0
    band = max(3, int(0.2 / max(dz, 1e-6)))
    caps = []
    if np.mean(rv[-band:]) > width_frac * girdle:
        caps.append(dict(plane=(0.0, 0.0, 1.0, float(zv[-1])), rms=0.0, source="cap"))
    if np.mean(rv[:band]) > width_frac * girdle:
        caps.append(dict(plane=(0.0, 0.0, -1.0, float(-zv[0])), rms=0.0, source="cap"))
    return caps
