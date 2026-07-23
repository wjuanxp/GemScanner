# Clean-room silhouette → faceted-gemstone bake-off — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Independently (clean-room) reconstruct a faceted convex-polytope gemstone from turntable silhouettes via three distinct algorithms, bake them off on gem04 against the shipped v2.3 benchmark, and produce a survey/results note with a recommendation.

**Architecture:** All prototypes live under `scratchpad/cleanroom/` and import **only** `gemscanner.storage.dataset`, `gemscanner.vision.silhouette`, and `gemscanner.coords` (I/O + silhouette + calibration). Everything from support samples → mesh is rebuilt independently. A shared front-end builds support samples `h(θ,z)`; a shared back-end turns half-spaces into a watertight polytope and scores facet fit; three candidate modules recover facet planes by different mechanisms (RANSAC / dual-convex / EGI); a bake-off harness runs all three + a space-carving control + the v2.3 benchmark on gem04 and emits a metrics table, a PIL comparison render, and a results note.

**Tech Stack:** Python 3.12, numpy, scipy (`spatial.HalfspaceIntersection`, `optimize.linprog`, `ndimage.median_filter`), trimesh, opencv (via existing silhouette code), Pillow (render). No matplotlib/pyglet (absent in venv). Run everything with `.venv/Scripts/python.exe`.

## Global Constraints

- **Clean-room import rule:** modules under `scratchpad/cleanroom/` may import from `gemscanner.storage.dataset`, `gemscanner.vision.silhouette`, `gemscanner.coords` ONLY. They must NOT import `gemscanner.reconstruction.*` (except the bake-off harness, which may call the shipped pipeline strictly to produce the control and benchmark meshes — clearly labelled).
- **No changes** to `gemscanner/` in this investigation. All new code under `scratchpad/cleanroom/`.
- **Orthographic** projection is assumed (verified: `coords.column_to_projection` is a linear `mm_per_px` scale).
- **Plane convention** (frozen across all tasks): a plane is a 4-tuple `(a, b, c, d)` meaning the half-space `a*x + b*y + c*z <= d`, with `(a,b,c)` a **unit** outward normal. Horizontal azimuth convention matches the shipped code: `(a,b) ∝ (cos θ*, −sin θ*)`. Affine support form: `H(z) = β + α·z` with `m = 1/sqrt(1+α²)`, `a = m·cosθ*`, `b = −m·sinθ*`, `c = −α·m`, `d = β·m`.
- **gem04 rig calibration:** `holder_mask_rows = 705` (masks the pedestal post; not in the manifest — supply explicitly).
- **Test runner:** `.venv/Scripts/python.exe -m pytest <path> -v`.
- **Interpreter:** always `.venv/Scripts/python.exe` (venv is not auto-activated).

---

## File Structure

- `scratchpad/cleanroom/__init__.py` — namespace marker.
- `scratchpad/cleanroom/support_samples.py` — Task 1. Build `SupportSamples` from a dataset; analytic synthetic generator for tests.
- `scratchpad/cleanroom/polytope.py` — Task 2. Shared back-end: affine↔plane, `planes_to_mesh`, `merge_planes`, `facet_rms`, `extremal_caps`.
- `scratchpad/cleanroom/strike_metric.py` — Task 3. Objective strike-line energy of a mesh.
- `scratchpad/cleanroom/cand_c_egi.py` — Task 4. EGI / Gauss-sphere normal clustering.
- `scratchpad/cleanroom/cand_a_ransac.py` — Task 5. Tangent-plane RANSAC.
- `scratchpad/cleanroom/cand_b_dual.py` — Task 6. Dual/convex-hull + coplanar merge.
- `scratchpad/cleanroom/render.py` — Task 7. PIL orthographic shaded comparison render.
- `scratchpad/cleanroom/bakeoff.py` — Task 7. Harness: run all on gem04, table, render, note.
- `scratchpad/cleanroom/test_support_samples.py`, `test_polytope.py`, `test_strike_metric.py`, `test_candidates.py` — co-located pytest tests using synthetic ground truth.
- `docs/superpowers/notes/2026-07-22-cleanroom-bakeoff-results.md` — Task 8. Results + recommendation.

Shared data type (defined in Task 1, used everywhere):

```python
@dataclass
class SupportSamples:
    theta: np.ndarray   # (V,) view azimuths, radians
    z: np.ndarray       # (H,) heights, mm
    h: np.ndarray       # (H, V) right-edge support value, mm; nan where invalid
    valid: np.ndarray   # (H, V) bool
```

Shared plane representation everywhere: `dict(plane=(a,b,c,d), rms=float, source=str)`. `rms==0.0` marks a cap (table/culet); tangent facets have `rms>0`.

---

### Task 1: Support-sample front-end + synthetic generator

**Files:**
- Create: `scratchpad/cleanroom/__init__.py` (empty)
- Create: `scratchpad/cleanroom/support_samples.py`
- Test: `scratchpad/cleanroom/test_support_samples.py`

**Interfaces:**
- Consumes: `gemscanner.storage.dataset.load_dataset`, `gemscanner.vision.silhouette.extract_silhouette/row_spans`, `gemscanner.coords.row_to_z/axis_column_at_row/column_to_projection`.
- Produces:
  - `SupportSamples` dataclass (fields above).
  - `build_support_samples(dataset, holder_mask_rows=0, threshold=None) -> SupportSamples`
  - `synthetic_support_from_planes(planes, thetas_rad, z_values) -> SupportSamples` where `planes` is a list of `(a,b,c,d)` unit-normal half-spaces bounding a convex body containing the origin.

- [ ] **Step 1: Write the failing test**

```python
# scratchpad/cleanroom/test_support_samples.py
import numpy as np
from scratchpad.cleanroom.support_samples import synthetic_support_from_planes

def _box_planes(hx, hy, hz):
    # axis-aligned box |x|<=hx, |y|<=hy, |z|<=hz as 6 unit half-spaces
    return [(1,0,0,hx),(-1,0,0,hx),(0,1,0,hy),(0,-1,0,hy),(0,0,1,hz),(0,0,-1,hz)]

def test_box_support_matches_closed_form():
    planes = _box_planes(3.0, 2.0, 1.0)
    thetas = np.radians([0.0, 90.0, 180.0, 270.0])
    zs = np.array([-0.5, 0.0, 0.5])
    s = synthetic_support_from_planes(planes, thetas, zs)
    # direction u(theta)=(cos, -sin). theta=0 -> +x, support = hx = 3
    # theta=90 -> (0,-1) i.e. -y, support = hy = 2
    assert s.h.shape == (3, 4)
    assert np.allclose(s.h[:, 0], 3.0, atol=1e-4)   # +x
    assert np.allclose(s.h[:, 1], 2.0, atol=1e-4)   # -y
    assert np.allclose(s.h[:, 2], 3.0, atol=1e-4)   # -x
    assert np.allclose(s.h[:, 3], 2.0, atol=1e-4)   # +y
    assert s.valid.all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_support_samples.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` (module not created yet).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/support_samples.py
from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans


@dataclass
class SupportSamples:
    theta: np.ndarray   # (V,) radians
    z: np.ndarray       # (H,) mm
    h: np.ndarray       # (H, V) mm, nan invalid
    valid: np.ndarray   # (H, V) bool


def build_support_samples(dataset, holder_mask_rows=0, threshold=None):
    """Right-edge support h(theta, z) from silhouettes (orthographic).
    theta convention: view normal u=(cos th, -sin th); h_right = +x_max."""
    m = dataset.manifest
    H, mmpp, V = m.image_height, m.mm_per_px, dataset.frame_count()
    z = np.array([row_to_z(v, H, mmpp) for v in range(H)])
    theta = np.radians(np.asarray(m.angles_deg, float))
    h = np.full((H, V), np.nan)
    for i in range(V):
        img = dataset.load_frame(i)
        mask = extract_silhouette(img, threshold, holder_mask_rows)
        spans = row_spans(mask)
        for v in range(H):
            L, R = spans[v]
            if L < 0:
                continue
            axc = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            h[v, i] = column_to_projection(R, axc, mmpp)
    return SupportSamples(theta=theta, z=z, h=h, valid=~np.isnan(h))


def synthetic_support_from_planes(planes, thetas_rad, z_values):
    """Exact support h(theta,z) of the convex body {a x+b y+c z <= d} via LP.
    At height z the slice is {(a,b).(x,y) <= d - c z}; support in direction
    u=(cos th,-sin th) is max u.(x,y) over that polygon (a small linprog)."""
    P = np.asarray(planes, float)
    A2 = P[:, :2]                      # (K,2) horizontal parts
    thetas_rad = np.asarray(thetas_rad, float)
    z_values = np.asarray(z_values, float)
    H, V = len(z_values), len(thetas_rad)
    h = np.full((H, V), np.nan)
    for vi, z in enumerate(z_values):
        b2 = P[:, 3] - P[:, 2] * z     # (K,) rhs at this height
        for ti, th in enumerate(thetas_rad):
            u = np.array([np.cos(th), -np.sin(th)])
            res = linprog(-u, A_ub=A2, b_ub=b2,
                          bounds=[(None, None), (None, None)])
            if res.success:
                h[vi, ti] = float(u @ res.x)
    return SupportSamples(theta=thetas_rad, z=z_values, h=h, valid=~np.isnan(h))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_support_samples.py -v`
Expected: PASS.

- [ ] **Step 5: Add a real-data smoke test and run it**

Append to the test file:

```python
def test_build_from_gem04_shapes():
    from gemscanner.storage.dataset import load_dataset
    ds = load_dataset("scans/gem04")
    s = build_support_samples(ds, holder_mask_rows=705)
    assert s.h.shape[1] == ds.frame_count()
    assert s.valid.any()
    # gem is a few mm; support should be within a sane physical range
    assert 0.5 < np.nanmax(s.h) < 25.0
```

Add the import `from scratchpad.cleanroom.support_samples import build_support_samples`.
Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_support_samples.py -v`
Expected: PASS (2 tests). Wall-clock a few seconds.

- [ ] **Step 6: Commit**

```bash
git add scratchpad/cleanroom/__init__.py scratchpad/cleanroom/support_samples.py scratchpad/cleanroom/test_support_samples.py
git commit -m "feat(cleanroom): support-sample front-end + synthetic generator"
```

---

### Task 2: Shared polytope back-end

**Files:**
- Create: `scratchpad/cleanroom/polytope.py`
- Test: `scratchpad/cleanroom/test_polytope.py`

**Interfaces:**
- Consumes: `SupportSamples` (Task 1).
- Produces:
  - `affine_to_plane(theta_star, alpha, beta) -> (a,b,c,d)`
  - `plane_to_affine(plane) -> (theta_star, alpha, beta)`
  - `planes_to_mesh(planes) -> (mesh, verts, edges)` — `planes` = list of `(a,b,c,d)`. Raises `ValueError` if unbounded.
  - `merge_planes(recs, merge_deg=6.0, d_reltol=0.02) -> list[dict]` — `recs` = list of `dict(plane,rms,source)`.
  - `facet_rms(plane, samples, az_tol_deg=6.0, resid_tol_mm=0.05) -> (rms_mm, n_inliers)`
  - `extremal_caps(samples, width_frac=0.3) -> list[dict]` — table/culet caps as `dict(plane,rms=0.0,source="cap")`.

- [ ] **Step 1: Write the failing test**

```python
# scratchpad/cleanroom/test_polytope.py
import numpy as np
from scratchpad.cleanroom.polytope import (
    affine_to_plane, plane_to_affine, planes_to_mesh, merge_planes)

def _box_planes(hx, hy, hz):
    return [(1,0,0,hx),(-1,0,0,hx),(0,1,0,hy),(0,-1,0,hy),(0,0,1,hz),(0,0,-1,hz)]

def test_affine_plane_roundtrip():
    th, al, be = 0.7, -0.3, 2.5
    a, b, c, d = affine_to_plane(th, al, be)
    assert abs(np.hypot(np.hypot(a, b), c) - 1.0) < 1e-9   # unit normal
    th2, al2, be2 = plane_to_affine((a, b, c, d))
    assert abs(np.angle(np.exp(1j*(th2-th)))) < 1e-6
    assert abs(al2-al) < 1e-6 and abs(be2-be) < 1e-6

def test_box_planes_to_mesh_watertight_extents():
    mesh, verts, edges = planes_to_mesh(_box_planes(3.0, 2.0, 1.0))
    assert mesh.is_watertight
    ext = mesh.bounding_box.extents
    assert np.allclose(sorted(ext), [2.0, 4.0, 6.0], atol=1e-6)

def test_merge_collapses_near_duplicates():
    recs = [dict(plane=(1,0,0,3.0), rms=0.01, source="t"),
            dict(plane=(1,0,0,3.02), rms=0.005, source="t"),  # ~dup, better rms
            dict(plane=(0,1,0,2.0), rms=0.01, source="t")]
    out = merge_planes(recs, merge_deg=6.0)
    assert len(out) == 2
    kept = [r for r in out if abs(r["plane"][0]-1) < 1e-9][0]
    assert kept["rms"] == 0.005   # keeps lower-rms of the merged pair
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_polytope.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/polytope.py
import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
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
    interior = _interior_point(hs)
    hi = HalfspaceIntersection(hs, interior)
    pts = hi.intersections
    hull = trimesh.Trimesh(vertices=pts).convex_hull
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
    """Table/culet caps: cap a z-extreme only if the silhouette there is a wide
    flat table (> width_frac * girdle width). Pointed culet gets no cap."""
    # per-row mean diameter across views (h_right + mirror = 2*h assuming
    # centred; use h at theta and theta+pi via full 360 coverage)
    width = np.nanmax(samples.h, axis=1) + np.nanmax(-samples.h, axis=1)
    ok = np.isfinite(width) & samples.valid.any(axis=1)
    if not ok.any():
        return []
    zv, wv = samples.z[ok], width[ok]
    order = np.argsort(zv); zv, wv = zv[order], wv[order]
    girdle = float(np.nanmax(wv))
    if girdle <= 0:
        return []
    band = max(3, int(0.2 / max(abs(zv[1]-zv[0]), 1e-6)))
    caps = []
    if np.nanmean(wv[-band:]) > width_frac * girdle:
        caps.append(dict(plane=(0.0, 0.0, 1.0, float(zv[-1])), rms=0.0, source="cap"))
    if np.nanmean(wv[:band]) > width_frac * girdle:
        caps.append(dict(plane=(0.0, 0.0, -1.0, float(-zv[0])), rms=0.0, source="cap"))
    return caps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_polytope.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/polytope.py scratchpad/cleanroom/test_polytope.py
git commit -m "feat(cleanroom): shared polytope back-end (planes<->affine, mesh, merge, caps, rms)"
```

---

### Task 3: Objective strike-line metric

**Files:**
- Create: `scratchpad/cleanroom/strike_metric.py`
- Test: `scratchpad/cleanroom/test_strike_metric.py`

**Interfaces:**
- Consumes: a `trimesh.Trimesh`.
- Produces: `strike_energy(mesh, n_azimuth=48, n_z=300, r_max=20.0, hp_rows=9) -> float` — mean over azimuths of the high-pass RMS (µm) of surface radius along z. High = strike-lines present.

- [ ] **Step 1: Write the failing test**

```python
# scratchpad/cleanroom/test_strike_metric.py
import numpy as np
import trimesh
from scratchpad.cleanroom.strike_metric import strike_energy
from scratchpad.cleanroom.polytope import planes_to_mesh

def _box_planes(hx, hy, hz):
    return [(1,0,0,hx),(-1,0,0,hx),(0,1,0,hy),(0,-1,0,hz*0+hy),(0,0,1,hz),(0,0,-1,hz)]

def test_clean_facet_mesh_has_low_strike_energy():
    mesh, _, _ = planes_to_mesh([(1,0,0,3.0),(-1,0,0,3.0),(0,1,0,3.0),
                                 (0,-1,0,3.0),(0,0,1,3.0),(0,0,-1,3.0)])
    e_clean = strike_energy(mesh)
    # add radial ripple in z to fake strike-lines
    v = mesh.vertices.copy()
    r = np.hypot(v[:,0], v[:,1])
    scale = 1.0 + 0.03*np.sin(v[:,2]*40.0)   # 3% z-frequency ripple
    v[:,0] *= scale; v[:,1] *= scale
    striped = trimesh.Trimesh(vertices=v, faces=mesh.faces, process=False)
    e_striped = strike_energy(striped)
    assert e_striped > 5.0 * e_clean + 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_strike_metric.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/strike_metric.py
import numpy as np
from scipy.ndimage import median_filter


def strike_energy(mesh, n_azimuth=48, n_z=300, r_max=20.0, hp_rows=9):
    """Cast outward horizontal rays on a grid of (azimuth, z); record hit
    radius r(z); high-pass along z (r - median_filter) and RMS. Averaged over
    azimuths. A clean faceted polytope -> ~0; per-z-row noise -> elevated."""
    zmin, zmax = mesh.bounds[0, 2], mesh.bounds[1, 2]
    zs = np.linspace(zmin + 1e-3, zmax - 1e-3, n_z)
    phis = np.linspace(0, 2*np.pi, n_azimuth, endpoint=False)
    energies = []
    for phi in phis:
        d = np.array([np.cos(phi), np.sin(phi), 0.0])
        origins = np.column_stack([np.zeros(n_z), np.zeros(n_z), zs])
        dirs = np.tile(d, (n_z, 1))
        locs, idx_ray, _ = mesh.ray.intersects_location(origins, dirs,
                                                        multiple_hits=True)
        r = np.full(n_z, np.nan)
        for j in range(n_z):
            hits = locs[idx_ray == j]
            if len(hits):
                r[j] = np.max(np.hypot(hits[:, 0], hits[:, 1]))
        good = np.isfinite(r)
        if good.sum() < hp_rows + 2:
            continue
        rr = r.copy()
        rr[~good] = np.interp(np.flatnonzero(~good), np.flatnonzero(good), r[good])
        hp = rr - median_filter(rr, size=hp_rows)
        energies.append(np.sqrt(np.mean(hp[good]**2)) * 1000.0)  # µm
    return float(np.mean(energies)) if energies else float("nan")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_strike_metric.py -v`
Expected: PASS. (If trimesh selects the pure-python ray engine it is slower but still passes; keep `n_z=300`.)

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/strike_metric.py scratchpad/cleanroom/test_strike_metric.py
git commit -m "feat(cleanroom): objective strike-line energy metric"
```

---

### Task 4: Candidate C — EGI / Gauss-sphere clustering

**Files:**
- Create: `scratchpad/cleanroom/cand_c_egi.py`
- Test: `scratchpad/cleanroom/test_candidates.py` (shared synthetic gate; created here)

**Interfaces:**
- Consumes: `SupportSamples`, `polytope.affine_to_plane/facet_rms`.
- Produces: `reconstruct_egi(samples, merge_deg=6.0, slope_win=9, min_arc_deg=6.0) -> list[dict]` returning tangent-facet `dict(plane,rms,source="egi")` (no caps; harness adds caps).

Synthetic ground-truth used by all candidate tests — a hexagonal bipyramid (gem-like: 12 slanted facets, top and bottom apex):

```python
def _bipyramid_planes(n=6, slope=1.2, r=2.0):
    # n top + n bottom slanted facets; normals evenly in azimuth, tilt from slope
    planes = []
    for k in range(n):
        az = 2*np.pi*k/n
        for sgn in (+1.0, -1.0):
            a = np.cos(az); b = -np.sin(az); c = sgn*slope
            nrm = np.hypot(np.hypot(a, b), c)
            planes.append((a/nrm, b/nrm, c/nrm, r/nrm))
    return planes
```

- [ ] **Step 1: Write the failing test**

```python
# scratchpad/cleanroom/test_candidates.py
import numpy as np
from scratchpad.cleanroom.support_samples import synthetic_support_from_planes
from scratchpad.cleanroom.polytope import planes_to_mesh, merge_planes
from scratchpad.cleanroom.cand_c_egi import reconstruct_egi

def _bipyramid_planes(n=6, slope=1.2, r=2.0):
    planes = []
    for k in range(n):
        az = 2*np.pi*k/n
        for sgn in (+1.0, -1.0):
            a = np.cos(az); b = -np.sin(az); c = sgn*slope
            nrm = np.hypot(np.hypot(a, b), c)
            planes.append((a/nrm, b/nrm, c/nrm, r/nrm))
    return planes

def _samples_for(planes, nth=180, nz=140):
    thetas = np.linspace(0, 2*np.pi, nth, endpoint=False)
    zs = np.linspace(-1.5, 1.5, nz)
    return synthetic_support_from_planes(planes, thetas, zs)

def _normal_error_deg(recs, truth):
    tn = np.array([p[:3] for p in truth])
    errs = []
    for r in recs:
        n = np.array(r["plane"][:3])
        cs = np.clip(tn @ n, -1, 1)
        errs.append(np.degrees(np.arccos(cs.max())))
    return np.array(errs)

def test_egi_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = merge_planes(reconstruct_egi(s))
    assert len(recs) >= 12                       # all 12 slanted facets
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.0                  # normals within a few deg
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py::test_egi_recovers_bipyramid -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/cand_c_egi.py
import numpy as np
from scratchpad.cleanroom.polytope import affine_to_plane, facet_rms


def _theilsen_slope(z, h):
    dz = z[:, None] - z[None, :]
    dh = h[:, None] - h[None, :]
    ok = np.abs(dz) > 1e-9
    return np.median(dh[ok] / dz[ok]) if ok.any() else np.nan


def reconstruct_egi(samples, merge_deg=6.0, slope_win=9, min_arc_deg=6.0):
    """Per-sample surface normals -> greedy angular clustering on the Gauss
    sphere -> one plane per cluster (offset from robust affine fit)."""
    V = len(samples.theta)
    normals = []      # (nx,ny,nz)
    carriers = []     # (view_index, z) provenance for offset solve
    k = slope_win // 2
    for i in range(V):
        sel = np.where(samples.valid[:, i])[0]
        if len(sel) < slope_win + 1:
            continue
        zc = samples.z[sel]; hc = samples.h[sel, i]
        order = np.argsort(zc); zc, hc = zc[order], hc[order]
        for j in range(k, len(zc) - k):
            alpha = _theilsen_slope(zc[j-k:j+k+1], hc[j-k:j+k+1])
            if not np.isfinite(alpha):
                continue
            a, b, c, _d = affine_to_plane(samples.theta[i], alpha, 0.0)
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
        if nin >= 4:
            recs.append(dict(plane=plane, rms=rms, source="egi"))
    return recs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py::test_egi_recovers_bipyramid -v`
Expected: PASS. If normal-error or count fails, tune `merge_deg`/`min_arc_deg` — do NOT relax the assertions.

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/cand_c_egi.py scratchpad/cleanroom/test_candidates.py
git commit -m "feat(cleanroom): candidate C — EGI/Gauss-sphere facet recovery"
```

---

### Task 5: Candidate A — Tangent-plane RANSAC

**Files:**
- Create: `scratchpad/cleanroom/cand_a_ransac.py`
- Modify: `scratchpad/cleanroom/test_candidates.py` (add RANSAC test)

**Interfaces:**
- Consumes: `SupportSamples`, `polytope.affine_to_plane/plane_to_affine/facet_rms`.
- Produces: `reconstruct_ransac(samples, n_iter=2000, az_win_deg=8.0, z_win_mm=0.6, resid_tol_mm=0.03, min_inliers=40, seed=0) -> list[dict]` returning `dict(plane,rms,source="ransac")`.

- [ ] **Step 1: Write the failing test**

Add to `test_candidates.py`:

```python
from scratchpad.cleanroom.cand_a_ransac import reconstruct_ransac

def test_ransac_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = merge_planes(reconstruct_ransac(s, n_iter=1500, seed=1))
    assert len(recs) >= 12
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.0
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py::test_ransac_recovers_bipyramid -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/cand_a_ransac.py
import numpy as np
from scratchpad.cleanroom.polytope import affine_to_plane, facet_rms


def _flatten(samples):
    """Return arrays (theta, z, h) of all valid support observations."""
    H, V = samples.h.shape
    ti = np.tile(np.arange(V), H)
    zi = np.repeat(np.arange(H), V)
    flat_theta = samples.theta[ti]
    flat_z = samples.z[zi]
    flat_h = samples.h.ravel()
    ok = np.isfinite(flat_h)
    return flat_theta[ok], flat_z[ok], flat_h[ok]


def reconstruct_ransac(samples, n_iter=2000, az_win_deg=8.0, z_win_mm=0.6,
                       resid_tol_mm=0.03, min_inliers=40, seed=0):
    """Hypothesise a plane from a random azimuth+z window (fit beta+alpha*z),
    score by counting support samples it is tangent to (residual < tol within
    an azimuth band), keep well-supported planes, remove their inliers, repeat
    greedily."""
    rng = np.random.default_rng(seed)
    th, z, h = _flatten(samples)
    live = np.ones(len(th), bool)
    az_tol = np.radians(az_win_deg)
    recs = []
    for _ in range(n_iter):
        if live.sum() < min_inliers:
            break
        # seed: a random live sample + its azimuth/z neighbourhood
        s0 = rng.choice(np.flatnonzero(live))
        near = (np.abs(np.angle(np.exp(1j*(th - th[s0])))) < az_tol) & \
               (np.abs(z - z[s0]) < z_win_mm) & live
        if near.sum() < 5:
            continue
        A = np.column_stack([z[near], np.ones(near.sum())])
        (alpha, beta), *_ = np.linalg.lstsq(A, h[near], rcond=None)
        theta_star = th[s0]
        # score across ALL live samples within azimuth band
        band = (np.abs(np.angle(np.exp(1j*(th - theta_star)))) < az_tol) & live
        pred = beta + alpha * z
        inl = band & (np.abs(pred - h) < resid_tol_mm)
        if inl.sum() < min_inliers:
            continue
        # refit on inliers, recentre azimuth as inlier mean
        A2 = np.column_stack([z[inl], np.ones(inl.sum())])
        (alpha, beta), *_ = np.linalg.lstsq(A2, h[inl], rcond=None)
        theta_star = np.angle(np.mean(np.exp(1j*th[inl])))
        plane = affine_to_plane(theta_star, alpha, beta)
        rms, nin = facet_rms(plane, samples)
        recs.append(dict(plane=plane, rms=rms if np.isfinite(rms) else 0.01,
                         source="ransac"))
        live[inl] = False
    return recs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py::test_ransac_recovers_bipyramid -v`
Expected: PASS. If flaky on `seed`, keep the assertions; adjust `n_iter`/`min_inliers` only.

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/cand_a_ransac.py scratchpad/cleanroom/test_candidates.py
git commit -m "feat(cleanroom): candidate A — tangent-plane RANSAC facet recovery"
```

---

### Task 6: Candidate B — Dual / convex-hull + coplanar merge

**Files:**
- Create: `scratchpad/cleanroom/cand_b_dual.py`
- Modify: `scratchpad/cleanroom/test_candidates.py` (add dual test)

**Interfaces:**
- Consumes: `SupportSamples`, `polytope.merge_planes/plane_to_affine/facet_rms`.
- Produces: `reconstruct_dual(samples, merge_deg=6.0, min_face_area_frac=0.002) -> list[dict]` returning `dict(plane,rms,source="dual")`.

**Mechanism:** per z-slice, intersect the 2D half-planes `u_i·X <= h_i` → slice polygon; collect all polygon vertices over all z into a 3D surface point cloud; take its 3D convex hull; cluster hull faces by normal (the polar-dual face-selection done robustly in primal space); refit each cluster to one plane over its supporting samples. The coplanar-merge is the z-coupling step that removes strike-lines.

- [ ] **Step 1: Write the failing test**

Add to `test_candidates.py`:

```python
from scratchpad.cleanroom.cand_b_dual import reconstruct_dual

def test_dual_recovers_bipyramid():
    truth = _bipyramid_planes()
    s = _samples_for(truth)
    recs = reconstruct_dual(s)     # returns already-merged planes
    assert len(recs) >= 12
    err = _normal_error_deg(recs, truth)
    assert np.median(err) < 3.5
    mesh, _, _ = planes_to_mesh([r["plane"] for r in recs])
    assert mesh.is_watertight
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py::test_dual_recovers_bipyramid -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# scratchpad/cleanroom/cand_b_dual.py
import numpy as np
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from scratchpad.cleanroom.polytope import merge_planes, plane_to_affine, facet_rms


def _slice_polygon(u, hvals):
    """2D convex polygon = {x : u_i . x <= h_i}. Returns (N,2) or None."""
    hs = np.column_stack([u, -hvals])          # a x + b y - h <= 0
    A = hs[:, :2]; b = -hs[:, 2]
    norm = np.linalg.norm(A, axis=1, keepdims=True)
    c = np.zeros(3); c[-1] = -1.0
    res = linprog(c, A_ub=np.hstack([A, norm]), b_ub=b,
                  bounds=[(None, None), (None, None), (0, None)])
    if not res.success or res.x[-1] <= 0:
        return None
    try:
        hi = HalfspaceIntersection(hs, res.x[:2])
    except Exception:
        return None
    return hi.intersections


def reconstruct_dual(samples, merge_deg=6.0, min_face_area_frac=0.002):
    u = np.column_stack([np.cos(samples.theta), -np.sin(samples.theta)])
    cloud = []
    for vi in range(len(samples.z)):
        sel = samples.valid[vi]
        if sel.sum() < 3:
            continue
        poly = _slice_polygon(u[sel], samples.h[vi, sel])
        if poly is None or len(poly) < 3:
            continue
        cloud.append(np.column_stack([poly, np.full(len(poly), samples.z[vi])]))
    if not cloud:
        return []
    pts = np.vstack(cloud)
    hull = trimesh.Trimesh(vertices=pts).convex_hull
    total = float(hull.area)
    recs = []
    for fn, fa in zip(hull.face_normals, hull.area_faces):
        if fa < min_face_area_frac * total:
            continue
        # face plane through its centroid; normalise to our convention
        recs.append(dict(normal=np.asarray(fn, float), area=float(fa)))
    # cluster faces by normal, area-weighted -> merged planes
    cos_tol = np.cos(np.radians(merge_deg))
    clusters = []   # [accum_normal(weighted), area]
    for r in sorted(recs, key=lambda x: -x["area"]):
        n = r["normal"]; w = r["area"]
        for cl in clusters:
            ref = cl[0] / np.linalg.norm(cl[0])
            if float(n @ ref) >= cos_tol:
                cl[0] += w * n; cl[1] += w
                break
        else:
            clusters.append([w * n.copy(), w])
    out = []
    for accum, _area in clusters:
        nrm = accum / np.linalg.norm(accum)
        if abs(nrm[2]) > 0.999:                 # near-horizontal cap, skip here
            continue
        theta_star = np.arctan2(-nrm[1], nrm[0])
        alpha = -nrm[2] / np.hypot(nrm[0], nrm[1])
        dth = np.angle(np.exp(1j*(samples.theta - theta_star)))
        i = int(np.argmin(np.abs(dth)))
        sel = samples.valid[:, i]
        beta = float(np.median(samples.h[sel, i] - alpha*samples.z[sel]))
        from scratchpad.cleanroom.polytope import affine_to_plane
        plane = affine_to_plane(theta_star, alpha, beta)
        rms, nin = facet_rms(plane, samples)
        if nin >= 4:
            out.append(dict(plane=plane, rms=rms if np.isfinite(rms) else 0.01,
                            source="dual"))
    return merge_planes(out, merge_deg=merge_deg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/test_candidates.py -v`
Expected: PASS (all three candidate tests).

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/cand_b_dual.py scratchpad/cleanroom/test_candidates.py
git commit -m "feat(cleanroom): candidate B — dual/convex-hull + coplanar-merge facet recovery"
```

---

### Task 7: Bake-off harness + PIL comparison render (gem04)

**Files:**
- Create: `scratchpad/cleanroom/render.py`
- Create: `scratchpad/cleanroom/bakeoff.py`

**Interfaces:**
- Consumes: all candidate `reconstruct_*`, `polytope.merge_planes/planes_to_mesh/extremal_caps`, `strike_metric.strike_energy`, `support_samples.build_support_samples`, and (harness only, labelled) `gemscanner.reconstruction.pipeline.reconstruct_dataset` for control+benchmark.
- Produces:
  - `render.render_side_by_side(named_meshes, out_png, elev_deg=15, size=320) -> None` — orthographic painter's-algorithm shaded panels, one per mesh, tiled into one PNG.
  - `bakeoff.main()` — runs everything on gem04, prints the metrics table, writes `scratchpad/cleanroom/bakeoff_gem04.png`, and prints a markdown results block for the note.

- [ ] **Step 1: Write the render module (no separate unit test; validated visually in Step 3)**

```python
# scratchpad/cleanroom/render.py
import numpy as np
from PIL import Image


def _project(mesh, elev_deg, azim_deg, size):
    v = mesh.vertices - mesh.vertices.mean(axis=0)
    e, a = np.radians(elev_deg), np.radians(azim_deg)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    p = v @ Rz.T @ Rx.T
    span = np.max(np.ptp(p[:, :2], axis=0)) or 1.0
    scale = 0.8 * size / span
    xy = p[:, :2] * scale + size / 2.0
    xy[:, 1] = size - xy[:, 1]
    return xy, p[:, 2], (mesh.face_normals @ Rz.T @ Rx.T)


def render_side_by_side(named_meshes, out_png, elev_deg=15, azim_deg=35, size=320):
    panels = []
    for name, mesh in named_meshes:
        img = Image.new("RGB", (size, size), (245, 245, 245))
        px = img.load()
        if mesh is not None and len(mesh.faces):
            xy, depth, fn = _project(mesh, elev_deg, azim_deg, size)
            face_depth = depth[mesh.faces].mean(axis=1)
            light = np.array([0.3, 0.3, 0.9]); light /= np.linalg.norm(light)
            shade = np.clip(fn @ light, 0.15, 1.0)
            zbuf = np.full((size, size), -1e9)
            for fi in np.argsort(face_depth):     # painter's: far to near
                tri = xy[mesh.faces[fi]]
                col = int(60 + 180 * shade[fi])
                _fill_tri(px, zbuf, tri, face_depth[fi], (col, col, min(255, col+30)), size)
        panels.append((name, img))
    W = size * len(panels)
    canvas = Image.new("RGB", (W, size + 18), (255, 255, 255))
    from PIL import ImageDraw
    for k, (name, img) in enumerate(panels):
        canvas.paste(img, (k * size, 18))
        ImageDraw.Draw(canvas).text((k * size + 6, 4), name, fill=(0, 0, 0))
    canvas.save(out_png)


def _fill_tri(px, zbuf, tri, z, color, size):
    xs = tri[:, 0]; ys = tri[:, 1]
    x0, x1 = int(max(0, xs.min())), int(min(size - 1, xs.max()))
    y0, y1 = int(max(0, ys.min())), int(min(size - 1, ys.max()))
    if x1 < x0 or y1 < y0:
        return
    (ax, ay), (bx, by), (cx, cy) = tri
    denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(denom) < 1e-9:
        return
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            w0 = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / denom
            w1 = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / denom
            w2 = 1 - w0 - w1
            if w0 >= -0.01 and w1 >= -0.01 and w2 >= -0.01:
                if z > zbuf[xx, yy]:
                    zbuf[xx, yy] = z
                    px[xx, yy] = color
```

- [ ] **Step 2: Write the harness**

```python
# scratchpad/cleanroom/bakeoff.py
import time
import warnings
import numpy as np
import trimesh
from scratchpad.cleanroom.support_samples import build_support_samples
from scratchpad.cleanroom.polytope import merge_planes, planes_to_mesh, extremal_caps
from scratchpad.cleanroom.strike_metric import strike_energy
from scratchpad.cleanroom.cand_a_ransac import reconstruct_ransac
from scratchpad.cleanroom.cand_b_dual import reconstruct_dual
from scratchpad.cleanroom.cand_c_egi import reconstruct_egi
from scratchpad.cleanroom.render import render_side_by_side
from gemscanner.storage.dataset import load_dataset

SCAN = "scans/gem04"
HOLDER = 705


def _assemble(planes_fn, samples):
    recs = merge_planes(planes_fn(samples))
    recs = recs + extremal_caps(samples)
    mesh, verts, edges = planes_to_mesh([r["plane"] for r in recs])
    tangent = [r for r in recs if r["rms"] > 0]
    return mesh, recs, tangent


def _metrics(name, mesh, tangent, ref):
    ext = mesh.bounding_box.extents
    dvec = (ext - ref.bounding_box.extents) * 1000.0
    rms = np.array([r["rms"]*1000.0 for r in tangent]) if tangent else np.array([np.nan])
    return dict(name=name, planes=len(tangent), watertight=bool(mesh.is_watertight),
                extents=ext, dX=dvec[0], dY=dvec[1], dZ=dvec[2],
                vol=mesh.volume, dvol=mesh.volume-ref.volume,
                rms_med=float(np.nanmedian(rms)), rms_max=float(np.nanmax(rms)),
                strike=strike_energy(mesh))


def main():
    ds = load_dataset(SCAN)
    ref = trimesh.load(f"{SCAN}/gem.stl")
    print("building support samples...")
    s = build_support_samples(ds, holder_mask_rows=HOLDER)

    rows = []
    meshes = []
    for name, fn in [("Cand-A RANSAC", reconstruct_ransac),
                     ("Cand-B dual", reconstruct_dual),
                     ("Cand-C EGI", reconstruct_egi)]:
        t0 = time.time()
        mesh, recs, tangent = _assemble(fn, s)
        m = _metrics(name, mesh, tangent, ref); m["sec"] = time.time()-t0
        rows.append(m); meshes.append((name, mesh))
        mesh.export(f"scratchpad/cleanroom/{name.split()[0].lower()}_gem04.stl")

    # control (space carving = shipped strip) and benchmark (shipped v2.3 facet)
    from gemscanner.reconstruction.pipeline import reconstruct_dataset
    from gemscanner.reconstruction.base import ReconstructionParams
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ctrl = reconstruct_dataset(SCAN, ReconstructionParams(method="strip", holder_mask_rows=HOLDER))
        bench = reconstruct_dataset(SCAN, ReconstructionParams(method="facet", holder_mask_rows=HOLDER))
    for name, mesh in [("CONTROL strip", ctrl), ("BENCH v2.3", bench)]:
        ext = mesh.bounding_box.extents
        dvec = (ext - ref.bounding_box.extents)*1000.0
        rows.append(dict(name=name, planes=len(getattr(mesh, "faces", [])),
                         watertight=bool(mesh.is_watertight), extents=ext,
                         dX=dvec[0], dY=dvec[1], dZ=dvec[2], vol=mesh.volume,
                         dvol=mesh.volume-ref.volume, rms_med=np.nan, rms_max=np.nan,
                         strike=strike_energy(mesh), sec=np.nan))
        meshes.append((name, mesh))

    hdr = f"{'method':<16}{'facets':>7}{'wt':>4}{'dX':>8}{'dY':>8}{'dZ':>8}" \
          f"{'rmsMed':>8}{'strike':>8}{'sec':>7}"
    print("\n" + hdr); print("-"*len(hdr))
    for m in rows:
        print(f"{m['name']:<16}{m['planes']:>7}{str(m['watertight'])[0]:>4}"
              f"{m['dX']:>8.0f}{m['dY']:>8.0f}{m['dZ']:>8.0f}"
              f"{m['rms_med']:>8.1f}{m['strike']:>8.1f}{m['sec']:>7.1f}")
    print("\n(units: d* µm vs gem.stl, rmsMed µm, strike µm high-pass energy)")

    render_side_by_side([("gem.stl", ref)] + meshes,
                        "scratchpad/cleanroom/bakeoff_gem04.png")
    print("wrote scratchpad/cleanroom/bakeoff_gem04.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the harness end-to-end on gem04**

Run: `.venv/Scripts/python.exe -m scratchpad.cleanroom.bakeoff`
Expected: prints a table with 5 rows (3 candidates + control + benchmark), and writes `bakeoff_gem04.png`. Success criteria to observe (record actual numbers, do not fake):
- all three candidates `watertight=True`;
- candidate `strike` energy is small and **the CONTROL strip row has visibly higher `strike`** (this is the whole point — the metric must separate them);
- candidate extents `dX/dY/dZ` within a small factor of the BENCH v2.3 row.
If a candidate is not watertight or fails to bound a region (`ValueError` from `planes_to_mesh`), that is a **real finding** — record it; do not silently drop the candidate.

- [ ] **Step 4: Visually inspect the render**

Open `scratchpad/cleanroom/bakeoff_gem04.png` (use the Read tool on the PNG). Confirm the CONTROL panel shows horizontal striping/terracing and the three candidate panels show clean flat facets. Capture this observation for the note.

- [ ] **Step 5: Commit**

```bash
git add scratchpad/cleanroom/render.py scratchpad/cleanroom/bakeoff.py scratchpad/cleanroom/bakeoff_gem04.png
git commit -m "feat(cleanroom): gem04 bake-off harness + PIL comparison render"
```

---

### Task 8: Results note + recommendation + memory update

**Files:**
- Create: `docs/superpowers/notes/2026-07-22-cleanroom-bakeoff-results.md`
- Modify: `C:\Users\wjuanxp\.claude\projects\D--CodingProject-GemScanner\memory\MEMORY.md` and a new memory file (if a durable finding emerges).

- [ ] **Step 1: Write the results note**

Write `docs/superpowers/notes/2026-07-22-cleanroom-bakeoff-results.md` containing, with the ACTUAL numbers captured in Task 7 (no placeholders):
- The survey table (copy from the spec).
- The bake-off metrics table (the harness's printed table) verbatim.
- The embedded/linked comparison render and the strike-line observation.
- Per-candidate verdict: watertight? strike-free (metric + visual)? extents vs BENCH v2.3? parameter count / robustness?
- **Recommendation** (one of): (a) v2.3 remains best — none beats it; (b) port a specific idea into the shipped pipeline (name it and say why — e.g. "Cand-B's coplanar-merge closes Z"); (c) a candidate is worth promoting.
- Honesty rule: if no candidate beats v2.3, say so plainly. The investigation's value is the comparison, not a forced win.

- [ ] **Step 2: Update memory index**

Add one line to `MEMORY.md` under the index, e.g.:
`- [Clean-room bakeoff](gemscanner-cleanroom-bakeoff.md) — 2026-07-22 survey+bakeoff on gem04: <one-line verdict>`
and create `gemscanner-cleanroom-bakeoff.md` (metadata type: project) capturing the durable finding and the recommendation, linking `[[gemscanner-faceted-recon]]` and `[[gemscanner-striation-fix]]`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/notes/2026-07-22-cleanroom-bakeoff-results.md
git commit -m "docs(cleanroom): gem04 bake-off results + recommendation"
```

---

## Self-Review

**Spec coverage:**
- Survey of method families → Task 8 note reproduces it; the down-select drives Tasks 4–6. ✓
- Reuse I/O + silhouette only → Global Constraints import rule + Task 1 imports only allowed modules; harness's pipeline import is the one labelled exception for control/benchmark. ✓
- Three candidates A/B/C → Tasks 5/6/4. ✓
- Space-carving negative control + v2.3 benchmark → Task 7 harness. ✓
- Shared `h(θ,z)` front-end → Task 1. ✓
- Numeric gates (facets/watertight/extents/volume/rms) → Task 7 `_metrics`. ✓
- Strike-line objective metric → Task 3. ✓
- Visual gate (side-by-side render) → Task 7 render + Step 4 inspection. ✓
- Deliverables: spec (done), results note (Task 8), scratchpad code (Tasks 1–7), comparison render (Task 7), recommendation (Task 8). ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code; tests have real assertions with synthetic ground truth. ✓

**Type consistency:** plane = `(a,b,c,d)` unit-normal `<= d` everywhere; rec = `dict(plane,rms,source)` with `rms==0.0` ⇒ cap, used consistently in `merge_planes`, `_assemble`, `_metrics`; `affine_to_plane`/`plane_to_affine` names match across Tasks 2/4/5/6; `SupportSamples` fields `theta/z/h/valid` consistent across all consumers; `reconstruct_egi/ransac/dual` all return `list[dict]` and are called uniformly by the harness. ✓

**Note on candidate correctness:** the reference implementations in Tasks 4–6 are validated by the synthetic bipyramid gate (normals < ~3°, watertight). If a candidate's gate fails during implementation, tune its own parameters — never relax the assertion — consistent with the project's "visual/numeric gate is mandatory, don't fake a pass" rule.
