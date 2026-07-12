# Facet Detection v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed soft-hull facet seeding with detection on the raw support function (per-view affine segmentation + cross-view clustering), so `method="facet"` recovers the REAL facets of gem04 instead of a rounded convex envelope.

**Architecture:** For each view, split the raw `H(z)` support column into affine segments (each segment = a facet trace; spike measured ~5 µm rms on gem04). Chain matching segments across neighbouring views clusters traces into facets; the chain's edge-on view gives θ\*. The existing exact refit (`fit_affine_support` → `plane_from_affine`) and half-space assembly (`_merge_planes` → `planes_to_polytope`) are reused unchanged. Table/culet handling becomes orientation-aware (scans are culet-up; the culet gets NO cap).

**Tech Stack:** Python 3.12, numpy (detection is pure numpy), existing scipy/trimesh back-end, pytest. Spec: `docs/superpowers/specs/2026-07-12-facet-detection-v2-design.md`.

## Global Constraints

- Detection front-end is pure numpy; no soft-hull, no scipy in the new functions.
- Frozen, reused unchanged: `fit_affine_support`, `plane_from_affine`, `_merge_planes`, `planes_to_polytope`, `_interior_point`, `support_maps`, pipeline dispatch, GUI entry, fallback semantics.
- `seed_facets` stays in the module (tested, harmless) but the facet path no longer calls it. `annotate_seed_z_extent` and the v1 seed-consuming body of `recover_planes` are REPLACED.
- Params: add `facet_seg_median_rows=9`, `facet_slope_jump=0.12`, `facet_min_seg_mm=0.25`, `facet_min_views=3`, `facet_slope_tol=0.15`, `facet_table_width_frac=0.3`; REMOVE `facet_view_search`, `facet_axial_cos` (v1-seed concepts). Keep `facet_min_inliers`, `facet_merge_deg`, `facet_fallback`.
- Full suite (currently 110 tests) must stay green at every commit that touches shared modules. The toy-gem e2e test (`test_facet_reconstruct.py`) is a REGRESSION gate — its tolerances must not be loosened.
- Venv for everything: `.venv/Scripts/python.exe -m pytest ...`
- Final acceptance is gem04 QUANTITATIVE (refit rms median ≤15 µm; extents within ~50 µm/axis of gem.stl; watertight; culet apex not capped) AND VISUAL (rendered comparison for user sign-off). Do not claim success from numbers alone.

---

### Task 1: Per-view affine segmentation (`segment_support`)

The productionized spike core: split one view's `H(z)` into affine segments.

**Files:**
- Modify: `gemscanner/reconstruction/facet_fit.py` (append)
- Test: `tests/reconstruction/test_facet_fit.py` (append)

**Interfaces:**
- Consumes: numpy only.
- Produces: `segment_support(z, h, median_rows=9, slope_jump=0.12, min_seg_mm=0.25, min_rows=8) -> list[dict]` with keys `z_lo, z_hi, alpha, beta, rms, n` (alpha/beta of `h = beta + alpha*z`, fit by least squares on the segment; rows sorted by ascending z internally; NaN rows dropped). Empty list if <5 finite rows.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/reconstruction/test_facet_fit.py
from gemscanner.reconstruction.facet_fit import segment_support

def test_segment_support_splits_piecewise_affine():
    # three affine pieces: slopes +1.5, -0.5, -1.2 over z bands of 2mm each
    z = np.linspace(-3, 3, 240)
    h = np.where(z < -1, 4.0 + 1.5 * (z + 1),
        np.where(z < 1, 4.0 - 0.5 * (z + 1), 3.0 - 1.2 * (z - 1)))
    rng = np.random.default_rng(0)
    h = h + rng.normal(0, 0.003, h.size)          # 3um noise
    h[40] += 0.08; h[150] -= 0.06                 # terracing-style outliers
    segs = segment_support(z, h)
    assert len(segs) == 3
    slopes = sorted(s["alpha"] for s in segs)
    assert abs(slopes[0] - (-1.2)) < 0.06
    assert abs(slopes[1] - (-0.5)) < 0.06
    assert abs(slopes[2] - 1.5) < 0.06
    for s in segs:
        assert s["rms"] < 0.01                    # fits are ~noise-level
        assert s["z_hi"] > s["z_lo"]

def test_segment_support_handles_nans_and_tiny_input():
    z = np.linspace(-1, 1, 50)
    h = 2.0 + 0.3 * z
    h[10:20] = np.nan
    segs = segment_support(z, h)
    assert len(segs) >= 1 and abs(segs[0]["alpha"] - 0.3) < 0.05
    assert segment_support(z[:3], h[:3]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q -k segment_support`
Expected: FAIL with `ImportError: cannot import name 'segment_support'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to gemscanner/reconstruction/facet_fit.py
# (uses fit_affine_support defined earlier in this module -- no new imports)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q`
Expected: PASS (all facet_fit tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_fit.py
git commit -m "feat(reconstruction): per-view affine segmentation of raw support H(z)"
```

---

### Task 2: Cross-view clustering (`cluster_segments`)

Chain matching segments across neighbouring views (with wraparound) into facet candidates.

**Files:**
- Modify: `gemscanner/reconstruction/facet_fit.py` (append)
- Test: `tests/reconstruction/test_facet_fit.py` (append)

**Interfaces:**
- Consumes: `segs_by_view: list[list[dict]]` (Task 1 output per view, index = view).
- Produces: `cluster_segments(segs_by_view, min_views=3, slope_tol=0.15, overlap_frac=0.5) -> list[dict]`, each `{"view": int (edge-on view), "seg": dict (that view's segment), "views": list[int] (chain members)}`. Edge-on = the chain member maximising z-span, tie-broken by minimum rms (the facet is fully tangent-visible at edge-on; neighbouring views see only its boundary arris). Chains wrap around view V-1 → 0. A segment joins at most one chain.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/reconstruction/test_facet_fit.py
from gemscanner.reconstruction.facet_fit import cluster_segments

def _seg(z_lo, z_hi, alpha, rms=0.005, n=20):
    return {"z_lo": z_lo, "z_hi": z_hi, "alpha": alpha,
            "beta": 0.0, "rms": rms, "n": n}

def test_cluster_segments_chains_across_views_with_wraparound():
    V = 12
    segs = [[] for _ in range(V)]
    # facet A: views 10,11,0,1,2 (wraps), z [0,2]; widest+cleanest at view 0
    for i, (span, rms) in zip([10, 11, 0, 1, 2],
                              [(1.6, .01), (1.8, .008), (2.0, .003),
                               (1.8, .008), (1.6, .01)]):
        segs[i].append(_seg(0.0, span, alpha=-0.5 + 0.01 * i % 3, rms=rms))
    # facet B: views 5,6,7, z [-2,-0.5], different slope
    for i in [5, 6, 7]:
        segs[i].append(_seg(-2.0, -0.5, alpha=1.2, rms=0.005))
    # noise: lone segment in view 3 (chain too short)
    segs[3].append(_seg(0.5, 1.0, alpha=0.9))
    chains = cluster_segments(segs, min_views=3)
    assert len(chains) == 2
    a = next(c for c in chains if c["seg"]["alpha"] < 0)
    b = next(c for c in chains if c["seg"]["alpha"] > 1)
    assert a["view"] == 0                      # max z-span member wins
    assert set(a["views"]) == {10, 11, 0, 1, 2}
    assert set(b["views"]) == {5, 6, 7}

def test_cluster_segments_separates_stacked_facets_same_azimuth():
    # step cut: two tiers at the SAME views, different z bands -> two chains
    V = 6
    segs = [[_seg(-2.0, -0.8, alpha=0.5), _seg(-0.6, 0.8, alpha=-0.9)]
            for _ in range(V)]
    chains = cluster_segments(segs, min_views=3)
    assert len(chains) == 2
    zl = sorted(c["seg"]["z_lo"] for c in chains)
    assert zl[0] == -2.0 and zl[1] == -0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q -k cluster_segments`
Expected: FAIL with `ImportError: cannot import name 'cluster_segments'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to gemscanner/reconstruction/facet_fit.py
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
    Each chain of >= min_views becomes a facet candidate; its edge-on view is
    the member with the largest z-span (facet fully visible), rms tie-break."""
    V = len(segs_by_view)
    used = [[False] * len(s) for s in segs_by_view]
    chains = []
    for i0 in range(V):
        for k0, seed in enumerate(segs_by_view[i0]):
            if used[i0][k0]:
                continue
            used[i0][k0] = True
            chain = [(i0, seed)]
            cur = seed
            for step in range(1, V):           # extend forward with wraparound
                i = (i0 + step) % V
                best = None
                for k, s in enumerate(segs_by_view[i]):
                    if used[i][k]:
                        continue
                    if (abs(s["alpha"] - cur["alpha"]) <= slope_tol and
                            _z_overlap_frac(cur, s) >= overlap_frac):
                        if best is None or s["rms"] < segs_by_view[i][best]["rms"]:
                            best = k
                if best is None:
                    break
                used[i][best] = True
                cur = segs_by_view[i][best]
                chain.append((i, cur))
            if len(chain) >= min_views:
                # edge-on: max z-span, tie-break min rms
                view, seg = max(chain, key=lambda t: (t[1]["z_hi"] - t[1]["z_lo"],
                                                      -t[1]["rms"]))
                chains.append({"view": view, "seg": seg,
                               "views": [i for i, _ in chain]})
    return chains
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_fit.py
git commit -m "feat(reconstruction): cross-view chaining of support segments into facet candidates"
```

---

### Task 3: Orientation-aware table plane (`find_table_planes`)

Detect which z-extreme is the flat table from the width profile; NEVER cap the culet.

**Files:**
- Modify: `gemscanner/reconstruction/facet_fit.py` (append)
- Test: `tests/reconstruction/test_facet_fit.py` (append)

**Interfaces:**
- Consumes: `SupportMaps` (`sm.z`, `sm.h_right`, `sm.h_left`, `sm.valid`).
- Produces: `find_table_planes(sm, table_width_frac=0.3) -> list[dict]` — 0, 1, or 2 plane dicts in the `recover_planes` format `{"plane": (0,0,±1,d), "rms": 0.0, "n_inliers": int, "source": "extremal"}`. An extreme qualifies as a table iff the mean silhouette width over its outermost ~0.2 mm exceeds `table_width_frac ×` the maximum width (girdle). A pointed extreme (~zero width) never qualifies.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/reconstruction/test_facet_fit.py
from types import SimpleNamespace
from gemscanner.reconstruction.facet_fit import find_table_planes

def _fake_sm(z, width):
    """width(z) profile -> minimal SupportMaps stand-in (1 'view')."""
    w = np.asarray(width, float)
    hr = (w / 2)[:, None]
    valid = np.isfinite(w)[:, None] & (w[:, None] > 0)
    hr = np.where(valid, hr, np.nan)
    return SimpleNamespace(z=np.asarray(z, float), h_right=hr, h_left=hr.copy(),
                           valid=valid, theta=np.array([0.0]))

def test_table_detected_at_wide_flat_bottom_only():
    # culet-up: pointed top (width->0), wide flat bottom (table)
    z = np.linspace(-3, 3, 120)                  # ascending z
    width = np.clip(4.0 - 1.2 * (z + 3) * 0, 0, None)
    width = np.where(z > 2.0, (3.0 - z) * 2.0, 4.0)   # top tapers to 0 at z=3
    planes = find_table_planes(_fake_sm(z, width))
    assert len(planes) == 1
    a, b, c, d = planes[0]["plane"]
    assert c == -1.0                             # bottom cap: -z <= d form
    assert abs(-d - z[0]) < 0.1                  # at z_min

def test_no_table_planes_when_both_ends_pointed():
    z = np.linspace(-2, 2, 80)
    width = 4.0 * (1 - np.abs(z) / 2)            # bicone: both ends -> 0
    assert find_table_planes(_fake_sm(z, width)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q -k table`
Expected: FAIL with `ImportError: cannot import name 'find_table_planes'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to gemscanner/reconstruction/facet_fit.py
def find_table_planes(sm, table_width_frac=0.3):
    """Orientation-aware extremal planes: cap a z-extreme ONLY if it is a wide
    flat table (silhouette width there > table_width_frac x girdle width).
    A pointed culet gets no cap -- its facets converge to the apex. Scans on
    this rig are culet-up (table at z_min), but detection is symmetric."""
    width = np.nanmean(sm.h_right + sm.h_left, axis=1)   # per-row diameter
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_fit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_fit.py
git commit -m "feat(reconstruction): orientation-aware table detection; never cap the culet"
```

---

### Task 4: Rewire `FacetReconstructor` + params (v2 path live)

Replace the seed-based `recover_planes` with segmentation+clustering; drop the soft-hull seed from the facet path; update params. The toy-gem e2e and pipeline tests are the regression gate.

**Files:**
- Modify: `gemscanner/reconstruction/base.py` (params)
- Modify: `gemscanner/reconstruction/facet_fit.py` (replace `recover_planes` body + `FacetReconstructor.reconstruct`; DELETE `annotate_seed_z_extent`, `_search_order`, `_nearest_view` if no longer referenced)
- Test: `tests/reconstruction/test_facet_reconstruct.py` (unchanged — regression), `tests/reconstruction/test_pipeline_facet.py` (unchanged — regression)

**Interfaces:**
- Consumes: Tasks 1–3 functions; frozen refit/assembly.
- Produces: `recover_planes(sm, params) -> list[dict]` (note: seeds arg REMOVED); `FacetReconstructor.reconstruct(dataset, params) -> trimesh.Trimesh` with `metadata["facets"]` exactly as today (planes, rms, vertices, edges). No soft-hull call anywhere in the facet path.

- [ ] **Step 1: Update params (base.py)**

Replace the facet param block with:

```python
    # facet method (method="facet"): unsupervised facet-plane recovery from
    # the raw support function (v2: per-view affine segmentation + cross-view
    # clustering; no soft-hull seed)
    facet_min_inliers: int = 12
    facet_merge_deg: float = 6.0
    facet_fallback: bool = True
    facet_seg_median_rows: int = 9     # z-median before segmentation
    facet_slope_jump: float = 0.12     # min slope jump |dH/dz| between adjacent facets
    facet_min_seg_mm: float = 0.25     # min segment z-span
    facet_min_views: int = 3           # min consecutive views per facet chain
    facet_slope_tol: float = 0.15      # slope match for cross-view chaining
    facet_table_width_frac: float = 0.3  # table plateau width vs girdle width
```

(`facet_view_search` and `facet_axial_cos` are deleted. Grep `gemscanner/ tests/ scripts/` first: the only consumers are the v1 `recover_planes` body being replaced in this task and possibly `scripts/validate_facet_gem04.py` — fix any hit.)

- [ ] **Step 2: Run regression tests to see them fail against the new params**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_reconstruct.py tests/reconstruction/test_pipeline_facet.py -q`
Expected: FAIL (old `recover_planes` references deleted params) — this is the RED for the rewire.

- [ ] **Step 3: Replace recover_planes and FacetReconstructor**

```python
# in gemscanner/reconstruction/facet_fit.py — REPLACE the old recover_planes
# (and delete annotate_seed_z_extent, _search_order, _nearest_view)
def recover_planes(sm, params):
    """v2: detect facets on the raw support maps (segment + chain), then refit
    each exactly. No soft-hull seed -- the smooth seed rounded real facets away
    (verified on gem04)."""
    V = len(sm.theta)
    segs_by_view = [
        segment_support(sm.z, sm.h_right[:, i],
                        median_rows=params.facet_seg_median_rows,
                        slope_jump=params.facet_slope_jump,
                        min_seg_mm=params.facet_min_seg_mm,
                        min_rows=params.facet_min_inliers)
        for i in range(V)
    ]
    chains = cluster_segments(segs_by_view,
                              min_views=params.facet_min_views,
                              slope_tol=params.facet_slope_tol)
    planes = []
    for ch in chains:
        i, seg = ch["view"], ch["seg"]
        mask = sm.valid[:, i] & (sm.z >= seg["z_lo"]) & (sm.z <= seg["z_hi"])
        alpha, beta, rms, n = fit_affine_support(
            sm.z, sm.h_right[:, i], mask,
            min_inliers=params.facet_min_inliers)
        if np.isnan(alpha):
            continue
        planes.append({"plane": plane_from_affine(sm.theta[i], alpha, beta),
                       "rms": rms, "n_inliers": n, "source": "tangent"})
    planes += find_table_planes(sm, params.facet_table_width_frac)
    return _merge_planes(planes, params.facet_merge_deg)


class FacetReconstructor:
    def reconstruct(self, dataset, params=None):
        params = params if params is not None else ReconstructionParams()
        sm = support_maps(dataset, params)
        planes = recover_planes(sm, params)
        if len(planes) < 4:
            raise ValueError("facet recovery failed: too few planes")
        mesh, verts, edges = planes_to_polytope(planes)
        mesh.metadata["facets"] = {
            "planes": [p["plane"] for p in planes],
            "rms": [p["rms"] for p in planes],
            "vertices": verts, "edges": edges}
        return mesh
```

Note: the `from gemscanner.reconstruction.soft_hull import SoftHullReconstructor` inside the old `reconstruct` is deleted with it — soft_hull remains only as the pipeline fallback / standalone method.

- [ ] **Step 4: Run the regression gates, then the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/reconstruction/test_facet_reconstruct.py tests/reconstruction/test_pipeline_facet.py -q`
Expected: PASS with the ORIGINAL tolerances (toy gem: median normal error <1°, volume <5%, watertight; pipeline: facet metadata present, ellipsoid falls back without crash). If the toy-gem test fails, DEBUG the detection (segments/chains) — do NOT touch the test. The toy gem's table is at z_max (table-up) and its culet apex at z_min; `find_table_planes` must cap only the top. This is also a much faster e2e than v1 (no soft-hull) — expect seconds, not minutes.
Then: `.venv/Scripts/python.exe -m pytest -q` — full suite green (note: `seed_facets` tests still pass; it remains exported).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/base.py gemscanner/reconstruction/facet_fit.py
git commit -m "feat(reconstruction): v2 facet detection live — segment+chain on raw support, no soft-hull seed"
```

---

### Task 5: gem04 validation with visual gate

Re-run the real-scan validation; deliver metrics AND a visual comparison for user sign-off. This is the acceptance test v1 skipped.

**Files:**
- Modify: `scripts/validate_facet_gem04.py` (report v2 metrics incl. per-facet rms from metadata; keep `HOLDER_MASK_ROWS = 705`)
- Create: `docs/superpowers/notes/2026-07-12-facet-v2-gem04-results.md`

**Interfaces:**
- Consumes: `reconstruct_dataset(SCAN, ReconstructionParams(method="facet", holder_mask_rows=705))`.
- Produces: printed metrics, `scans/gem04/gem_facet.stl` (overwritten), results note. The controller renders/hands the STL to the user for the visual gate.

- [ ] **Step 1: Update the script**

Extend `scripts/validate_facet_gem04.py` to print, from `mesh.metadata["facets"]`:
facet count (tangent vs extremal by rms==0), rms stats (median/max over tangent facets, µm), extents + per-axis delta vs `gem.stl` (µm), volume delta, watertight, vertex/edge counts, and the tilt of each tangent plane (`degrees(atan2(c, hypot(a,b)))`) sorted — to compare against the spike ladder (≈ −55° crown / +27/39/45/51/60° pavilion tiers). Also print whether any extremal plane has `c > 0` (a culet cap — must NOT be present on gem04).

- [ ] **Step 2: Run it**

Run: `.venv/Scripts/python.exe scripts/validate_facet_gem04.py`
Expected (quantitative gates): no fallback warning; tangent rms median ≤ 15 µm; extents within ~50 µm/axis of gem.stl; watertight; NO culet cap; tilt list shows the spike's tier structure. If gates fail, debug detection params (`facet_slope_jump`, `facet_min_views`, `facet_slope_tol`) against the spike output as reference — report honest numbers either way; do NOT tune to fake a pass.

- [ ] **Step 3: Write the results note**

`docs/superpowers/notes/2026-07-12-facet-v2-gem04-results.md`: all numbers, tilt ladder vs spike, tuning tried, limitations. Candid verdict.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_facet_gem04.py docs/superpowers/notes/2026-07-12-facet-v2-gem04-results.md
git commit -m "test(reconstruction): gem04 validation for facet detection v2"
```

- [ ] **Step 5: VISUAL GATE (controller + user)**

The controller renders `scans/gem04/gem_facet.stl` next to `scans/gem04/gem.stl` (or hands both to the user, who has an STL viewer) and asks the user to confirm the facet layout matches the real stone. **Merge is blocked until the user signs off.**

---

## Self-Review

**Spec coverage:** §4.1 support maps (existing, no task needed) ✓; §4.2 segmentation → Task 1 ✓; §4.3 clustering → Task 2 ✓; §4.4 refit (existing, wired in Task 4) ✓; §4.5 orientation-aware table/culet → Task 3 ✓; §4.6 assembly (existing) ✓; §5 params → Task 4 Step 1 ✓; §6 acceptance gates → Task 4 Step 4 (gate 1) + Task 5 (gates 2–3, visual sign-off) ✓.

**Placeholder scan:** none — all code steps carry complete code; commands carry expected outcomes.

**Type consistency:** segment dicts (`z_lo/z_hi/alpha/beta/rms/n`) produced by Task 1 are consumed by Task 2's `_z_overlap_frac`/chaining and Task 4's refit mask; chain dicts (`view/seg/views`) consumed in Task 4; `find_table_planes` returns the same plane-dict shape `recover_planes` appends and `_merge_planes` consumes; `plane_from_affine(theta, alpha, beta)` signature matches Task 4's call. ✓

**Known judgment point (documented in Task 2):** edge-on selection = max z-span then min rms (the spec said min-rms; z-span is the stronger edge-on signal since arris traces are also low-rms — this refines the spec, noted here deliberately). Executor should not re-litigate; Task 5 will confirm empirically on gem04.
