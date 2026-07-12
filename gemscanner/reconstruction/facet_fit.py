import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from gemscanner.reconstruction.support import support_maps
from gemscanner.reconstruction.base import ReconstructionParams


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


def _nearest_view(theta, az):
    d = np.angle(np.exp(1j * (theta - az)))   # wrapped difference
    return int(np.argmin(np.abs(d)))


def _search_order(radius):
    """di offsets ordered by increasing distance from 0: 0,-1,+1,-2,+2,..."""
    order = [0]
    for k in range(1, radius + 1):
        order += [-k, k]
    return order


def annotate_seed_z_extent(mesh, seeds, merge_deg):
    """Attach each seed's own z-range (from the seed-mesh faces that cluster into
    it) so recover_planes can restrict the affine fit to that facet's own tier.
    A tangent facet's support is affine in z only across its OWN z-extent -- a
    view column mixes girdle/crown/pavilion tiers (each with a different slope)
    over the object's full height, so fitting the whole column washes out the
    true per-facet slope. This only reads the mesh already built by seed_facets;
    it does not alter that function."""
    cos_tol = np.cos(np.radians(merge_deg))
    normals = np.asarray(mesh.face_normals, float)
    verts = np.asarray(mesh.vertices, float)
    faces = np.asarray(mesh.faces)
    for s in seeds:
        match = normals @ s["normal"] >= cos_tol
        if not match.any():
            continue
        zs = verts[faces[match]][:, :, 2]
        s["z_lo"], s["z_hi"] = float(zs.min()), float(zs.max())
    return seeds


def recover_planes(sm, seeds, params):
    """Refit each seed to an exact plane on the raw support maps; add table/culet."""
    planes = []
    for s in seeds:
        if abs(s["tilt"]) > params.facet_axial_cos:      # near-axial -> extremal
            continue
        i0 = _nearest_view(sm.theta, s["azimuth"])
        zlo, zhi = s.get("z_lo"), s.get("z_hi")
        best = None
        for di in _search_order(params.facet_view_search):
            i = (i0 + di) % len(sm.theta)
            mask = sm.valid[:, i]
            if zlo is not None:
                mask = mask & (sm.z >= zlo) & (sm.z <= zhi)
            alpha, beta, rms, n = fit_affine_support(
                sm.z, sm.h_right[:, i], mask,
                min_inliers=params.facet_min_inliers)
            if np.isnan(alpha):
                continue
            # take the first (nearest-to-seed-azimuth) valid fit: within a
            # facet's own tier, views a couple of steps away from i0 can land
            # in a neighbouring vertex's normal cone and report a deceptively
            # similar (or even lower) rms, so rms alone cannot be trusted to
            # pick the right view -- proximity to the seed azimuth is the
            # reliable signal.
            best = (rms, sm.theta[i], alpha, beta, n)
            break
        if best is None:
            continue
        rms, th, alpha, beta, n = best
        planes.append({"plane": plane_from_affine(th, alpha, beta),
                       "rms": rms, "n_inliers": n, "source": "tangent"})
    # table (top) and culet (bottom) as extremal-z horizontal planes
    zval = sm.z[np.where(sm.valid.any(axis=1))[0]]
    if zval.size:
        planes.append({"plane": (0.0, 0.0, 1.0, float(zval.max())),
                       "rms": 0.0, "n_inliers": int(sm.valid.any(axis=1).sum()),
                       "source": "extremal"})
        planes.append({"plane": (0.0, 0.0, -1.0, float(-zval.min())),
                       "rms": 0.0, "n_inliers": int(sm.valid.any(axis=1).sum()),
                       "source": "extremal"})
    return _merge_planes(planes, params.facet_merge_deg)


def _merge_planes(planes, merge_deg, d_reltol=0.02):
    # d-tolerance is RELATIVE to gem scale (max |offset|) so merging works on
    # any-sized stone -- a fixed mm threshold would over/under-merge on gem04.
    cos_tol = np.cos(np.radians(merge_deg))
    scale = max((abs(p["plane"][3]) for p in planes), default=1.0) or 1.0
    d_tol = d_reltol * scale
    out = []
    for p in planes:
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


def _interior_point(halfspaces):
    """Chebyshev centre: maximise the inscribed-ball radius via linprog."""
    A = halfspaces[:, :-1]; b = -halfspaces[:, -1]
    norm = np.linalg.norm(A, axis=1, keepdims=True)
    A_ub = np.hstack([A, norm])
    c = np.zeros(A.shape[1] + 1); c[-1] = -1.0     # maximise radius
    res = linprog(c, A_ub=A_ub, b_ub=b, bounds=[(None, None)] * A.shape[1] + [(0, None)])
    if not res.success or res.x is None or res.x[-1] <= 0:
        # no strictly-interior point => planes don't bound a closed region
        # (a facet is missing). Clean signal for the Task 7 fallback.
        raise ValueError("facet half-spaces do not bound an interior region")
    return res.x[:-1]


def planes_to_polytope(planes):
    """Intersect facet half-spaces (a*x+b*y+c*z <= d) into a convex polytope."""
    # scipy halfspace form: A x + b <= 0  =>  [a,b,c, -d]
    hs = np.array([[a, b, c, -d] for (a, b, c, d) in
                   [p["plane"] for p in planes]], float)
    interior = _interior_point(hs)
    hi = HalfspaceIntersection(hs, interior)
    pts = hi.intersections
    hull = trimesh.Trimesh(vertices=pts).convex_hull
    edges = hull.edges_unique
    return hull, np.asarray(hull.vertices, float), np.asarray(edges, int)


class FacetReconstructor:
    def reconstruct(self, dataset, params=None):
        params = params if params is not None else ReconstructionParams()
        from gemscanner.reconstruction.soft_hull import SoftHullReconstructor
        seed_mesh = SoftHullReconstructor().reconstruct(dataset, params)
        seeds = seed_facets(seed_mesh, merge_deg=params.facet_merge_deg)
        seeds = annotate_seed_z_extent(seed_mesh, seeds, params.facet_merge_deg)
        sm = support_maps(dataset, params)
        planes = recover_planes(sm, seeds, params)
        if len(planes) < 4:
            raise ValueError("facet recovery failed: too few planes")
        mesh, verts, edges = planes_to_polytope(planes)
        mesh.metadata["facets"] = {
            "planes": [p["plane"] for p in planes],
            "vertices": verts, "edges": edges}
        return mesh
