import numpy as np
from scratchpad.cleanroom.polytope import affine_to_plane, facet_rms


def _rolling_slope(z, h, win):
    """Local dh/dz at each sample of one column, via a centred least-squares
    window (closed form). NaN where the window would run off the end."""
    n = len(z)
    out = np.full(n, np.nan)
    k = max(2, win // 2)
    if n < 2 * k + 1:
        return out
    for j in range(k, n - k):
        zz = z[j - k:j + k + 1]
        hh = h[j - k:j + k + 1]
        zm = zz.mean()
        var = np.sum((zz - zm) ** 2)
        if var <= 1e-12:
            continue
        out[j] = np.sum((zz - zm) * (hh - hh.mean())) / var
    return out


def _slope_grid(samples, win_rows):
    """(H, V) grid of local dh/dz, computed per azimuth column over that
    column's valid rows only."""
    H, V = samples.h.shape
    grid = np.full((H, V), np.nan)
    for i in range(V):
        sel = np.flatnonzero(samples.valid[:, i])
        if sel.size < 5:
            continue
        grid[sel, i] = _rolling_slope(samples.z[sel], samples.h[sel, i], win_rows)
    return grid


def _facet_azimuth_mask(grid, step_cols, slack=1.0):
    """True where |dh/dz| is a LOCAL MINIMUM along the azimuth axis.

    Geometric basis (the same kink principle Candidate C uses, and the reason
    a naive per-column fit fails): at a real facet's own azimuth the support
    column h(.,z) is exactly affine, so |dh/dz| bottoms out; at any other
    azimuth the apparently-flat column is tracking the shared 3D EDGE between
    two neighbouring facets, whose |dh/dz| is strictly larger and peaks
    midway between facets. Comparing against columns +/- step_cols away (a
    step comparable to real facet spacing, NOT a few degrees -- a too-small
    step compares a facet against itself and passes everything) isolates the
    true facet azimuths."""
    a = np.abs(grid)
    left = np.roll(a, step_cols, axis=1)
    right = np.roll(a, -step_cols, axis=1)
    ok = np.isfinite(a) & np.isfinite(left) & np.isfinite(right)
    return ok & (a <= slack * left) & (a <= slack * right)


def reconstruct_ransac(samples, n_iter=2000, win_rows=9, resid_tol_mm=0.02,
                       min_span_mm=0.35, kink_step_deg=15.0, rms_tol_mm=0.15,
                       seed=0, max_stale=400):
    """Random-hypothesis (RANSAC-style) facet recovery from support samples.

    Each iteration draws a random unclaimed (row, azimuth) seed, takes the
    local slope alpha there, and then SNAPS the offset to the support
    envelope of that azimuth column:

        beta = max_z ( h(theta*, z) - alpha * z )

    That snap is what makes this method safe. For a convex body B the exact
    3D support in the direction n=(a,b,c) is S(n) = max_z [c z + m h(theta*,z)]
    with m = |(a,b)|, so snapping beta to that maximum makes the hypothesised
    plane EXACTLY TANGENT to B rather than an interior least-squares fit.
    Every accepted plane is therefore a true supporting plane, and an
    intersection of supporting planes is always a superset of B -- it can
    never carve real volume away, however many extra planes are accepted.
    (A plain windowed least-squares fit, by contrast, cuts into the body and
    is what makes an unguarded RANSAC destroy the shape.)

    A hypothesis is accepted only if:
      - its azimuth is a facet azimuth by the kink test (see
        `_facet_azimuth_mask`) -- rejects edge/vertex-tracking hypotheses,
        which are tangent but whose normals are blends of two real facet
        normals, and
      - the plane's contact set (rows within resid_tol_mm of the envelope)
        spans at least min_span_mm in z -- a facet touches along a band,
        a vertex touches at a point, and
      - its `facet_rms` over the neighbourhood of its own azimuth is finite
        and <= rms_tol_mm. Near the girdle a window can straddle the crown /
        pavilion transition and yield a plausible-looking but blended slope;
        those hypotheses fit their whole azimuth neighbourhood poorly and are
        rejected here (the same discriminator, and the same tolerance, that
        Candidate C needs for the identical artifact).

    Accepted contact rows are claimed so the greedy loop moves on to
    unexplained parts of the surface. Returns tangent facets only; the
    caller adds table/culet caps."""
    rng = np.random.default_rng(seed)
    H, V = samples.h.shape
    grid = _slope_grid(samples, win_rows)
    deg_per_col = 360.0 / max(V, 1)
    step_cols = max(1, int(round(kink_step_deg / max(deg_per_col, 1e-9))))
    mask = _facet_azimuth_mask(grid, step_cols)
    claimed = np.zeros((H, V), bool)
    recs = []
    stale = 0
    for _ in range(n_iter):
        if stale > max_stale:
            break
        cand = np.flatnonzero((mask & ~claimed).ravel())
        if cand.size == 0:
            break
        pick = int(rng.choice(cand))
        r, i = divmod(pick, V)
        alpha = grid[r, i]
        if not np.isfinite(alpha):
            claimed[r, i] = True
            stale += 1
            continue
        sel = samples.valid[:, i]
        zc = samples.z[sel]
        hc = samples.h[sel, i]
        # snap to the support envelope of this column => exactly tangent
        beta = float(np.max(hc - alpha * zc))
        resid = (beta + alpha * zc) - hc          # >= 0 by construction
        contact = resid <= resid_tol_mm
        if contact.sum() < 3:
            claimed[r, i] = True
            stale += 1
            continue
        span = float(zc[contact].max() - zc[contact].min())
        if span < min_span_mm:
            claimed[r, i] = True
            stale += 1
            continue
        plane = affine_to_plane(samples.theta[i], float(alpha), beta)
        rms, _nin = facet_rms(plane, samples)
        if not np.isfinite(rms) or rms > rms_tol_mm:
            claimed[r, i] = True
            stale += 1
            continue
        recs.append(dict(plane=plane, rms=float(rms), source="ransac"))
        rows = np.flatnonzero(sel)[contact]
        claimed[rows, i] = True
        stale = 0
    return recs
