import numpy as np
from scratchpad.cleanroom.polytope import affine_to_plane, facet_rms


def _theilsen_slope(z, h):
    dz = z[:, None] - z[None, :]
    dh = h[:, None] - h[None, :]
    ok = np.abs(dz) > 1e-9
    return np.median(dh[ok] / dz[ok]) if ok.any() else np.nan


def _local_slope_grid(samples, slope_win):
    """Theil-Sen dh/dz per (row, view), from a sliding window along z at
    each fixed azimuth column. NaN where a column has too few valid rows."""
    H, V = samples.h.shape
    k = slope_win // 2
    grid = np.full((H, V), np.nan)
    for i in range(V):
        sel = np.where(samples.valid[:, i])[0]
        if len(sel) < slope_win + 1:
            continue
        zc = samples.z[sel]; hc = samples.h[sel, i]
        order = np.argsort(zc); zc, hc = zc[order], hc[order]
        rows = sel[order]
        for j in range(k, len(zc) - k):
            alpha = _theilsen_slope(zc[j-k:j+k+1], hc[j-k:j+k+1])
            if np.isfinite(alpha):
                grid[rows[j], i] = alpha
    return grid


def reconstruct_egi(samples, merge_deg=6.0, slope_win=9, min_arc_deg=6.0, rms_tol_mm=0.15):
    """EGI / Gauss-sphere facet recovery.

    Key geometric fact this relies on: for a convex polytope, the right-edge
    support h(theta, z) at a FIXED azimuth column, as a function of z, is
    exactly affine only *at* the column whose theta matches a real facet's
    own azimuth. At any other azimuth the observed "flat" region is really
    tracking the fixed 3D EDGE shared by the two neighbouring facets (a
    support-function vertex), which varies smoothly and continuously with
    theta between one true facet azimuth and the next -- so naively treating
    every column's local dh/dz as "the" facet normal at that column's theta
    produces a smeared continuum between facets, not 12 tight clusters
    (verified empirically: per-column normal error grows from 0 deg exactly
    at a facet azimuth to >15 deg at the midpoint azimuth between facets).

    The fix: aggregate the per-column slope into a grid over (z-row, view)
    and, independently at each z-row, keep only the views where |dh/dz| is a
    LOCAL MINIMUM across the (circular) azimuth axis. A true facet azimuth is
    a kink (one-sided derivatives of alpha(theta) disagree) that is a genuine
    local minimum of |alpha|; the in-between vertex-tracking azimuths are a
    smooth local MAXIMUM of |alpha| (a stationary point of one smooth
    sinusoid), so this azimuth-domain local-minimum filter cleanly separates
    real facets from edge/vertex artifacts before any clustering happens.

    A second failure mode survives the azimuth filter: near the girdle (z~0)
    the sliding z-window straddles the crown/pavilion transition, producing
    a handful of spurious near-horizontal clusters whose implied plane fits
    the data poorly (facet_rms much larger than a genuine facet's, since a
    genuine facet's plane matches its whole neighbourhood tightly while a
    girdle-crossing artifact's does not). `rms_tol_mm` gates on this: a
    cluster is only kept if its facet_rms is finite and <= rms_tol_mm, in
    addition to the existing nin>=4 support-count gate.
    """
    grid = _local_slope_grid(samples, slope_win)
    H, V = grid.shape
    normals = []      # (nx,ny,nz)
    carriers = []     # view_index provenance for offset solve
    for zi in range(H):
        row = grid[zi]
        mag = np.abs(row)
        valid = np.isfinite(mag)
        if not valid.any():
            continue
        for i in np.where(valid)[0]:
            im1, ip1 = (i - 1) % V, (i + 1) % V
            if not (valid[im1] and valid[ip1]):
                continue
            if mag[i] <= mag[im1] and mag[i] <= mag[ip1] and (mag[i] < mag[im1] or mag[i] < mag[ip1]):
                a, b, c, _d = affine_to_plane(samples.theta[i], row[i], 0.0)
                normals.append((a, b, c)); carriers.append(i)
    if not normals:
        return []
    normals = np.array(normals)
    # greedy angular clustering (area/count weighted by membership)
    cos_tol = np.cos(np.radians(merge_deg))
    clusters = []     # [accum_normal, count]
    order = np.arange(len(normals))
    for idx in order:
        n = normals[idx]
        for cl in clusters:
            ref = cl[0] / np.linalg.norm(cl[0])
            if float(n @ ref) >= cos_tol:
                cl[0] += n; cl[1] += 1
                break
        else:
            clusters.append([n.copy(), 1])
    min_count = max(3, int(min_arc_deg / 360.0 * len(normals) / 6))
    recs = []
    for accum, cnt in clusters:
        if cnt < min_count:
            continue
        nrm = accum / np.linalg.norm(accum)
        theta_star = np.arctan2(-nrm[1], nrm[0])
        alpha = -nrm[2] / np.hypot(nrm[0], nrm[1])
        # robust beta: pick nearest azimuth column, fit intercept at that slope
        dth = np.angle(np.exp(1j * (samples.theta - theta_star)))
        i = int(np.argmin(np.abs(dth)))
        sel = samples.valid[:, i]
        beta = float(np.median(samples.h[sel, i] - alpha * samples.z[sel]))
        plane = affine_to_plane(theta_star, alpha, beta)
        rms, nin = facet_rms(plane, samples)
        if nin >= 4 and np.isfinite(rms) and rms <= rms_tol_mm:
            recs.append(dict(plane=plane, rms=rms, source="egi"))
    return recs
