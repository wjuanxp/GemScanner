import numpy as np


def plane_from_affine(theta_star, alpha, beta):
    """(theta*, alpha, beta) -> unit plane (a,b,c,d), a*x+b*y+c*z = d.
    Support of an edge-on facet: H(z) = beta + alpha*z with alpha=-c/m,
    beta=d/m, m=sqrt(a^2+b^2). Convention n_i=(cos th, -sin th)."""
    m = 1.0 / np.sqrt(1.0 + alpha * alpha)
    c = -alpha * m
    a = m * np.cos(theta_star)
    b = -m * np.sin(theta_star)
    d = beta * m
    return float(a), float(b), float(c), float(d)


def _theilsen(z, h):
    n = len(z)
    if n < 2:
        return np.nan, np.nan
    # median of pairwise slopes (subsample pairs when large to stay cheap)
    idx = np.arange(n)
    if n > 120:
        idx = np.linspace(0, n - 1, 120).astype(int)
    zz, hh = z[idx], h[idx]
    dz = zz[:, None] - zz[None, :]
    dh = hh[:, None] - hh[None, :]
    ok = np.abs(dz) > 1e-9
    if not ok.any():                 # all z identical (degenerate) -> no slope
        return np.nan, np.nan
    slope = np.median(dh[ok] / dz[ok])
    intercept = np.median(hh - slope * zz)
    return float(slope), float(intercept)


def fit_affine_support(z, h, mask, min_inliers=8, resid_tol_mm=0.05):
    """Robust affine fit H=beta+alpha*z over masked/valid samples.
    Returns (alpha, beta, rms, n_inliers); alpha=nan if too few points."""
    z = np.asarray(z, float); h = np.asarray(h, float)
    sel = np.asarray(mask, bool) & np.isfinite(h)
    if sel.sum() < min_inliers:
        return np.nan, np.nan, np.nan, int(sel.sum())
    zz, hh = z[sel], h[sel]
    alpha, beta = _theilsen(zz, hh)
    if np.isnan(alpha):
        return np.nan, np.nan, np.nan, int(sel.sum())
    resid = np.abs(hh - (beta + alpha * zz))
    keep = resid <= max(resid_tol_mm, np.median(resid) * 3)
    if keep.sum() >= min_inliers:
        zz, hh = zz[keep], hh[keep]              # scope fit + rms to inliers
        A = np.column_stack([zz, np.ones(len(zz))])
        (alpha, beta), *_ = np.linalg.lstsq(A, hh, rcond=None)
    fit = beta + alpha * zz
    rms = float(np.sqrt(np.mean((hh - fit) ** 2)))   # rms over inliers only
    return float(alpha), float(beta), rms, int(keep.sum())


def seed_facets(mesh, merge_deg=8.0, min_area_frac=0.005):
    """Cluster mesh face normals (area-weighted) into distinct facet seeds."""
    normals = np.asarray(mesh.face_normals, float)
    areas = np.asarray(mesh.area_faces, float)
    order = np.argsort(areas)[::-1]
    cos_tol = np.cos(np.radians(merge_deg))
    clusters = []   # each: [sum_area, accum_normal(weighted)]
    for i in order:
        n = normals[i]; w = areas[i]
        for cl in clusters:
            ref = cl[1] / np.linalg.norm(cl[1])
            if float(np.dot(n, ref)) >= cos_tol:
                cl[0] += w; cl[1] += w * n
                break
        else:
            clusters.append([w, w * n.copy()])
    total = float(areas.sum())
    seeds = []
    for area_sum, accum in clusters:
        if area_sum < min_area_frac * total:
            continue
        nrm = accum / np.linalg.norm(accum)
        seeds.append({"normal": nrm,
                      "azimuth": float(np.arctan2(-nrm[1], nrm[0])),
                      "tilt": float(nrm[2]),
                      "area": float(area_sum)})
    seeds.sort(key=lambda s: s["area"], reverse=True)
    return seeds
