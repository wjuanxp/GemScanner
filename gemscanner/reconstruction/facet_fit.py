import math
import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from gemscanner.reconstruction.support import support_maps
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.geometry.polygon import polygon_centroid


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


def facet_azimuths(slices, min_edge_mm=0.35, ext_edge_mm=0.15, bin_deg=2.0,
                   min_total_len=1.0, min_slices=3):
    """Cluster cross-section polygon edges across z by outward-normal azimuth.

    The strip slices' polygon edges ARE the facet traces: each real facet
    appears as a >= min_edge_mm edge at its azimuth in every slice of its
    z-band. Edges shorter than min_edge_mm are carve-quantization noise at
    polygon corners (length ~ R * view-step) and are skipped for the purposes
    of SEEDING a family (deciding which azimuths are real facets).

    Once a family is seeded, its returned z-band is EXTENDED using the
    shorter edges (>= ext_edge_mm) that fall in the family's azimuth bins --
    this recovers coverage near the culet, where a real facet's edges shrink
    below min_edge_mm well before the facet itself ends. Returns
    [(azimuth_rad, z_lo, z_hi)] families (length-weighted circular mean)."""
    nbins = int(round(360.0 / bin_deg))
    acc_len = np.zeros(nbins)
    acc_x = np.zeros(nbins); acc_y = np.zeros(nbins)
    zs = [[] for _ in range(nbins)]
    zs_ext = [[] for _ in range(nbins)]
    for s in slices:
        poly = s.polygon
        if poly is None or len(poly) < 3:
            continue
        c = polygon_centroid(poly)
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            e = b - a
            L = float(np.hypot(*e))
            if L < ext_edge_mm:
                continue
            nrm = np.array([e[1], -e[0]]) / L
            if nrm @ (0.5 * (a + b) - c) < 0:
                nrm = -nrm
            az = math.atan2(-nrm[1], nrm[0])      # n_i=(cos,-sin) convention
            k = int(round((math.degrees(az) % 360) / bin_deg)) % nbins
            zs_ext[k].append(s.z_mm)
            if L < min_edge_mm:
                continue
            acc_len[k] += L
            acc_x[k] += L * math.cos(az)
            acc_y[k] += L * math.sin(az)
            zs[k].append(s.z_mm)
    fams = []
    used = np.zeros(nbins, bool)
    for k in np.argsort(acc_len)[::-1]:
        if used[k] or acc_len[k] <= 0:
            continue
        members = [k]; used[k] = True
        for d in (-1, +1):                        # merge adjacent nonzero bins
            j = (k + d) % nbins
            while acc_len[j] > 0 and not used[j]:
                members.append(j); used[j] = True
                j = (j + d) % nbins
        tot = sum(acc_len[m] for m in members)
        allz = sorted(z for m in members for z in zs[m])
        if tot < min_total_len or len(allz) < min_slices:
            continue
        extz = sorted(z for m in members for z in zs_ext[m])
        ax = sum(acc_x[m] for m in members); ay = sum(acc_y[m] for m in members)
        fams.append((math.atan2(ay, ax), float(extz[0]), float(extz[-1])))
    return fams


_FINE_ROWS = 7          # two-scale pass 2: fine Theil-Sen window (rows)
_FINE_MIN_ROWS = 5      # two-scale pass 2: min inliers for a fine-window fit
_FINE_MIN_MM = 0.12     # two-scale pass 2: min unclaimed z-gap worth re-segmenting


def girdle_band(sm, eps_mm=0.04):
    """z-band of the width-profile plateau: a faceted girdle is a ring of
    near-vertical facets, so unlike a rounded girdle, the true widest band of
    the stone has ~constant width across several rows (vs a single peak row).
    Returns (z_lo, z_hi) bracketing rows within eps_mm of the max width, or
    None if fewer than 5 such rows exist (same warning-free width computation
    as find_table_planes -- np.nansum/np.nan_to_num avoids all-NaN-slice
    warnings)."""
    diam = sm.h_right + sm.h_left
    counts = np.isfinite(diam).sum(axis=1)
    width = np.where(counts > 0,
                     np.nansum(np.nan_to_num(diam), axis=1)
                     / np.maximum(counts, 1), np.nan)
    ok = np.isfinite(width)
    if not ok.any():
        return None
    zv, wv = sm.z[ok], width[ok]
    wmax = float(np.nanmax(wv))
    band = wv >= wmax - eps_mm
    zb = zv[band]
    if zb.size < 5:
        return None
    return float(zb.min()), float(zb.max())


def girdle_planes(sm, fams, band, min_rows=5):
    """Per-azimuth-family affine fit restricted to the girdle band -- recovers
    the (typically many, near-vertical) girdle facets a user has confirmed are
    faceted rather than rounded on this stone. `fams` supplies the azimuths
    (from facet_azimuths); each is refit fresh here over just the girdle
    rows, independent of whatever z-band that family's tangent tiers used."""
    if band is None:
        return []
    z_lo, z_hi = band
    out = []
    for az, _, _ in fams:
        d = np.angle(np.exp(1j * (sm.theta - az)))
        i = int(np.argmin(np.abs(d)))
        mask = sm.valid[:, i] & (sm.z >= z_lo) & (sm.z <= z_hi)
        alpha, beta, rms, n = fit_affine_support(sm.z, sm.h_right[:, i], mask,
                                                 min_inliers=min_rows)
        if np.isnan(alpha):
            continue
        out.append({"plane": plane_from_affine(sm.theta[i], alpha, beta),
                    "rms": rms, "n_inliers": n, "source": "girdle"})
    return out


def recover_planes(sm, slices, params):
    """v2.3: facet azimuths from cross-slice polygon edges (extended near the
    culet via facet_azimuths' ext_edge_mm), then per-azimuth affine tier
    segmentation of the raw support column at two scales -- a coarse pass
    (params.facet_seg_median_rows) followed by a fine pass (_FINE_ROWS) over
    any unclaimed z-gaps wider than _FINE_MIN_MM, which recovers thin tiers
    the coarse window smooths over -- plus a dedicated girdle-band pass
    (girdle_band/girdle_planes) that refits each azimuth over the width-
    profile plateau to recover near-vertical girdle facets. No soft-hull seed
    (it rounded real facets away -- verified on gem04); no cross-view
    chaining (chains conflate facet and arris traces -- verified on the toy
    gate). All candidate planes (tangent tiers + girdle + table/culet caps)
    are deduplicated in a single final _merge_planes call."""
    fams = facet_azimuths(slices, min_edge_mm=params.facet_min_edge_mm)
    planes = []
    for az, z_lo, z_hi in fams:
        d = np.angle(np.exp(1j * (sm.theta - az)))   # wrapped difference
        i = int(np.argmin(np.abs(d)))
        band = sm.valid[:, i] & (sm.z >= z_lo - 0.1) & (sm.z <= z_hi + 0.1)
        segs = segment_support(sm.z[band], sm.h_right[band, i],
                               median_rows=params.facet_seg_median_rows,
                               slope_jump=params.facet_slope_jump,
                               min_seg_mm=params.facet_min_seg_mm,
                               min_rows=params.facet_min_inliers)
        # ---- pass 2: fine-window segmentation of unclaimed z-gaps ----
        zb = np.sort(sm.z[band])
        claimed = [(s["z_lo"], s["z_hi"]) for s in segs]
        gaps = []
        cur = zb[0] if len(zb) else None
        for lo, hi in sorted(claimed):
            if cur is not None and lo - cur > _FINE_MIN_MM:
                gaps.append((cur, lo))
            cur = max(cur, hi) if cur is not None else hi
        if cur is not None and len(zb) and zb[-1] - cur > _FINE_MIN_MM:
            gaps.append((cur, zb[-1]))
        for glo, ghi in gaps:
            gsel = band & (sm.z >= glo) & (sm.z <= ghi)
            segs += segment_support(sm.z[gsel], sm.h_right[gsel, i],
                                    median_rows=_FINE_ROWS,
                                    slope_jump=params.facet_slope_jump,
                                    min_seg_mm=_FINE_MIN_MM,
                                    min_rows=_FINE_MIN_ROWS)
        for seg in segs:
            mask = sm.valid[:, i] & (sm.z >= seg["z_lo"]) & (sm.z <= seg["z_hi"])
            alpha, beta, rms, n = fit_affine_support(
                sm.z, sm.h_right[:, i], mask,
                min_inliers=min(params.facet_min_inliers, _FINE_MIN_ROWS))
            if np.isnan(alpha):
                continue
            planes.append({"plane": plane_from_affine(sm.theta[i], alpha, beta),
                           "rms": rms, "n_inliers": n, "source": "tangent"})
    planes += find_table_planes(sm, params.facet_table_width_frac)
    planes += girdle_planes(sm, fams, girdle_band(sm))
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


def segment_support(z, h, median_rows=9, slope_jump=0.12,
                    min_seg_mm=0.25, min_rows=8):
    """Split one view's raw support column H(z) into affine segments.

    Each segment is a candidate facet trace (a facet's support is affine in z
    while it is the active tangent). Both stages are rank-robust with NO
    pre-filtering of the signal (a blanket median staircases sloped columns;
    despiking is edge/ramp-biased -- both verified failure modes):
      - local slope via sliding-window Theil-Sen (median of pairwise slopes:
        single outliers corrupt a minority of pairs),
      - breaks at local maxima of the two-sided slope jump
        |slope(i+k) - slope(i-k)| above `slope_jump`,
      - a transition zone of k rows around each break is trimmed, then each
        segment is fit with the frozen robust fit_affine_support (rms over
        inliers).
    Returns [{z_lo, z_hi, alpha, beta, rms, n}] sorted by z_lo; [] if fewer
    than 5 finite samples."""
    z = np.asarray(z, float); h = np.asarray(h, float)
    ok = np.isfinite(h) & np.isfinite(z)
    z, h = z[ok], h[ok]
    if z.size < 5:
        return []
    order = np.argsort(z)
    z, h = z[order], h[order]
    n = len(z)
    k = max(2, median_rows // 2)

    def _fit(i0, i1):
        m = np.zeros(n, bool); m[i0:i1] = True
        alpha, beta, rms, nin = fit_affine_support(
            z, h, m, min_inliers=max(4, min_rows))
        if np.isnan(alpha) or (z[i1 - 1] - z[i0]) < min_seg_mm:
            return None
        return {"z_lo": float(z[i0]), "z_hi": float(z[i1 - 1]),
                "alpha": float(alpha), "beta": float(beta),
                "rms": float(rms), "n": int(nin)}

    if n < 4 * k + 2:                      # too short to segment: one fit
        s = _fit(0, n)
        return [s] if s else []

    slope = np.zeros(n)                    # sliding-window Theil-Sen slope
    for i in range(k, n - k):
        zz = z[i - k:i + k + 1]; hh = h[i - k:i + k + 1]
        dzm = zz[:, None] - zz[None, :]
        dhm = hh[:, None] - hh[None, :]
        sel = dzm > 1e-12
        slope[i] = np.median(dhm[sel] / dzm[sel])
    slope[:k] = slope[k]; slope[n - k:] = slope[n - k - 1]

    jump = np.zeros(n)
    jump[2 * k:n - 2 * k] = np.abs(slope[3 * k:n - k] - slope[k:n - 3 * k])
    above = jump > slope_jump
    breaks = []
    i = 0
    while i < n:                           # one break per contiguous run
        if above[i]:
            j = i
            while j < n and above[j]:
                j += 1
            breaks.append(i + int(np.argmax(jump[i:j])))
            i = j
        else:
            i += 1

    segs = []
    prev = 0
    for b in breaks:
        s = _fit(prev, max(prev, b - k))   # trim transition zone
        if s:
            segs.append(s)
        prev = b + k
    s = _fit(prev, n)
    if s:
        segs.append(s)
    return segs


def _z_overlap_frac(s, t):
    lo = max(s["z_lo"], t["z_lo"]); hi = min(s["z_hi"], t["z_hi"])
    if hi <= lo:
        return 0.0
    return (hi - lo) / min(s["z_hi"] - s["z_lo"], t["z_hi"] - t["z_lo"])


def cluster_segments(segs_by_view, min_views=3, slope_tol=0.15,
                     overlap_frac=0.5):
    """Chain matching affine segments across neighbouring views (wraparound).

    A real facet is tangent-visible over a contiguous azimuth arc, so its
    trace persists across neighbouring views with similar slope and z-band.
    Chains grow in BOTH directions from the seed view (forward-only chaining
    splits arcs that wrap past the seed -- verified failure). Each chain of
    >= min_views becomes a facet candidate; its edge-on view is the member
    with the largest z-span (facet fully visible), rms tie-break."""
    V = len(segs_by_view)
    used = [[False] * len(s) for s in segs_by_view]
    chains = []

    def _match(i, cur):
        best = None
        for k, s in enumerate(segs_by_view[i]):
            if used[i][k]:
                continue
            if (abs(s["alpha"] - cur["alpha"]) <= slope_tol and
                    _z_overlap_frac(cur, s) >= overlap_frac):
                if best is None or s["rms"] < segs_by_view[i][best]["rms"]:
                    best = k
        return best

    for i0 in range(V):
        for k0, seed in enumerate(segs_by_view[i0]):
            if used[i0][k0]:
                continue
            used[i0][k0] = True
            chain = [(i0, seed)]
            cur = seed
            for step in range(1, V):           # extend forward with wraparound
                i = (i0 + step) % V
                b = _match(i, cur)
                if b is None:
                    break
                used[i][b] = True
                cur = segs_by_view[i][b]
                chain.append((i, cur))
            cur = seed
            for step in range(1, V - len(chain) + 1):   # extend backward
                i = (i0 - step) % V
                b = _match(i, cur)
                if b is None:
                    break
                used[i][b] = True
                cur = segs_by_view[i][b]
                chain.insert(0, (i, cur))
            if len(chain) >= min_views:
                # edge-on: max z-span, tie-break min rms
                view, seg = max(chain, key=lambda t: (t[1]["z_hi"] - t[1]["z_lo"],
                                                      -t[1]["rms"]))
                chains.append({"view": view, "seg": seg,
                               "views": [i for i, _ in chain]})
    return chains


def find_table_planes(sm, table_width_frac=0.3):
    """Orientation-aware extremal planes: cap a z-extreme ONLY if it is a wide
    flat table (silhouette width there > table_width_frac x girdle width).
    A pointed culet gets no cap -- its facets converge to the apex. Scans on
    this rig are culet-up (table at z_min), but detection is symmetric."""
    diam = sm.h_right + sm.h_left                        # per-row, per-view
    counts = np.isfinite(diam).sum(axis=1)
    width = np.where(counts > 0,                         # nanmean w/o the
                     np.nansum(np.nan_to_num(diam), axis=1)
                     / np.maximum(counts, 1), np.nan)    # empty-slice warning
    ok = np.isfinite(width) & sm.valid.any(axis=1)
    if not ok.any():
        return []
    zv, wv = sm.z[ok], width[ok]
    girdle_w = float(np.nanmax(wv))
    if girdle_w <= 0:
        return []
    n_val = int(sm.valid.any(axis=1).sum())
    planes = []
    order = np.argsort(zv)
    zv, wv = zv[order], wv[order]
    band = max(3, int(0.2 / max(abs(zv[1] - zv[0]), 1e-6)))  # ~0.2mm of rows
    if np.nanmean(wv[-band:]) > table_width_frac * girdle_w:  # top is flat
        planes.append({"plane": (0.0, 0.0, 1.0, float(zv[-1])),
                       "rms": 0.0, "n_inliers": n_val, "source": "extremal"})
    if np.nanmean(wv[:band]) > table_width_frac * girdle_w:   # bottom is flat
        planes.append({"plane": (0.0, 0.0, -1.0, float(-zv[0])),
                       "rms": 0.0, "n_inliers": n_val, "source": "extremal"})
    return planes


class FacetReconstructor:
    def reconstruct(self, dataset, params=None):
        from gemscanner.reconstruction.strip_intersection import (
            StripIntersectionReconstructor)
        params = params if params is not None else ReconstructionParams()
        sm = support_maps(dataset, params)
        slices = StripIntersectionReconstructor().slice_cross_sections(
            dataset, params)
        planes = recover_planes(sm, slices, params)
        if len(planes) < 4:
            raise ValueError("facet recovery failed: too few planes")
        mesh, verts, edges = planes_to_polytope(planes)
        mesh.metadata["facets"] = {
            "planes": [p["plane"] for p in planes],
            "rms": [p["rms"] for p in planes],
            "vertices": verts, "edges": edges}
        return mesh
