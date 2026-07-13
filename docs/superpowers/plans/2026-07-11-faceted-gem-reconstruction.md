# Faceted-Gem Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an unsupervised, user-selectable `method="facet"` reconstruction that turns a turntable silhouette scan of a convex faceted gem into a clean flat-faceted polyhedron — real facets, sharp edges, exact meet-points, no terracing.

**Architecture:** The existing per-row carve already yields the stone's support function `H(view, z)`. Every facet is edge-on in one azimuth, where its support is affine in `z` (`H = β + α·z`); that fit recovers the exact plane. A smooth soft-hull mesh *seeds* facet count/orientation; each plane is *refit* on the raw support samples; the facet half-spaces are intersected into a watertight convex polytope whose edges/vertices are the facet edges/meet-points. Table/culet (near-axial normals) are recovered as extreme-z horizontal planes.

**Tech Stack:** Python 3.12, numpy, opencv (`cv2`), trimesh, scikit-image (soft-hull seed), scipy (`spatial.HalfspaceIntersection`, `optimize.linprog`), pytest. PySide6 for the GUI entry.

## Global Constraints

- Convex-stone assumption throughout; no concave/non-convex handling (out of scope).
- Fully unsupervised: no cut type, no facet count supplied by the user.
- Reuse existing conventions exactly: `coords.z_to_row` / `row_to_z`, `coords.column_to_projection` / `projection_to_column`, view normal `n_i = (cos θ_i, −sin θ_i)`, background 255 / silhouette 0, z=0 at image vertical centre.
- De-terracing math uses only `numpy` (repo convention: median filters avoid scipy); new facet math may use `scipy` (already an indirect dep — confirm/pin in Task 7).
- `reconstruct(...)` must keep returning a `trimesh.Trimesh` (drop-in for GUI/callers); facet metadata rides on `mesh.metadata["facets"]`.
- Strict TDD, bite-sized commits. Run the full suite (`pytest -q`) green before each commit that touches shared modules.
- Angle/offset tolerances for "exact recovery" on synthetic ground truth: normal error < 0.5°, offset error < 1 px (`mm_per_px`).

---

### Task 1: Synthetic polyhedron silhouette generator

Renders exact orthographic silhouettes of a *known* convex polyhedron about the vertical axis, so later tasks have ground truth. Orthographic silhouette of a convex solid = filled 2D convex hull of its projected vertices.

**Files:**
- Modify: `gemscanner/synthetic/generator.py` (add `generate_polyhedron_scan`)
- Test: `tests/synthetic/test_generator.py` (append)

**Interfaces:**
- Consumes: `coords.projection_to_column`, `coords.z_to_row`, `storage.manifest.ScanManifest`.
- Produces: `generate_polyhedron_scan(out_dir, vertices, n_views=180, mm_per_px=0.05, width=400, height=400) -> out_dir`. `vertices`: array-like `(N,3)` object-frame mm. Writes `frames/NNNN.png` + `manifest.json` (metadata `{"shape": "polyhedron", "n_vertices": N}`). Same axis/centre convention as `generate_ellipsoid_scan`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/synthetic/test_generator.py
from gemscanner.synthetic.generator import generate_polyhedron_scan

def _box_vertices(hx, hy, hz):
    import numpy as np
    return np.array([[sx*hx, sy*hy, sz*hz]
                     for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)

def test_polyhedron_box_width_matches_extent(tmp_path):
    out = generate_polyhedron_scan(str(tmp_path / "box"), _box_vertices(4, 2, 5),
                                   n_views=4, mm_per_px=0.05, width=400, height=400)
    m = ScanManifest.load(os.path.join(out, "manifest.json"))
    assert len(m.frame_files) == 4
    img = cv2.imread(os.path.join(out, m.frame_files[0]), cv2.IMREAD_GRAYSCALE)  # theta=0
    dark_cols = np.where((img == 0).any(axis=0))[0]
    width_px = dark_cols[-1] - dark_cols[0] + 1
    # theta=0 sees the full 2*hx = 8 mm width => 8/0.05 = 160 px (within rounding)
    assert abs(width_px - 160) <= 2
    dark_rows = np.where((img == 0).any(axis=1))[0]
    height_px = dark_rows[-1] - dark_rows[0] + 1
    assert abs(height_px - 200) <= 2  # 2*hz = 10 mm => 200 px
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synthetic/test_generator.py::test_polyhedron_box_width_matches_extent -v`
Expected: FAIL with `ImportError`/`cannot import name 'generate_polyhedron_scan'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to gemscanner/synthetic/generator.py (near the top imports it already has math, np, cv2)
from gemscanner.coords import z_to_row   # add to existing import line

def generate_polyhedron_scan(out_dir, vertices, n_views=180, mm_per_px=0.05,
                             width=400, height=400):
    """Render orthographic silhouettes of a convex polyhedron rotating about the
    vertical (z) axis. Silhouette = filled 2D convex hull of projected vertices.
    Background bright (255), silhouette dark (0)."""
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    vertices = np.asarray(vertices, dtype=float)
    axis_column = (width - 1) / 2.0
    angles = [i * 360.0 / n_views for i in range(n_views)]
    frame_files = []
    for i, ang in enumerate(angles):
        th = math.radians(ang)
        p = vertices[:, 0] * math.cos(th) - vertices[:, 1] * math.sin(th)  # horiz proj
        cols = projection_to_column(p, axis_column, mm_per_px)
        rows = z_to_row(vertices[:, 2], height, mm_per_px)
        pts = np.column_stack([cols, rows]).astype(np.float32)
        img = np.full((height, width), 255, dtype=np.uint8)
        hull = cv2.convexHull(pts)
        cv2.fillConvexPoly(img, hull.astype(np.int32), 0)
        fname = f"{i:04d}.png"
        cv2.imwrite(os.path.join(out_dir, "frames", fname), img)
        frame_files.append(f"frames/{fname}")
    manifest = ScanManifest(
        angles_deg=angles, mm_per_px=mm_per_px, axis_column=axis_column,
        axis_tilt_rad=0.0, image_width=width, image_height=height,
        frame_files=frame_files,
        metadata={"shape": "polyhedron", "n_vertices": int(len(vertices))},
    )
    manifest.save(os.path.join(out_dir, "manifest.json"))
    return out_dir
```

Note: `z_to_row` broadcasts over the vertex array (it is pure arithmetic on `z`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synthetic/test_generator.py -v`
Expected: PASS (both new and existing generator tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/synthetic/generator.py tests/synthetic/test_generator.py
git commit -m "feat(synthetic): orthographic silhouette generator for convex polyhedra"
```

---

### Task 2: Toy-gem builder + ground-truth facet planes

A parametric convex faceted solid (table + crown + girdle + pavilion + culet) and a helper that extracts its unique face planes. Gives later tasks exact ground-truth planes to score against.

**Files:**
- Create: `gemscanner/synthetic/toy_gem.py`
- Test: `tests/synthetic/test_toy_gem.py`

**Interfaces:**
- Consumes: `trimesh`.
- Produces:
  - `make_toy_gem(n=8, r_girdle=5.0, r_table=3.0, z_table=2.0, z_girdle_top=0.4, z_girdle_bottom=-0.4, z_culet=-4.0) -> (vertices (V,3) float, planes list[(normal (3,) unit, d float)])`. Solid: a girdle **band** — two `n`-gon rings at radius `r_girdle`, at `z_girdle_top` and `z_girdle_bottom` (this band creates the `n` **vertical** girdle facets); a smaller table polygon (radius `r_table`) at `z_table` (→ `n` crown + 1 table); a single apex culet at `z_culet` (→ `n` pavilion). Exactly `3n+1` distinct planes. Outward normals, body on `normal·x <= d` side.
  - `unique_face_planes(mesh, angle_tol_deg=1.0, offset_tol=1e-3) -> list[(normal (3,), d)]`: clusters a trimesh's coplanar triangles into distinct facet planes.

- [ ] **Step 1: Write the failing test**

```python
# tests/synthetic/test_toy_gem.py
import numpy as np
from gemscanner.synthetic.toy_gem import make_toy_gem, unique_face_planes

def test_toy_gem_has_all_four_facet_families():
    n = 8
    verts, planes = make_toy_gem(n=n)
    normals = np.array([p[0] for p in planes])
    # all normals unit length
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-6)
    top = [p for p in planes if p[0][2] > 0.99]            # table, +z
    vertical = [p for p in planes if abs(p[0][2]) < 0.05]  # girdle, z~0
    crown = [p for p in planes if 0.05 <= p[0][2] <= 0.99] # tilted up
    pavilion = [p for p in planes if p[0][2] < -0.05]      # tilted down
    assert len(top) == 1
    assert len(vertical) == n
    assert len(crown) == n
    assert len(pavilion) == n
    assert len(planes) == 3 * n + 1     # all four families, nothing else

def test_unique_face_planes_dedupes_coplanar_triangles():
    verts, _ = make_toy_gem(n=6)
    import trimesh
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    planes = unique_face_planes(hull)
    # a hexagonal toy gem: 1 table + 6 girdle + 6 crown + 6 pavilion = 19 distinct planes
    assert len(planes) == 19
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/synthetic/test_toy_gem.py -v`
Expected: FAIL with `ModuleNotFoundError: gemscanner.synthetic.toy_gem`.

- [ ] **Step 3: Write minimal implementation**

```python
# gemscanner/synthetic/toy_gem.py
"""Parametric convex faceted test solid + ground-truth plane extraction."""
import numpy as np
import trimesh


def make_toy_gem(n=8, r_girdle=5.0, r_table=3.0, z_table=2.0,
                 z_girdle_top=0.4, z_girdle_bottom=-0.4, z_culet=-4.0):
    """Return (vertices, planes) for a convex faceted 'toy gem'.

    Geometry: a girdle BAND (two n-gon rings at radius r_girdle, at
    z_girdle_top and z_girdle_bottom) gives n vertical girdle facets; a smaller
    table ring gives n crown facets + a table; a culet apex gives n pavilion
    facets. Same-radius rings make each girdle facet a vertical planar quad ->
    the convex hull has exactly 3n+1 distinct planes. planes are the unique
    outward face planes (normal unit, body on normal.x <= d)."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cos, sin = np.cos(a), np.sin(a)
    g_top = np.column_stack([r_girdle * cos, r_girdle * sin, np.full(n, z_girdle_top)])
    g_bot = np.column_stack([r_girdle * cos, r_girdle * sin, np.full(n, z_girdle_bottom)])
    table = np.column_stack([r_table * cos, r_table * sin, np.full(n, z_table)])
    culet = np.array([[0.0, 0.0, z_culet]])
    verts = np.vstack([g_top, g_bot, table, culet])
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    planes = unique_face_planes(hull)
    return np.asarray(hull.vertices, float), planes


def unique_face_planes(mesh, angle_tol_deg=1.0, offset_tol=1e-3):
    """Cluster a convex mesh's triangles into distinct (normal, d) facet planes."""
    normals = np.asarray(mesh.face_normals, float)
    # signed offset d = normal . (any vertex of the face)
    tri0 = mesh.vertices[mesh.faces[:, 0]]
    d = np.einsum("ij,ij->i", normals, tri0)
    cos_tol = np.cos(np.radians(angle_tol_deg))
    out = []
    for nrm, off in zip(normals, d):
        for i, (kn, kd) in enumerate(out):
            if float(np.dot(nrm, kn)) >= cos_tol and abs(off - kd) <= offset_tol:
                break
        else:
            out.append((nrm / np.linalg.norm(nrm), float(off)))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/synthetic/test_toy_gem.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/synthetic/toy_gem.py tests/synthetic/test_toy_gem.py
git commit -m "feat(synthetic): parametric toy-gem builder + unique face-plane extraction"
```

---

### Task 3: Support-map extraction from silhouettes

Expose the stone's support function `H(view, z)` as arrays — the raw material the facet fit consumes — reusing the existing carve inputs without changing `strip_intersection`'s behaviour.

**Files:**
- Create: `gemscanner/reconstruction/support.py`
- Test: `tests/reconstruction/test_support.py`

**Interfaces:**
- Consumes: `vision.silhouette.extract_silhouette` + `row_spans`, `coords.row_to_z`, `coords.axis_column_at_row`, `coords.column_to_projection`, `base.ReconstructionParams`.
- Produces: `support_maps(dataset, params=None) -> SupportMaps` dataclass with fields:
  - `z (H,) float` — object height per row (mm)
  - `theta (V,) float` — view angle per frame (rad)
  - `h_right (H, V) float` — support in `+n_i` (`= pmax`), NaN where row empty
  - `h_left  (H, V) float` — support in `−n_i` (`= −pmin`), NaN where row empty
  - `valid (H, V) bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_support.py
import numpy as np
from gemscanner.synthetic.generator import generate_polyhedron_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.support import support_maps

def _box(hx, hy, hz):
    return np.array([[sx*hx, sy*hy, sz*hz]
                     for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)

def test_support_of_box_is_half_width_at_theta0(tmp_path):
    out = generate_polyhedron_scan(str(tmp_path / "box"), _box(4, 2, 5),
                                   n_views=4, mm_per_px=0.05, width=400, height=400)
    sm = support_maps(load_dataset(out))
    # theta=0 view: support in +x is hx = 4 mm, over the box's z-range
    col = np.nanmedian(sm.h_right[:, 0])
    assert abs(col - 4.0) <= 0.05        # within one pixel (mm_per_px)
    # rows outside the box are invalid
    assert sm.valid.any() and not sm.valid.all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_support.py -v`
Expected: FAIL with `ModuleNotFoundError: gemscanner.reconstruction.support`.

- [ ] **Step 3: Write minimal implementation**

```python
# gemscanner/reconstruction/support.py
import math
from dataclasses import dataclass
import numpy as np
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans
from gemscanner.reconstruction.base import ReconstructionParams


@dataclass
class SupportMaps:
    z: np.ndarray          # (H,)
    theta: np.ndarray      # (V,)
    h_right: np.ndarray    # (H, V)
    h_left: np.ndarray     # (H, V)
    valid: np.ndarray      # (H, V) bool


def support_maps(dataset, params=None):
    params = params if params is not None else ReconstructionParams()
    m = dataset.manifest
    H, mmpp = m.image_height, m.mm_per_px
    V = dataset.frame_count()

    z = np.array([row_to_z(v, H, mmpp) for v in range(H)])
    theta = np.radians(np.asarray(m.angles_deg, float))
    h_right = np.full((H, V), np.nan)
    h_left = np.full((H, V), np.nan)

    for i in range(V):
        img = dataset.load_frame(i)
        mask = extract_silhouette(img, params.threshold, params.holder_mask_rows)
        spans = row_spans(mask)
        for v in range(H):
            L, R = spans[v]
            if L < 0:
                continue
            axc = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            pmin = column_to_projection(L, axc, mmpp)
            pmax = column_to_projection(R, axc, mmpp)
            h_right[v, i] = pmax
            h_left[v, i] = -pmin

    valid = ~np.isnan(h_right)
    return SupportMaps(z=z, theta=theta, h_right=h_right, h_left=h_left, valid=valid)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_support.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/support.py tests/reconstruction/test_support.py
git commit -m "feat(reconstruction): support-map extraction H(view,z) from silhouettes"
```

---

### Task 4: Affine tangent fit → exact plane recovery (pure math)

The crux math, isolated and unit-tested: fit `H = β + α·z` robustly, and convert a `(θ*, α, β)` triple into an exact unit plane `(a,b,c,d)`.

**Files:**
- Create: `gemscanner/reconstruction/facet_fit.py`
- Test: `tests/reconstruction/test_facet_fit.py`

**Interfaces:**
- Consumes: `numpy`.
- Produces:
  - `plane_from_affine(theta_star, alpha, beta) -> (a, b, c, d)` unit normal + offset, using `m=1/√(1+α²)`, `c=−α/√(1+α²)`, `a=m·cosθ*`, `b=−m·sinθ*`, `d=β·m` (matches `n_i=(cosθ,−sinθ)`).
  - `fit_affine_support(z, h, mask, min_inliers=8, resid_tol_mm=0.05) -> (alpha, beta, rms, n_inliers)`: robust (Theil–Sen slope + median intercept, then one inlier-trim + refit). Returns `alpha=nan` if fewer than `min_inliers` valid points.

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_facet_fit.py
import numpy as np
from gemscanner.reconstruction.facet_fit import plane_from_affine, fit_affine_support

def test_plane_from_affine_vertical_facet():
    # alpha=0 => vertical facet (c=0); theta*=0 => normal +x
    a, b, c, d = plane_from_affine(0.0, alpha=0.0, beta=5.0)
    assert np.allclose([a, b, c, d], [1.0, 0.0, 0.0, 5.0], atol=1e-9)

def test_plane_from_affine_45deg():
    # a 45-degree facet facing +x: normal ~ (cos45,0,sin45) with c>0 => alpha<0
    a, b, c, d = plane_from_affine(0.0, alpha=-1.0, beta=3.0)
    assert np.allclose([a, b, c], [np.sqrt(0.5), 0.0, np.sqrt(0.5)], atol=1e-9)
    assert np.isclose(a*a + b*b + c*c, 1.0)
    # d = beta*m with m=1/sqrt(2); verifies the d-scaling (m!=1 here)
    assert np.isclose(d, 3.0 / np.sqrt(2.0))

def test_fit_affine_robust_to_outliers():
    z = np.linspace(-4, 4, 60)
    h = 2.0 + 0.5 * z
    h[10] += 3.0; h[40] -= 2.5           # terracing-style outliers
    mask = np.ones_like(z, bool)
    alpha, beta, rms, n = fit_affine_support(z, h, mask)
    assert abs(alpha - 0.5) < 0.02 and abs(beta - 2.0) < 0.05
    assert n >= 50
    assert rms < 0.01                    # rms scoped to inliers, not outliers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_facet_fit.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# gemscanner/reconstruction/facet_fit.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_facet_fit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_fit.py
git commit -m "feat(reconstruction): affine support fit + exact plane recovery math"
```

---

### Task 5: Gauss-sphere facet seeding

Cluster a smooth mesh's face normals into distinct facet orientations — telling the refit *how many* facets and *which azimuth* each lives at. Greedy angular clustering keeps it dependency-light and deterministic.

**Files:**
- Modify: `gemscanner/reconstruction/facet_fit.py` (add `seed_facets`)
- Test: `tests/reconstruction/test_facet_fit.py` (append)

**Interfaces:**
- Consumes: `trimesh` mesh (`.face_normals`, `.area_faces`).
- Produces: `seed_facets(mesh, merge_deg=8.0, min_area_frac=0.005) -> list[dict]`, each `{"normal": (3,) unit, "azimuth": float rad, "tilt": float, "area": float}`, sorted by area desc. `azimuth = atan2(-b, a)` so it maps straight to a view angle under `n_i=(cosθ,−sinθ)`; `tilt = normal_z`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/reconstruction/test_facet_fit.py
from gemscanner.reconstruction.facet_fit import seed_facets
from gemscanner.synthetic.toy_gem import make_toy_gem
import trimesh

def test_seed_facets_recovers_distinct_orientations():
    verts, planes = make_toy_gem(n=8)
    hull = trimesh.Trimesh(vertices=verts).convex_hull
    seeds = seed_facets(hull, merge_deg=8.0)
    # ~ table(1) + girdle(8) + crown(8) + pavilion(8) distinct orientations
    assert 20 <= len(seeds) <= 30
    # a near +z table orientation is present
    assert any(s["normal"][2] > 0.95 for s in seeds)
    # azimuth maps back to the normal's horizontal direction
    for s in seeds[:5]:
        a, b = s["normal"][0], s["normal"][1]
        assert abs(np.cos(s["azimuth"]) - a / max(np.hypot(a, b), 1e-9)) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_facet_fit.py::test_seed_facets_recovers_distinct_orientations -v`
Expected: FAIL with `ImportError: cannot import name 'seed_facets'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to gemscanner/reconstruction/facet_fit.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_facet_fit.py -v`
Expected: PASS (all facet_fit tests).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_fit.py
git commit -m "feat(reconstruction): Gauss-sphere facet seeding from a smooth mesh"
```

---

### Task 6: Plane recovery, half-space assembly, and the FacetReconstructor

Tie it together: for each seed, refit the exact plane on the raw support maps (with azimuth refinement); add table/culet; merge duplicates; intersect half-spaces into a watertight polytope; emit mesh + edges + meet-points. End-to-end synthetic test asserts near-exact recovery.

**Files:**
- Modify: `gemscanner/reconstruction/base.py:4-17` (add facet fields — needed by this task's code)
- Modify: `gemscanner/reconstruction/facet_fit.py` (add recovery, assembly, `FacetReconstructor`)
- Test: `tests/reconstruction/test_facet_reconstruct.py`

**Interfaces:**
- Consumes: `support_maps` (Task 3), `plane_from_affine`/`fit_affine_support`/`seed_facets` (Tasks 4–5), `soft_hull.SoftHullReconstructor` (seed mesh), `scipy.spatial.HalfspaceIntersection`, `scipy.optimize.linprog`, `trimesh`.
- Produces:
  - `ReconstructionParams` facet fields (see Step 1b) — consumed here and by Task 7's dispatch.
  - `recover_planes(sm, seeds, params) -> list[dict]`, each `{"plane": (a,b,c,d), "rms": float, "n_inliers": int, "source": "tangent"|"extremal"}`.
  - `planes_to_polytope(planes) -> (trimesh.Trimesh, vertices (K,3), edges (E,2) int)`.
  - `class FacetReconstructor: reconstruct(self, dataset, params=None) -> trimesh.Trimesh` with `mesh.metadata["facets"]` = `{"planes":..., "vertices":..., "edges":...}`.

- [ ] **Step 1a: Add the facet params (prereq for the code below)**

```python
# gemscanner/reconstruction/base.py — add to ReconstructionParams (after `method`)
    # facet method (method="facet"): unsupervised facet-plane recovery
    facet_min_inliers: int = 12
    facet_merge_deg: float = 6.0
    facet_view_search: int = 4
    facet_axial_cos: float = 0.95      # |normal_z| above this = table/culet, not tangent
    facet_fallback: bool = True
    # (facet_planarity_tol_mm was dropped in final-review cleanup as unused)
```

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_facet_reconstruct.py
import numpy as np
import trimesh
from gemscanner.synthetic.toy_gem import make_toy_gem, unique_face_planes
from gemscanner.synthetic.generator import generate_polyhedron_scan
from gemscanner.storage.dataset import load_dataset
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.facet_fit import FacetReconstructor

def _min_normal_error_deg(recovered, gt):
    errs = []
    for nr in recovered:
        c = max(abs(float(np.dot(nr, g))) for g in gt)
        errs.append(np.degrees(np.arccos(min(1.0, c))))
    return np.array(errs)

def test_facet_reconstruction_matches_ground_truth(tmp_path):
    verts, gt_planes = make_toy_gem(n=8)
    gt_normals = [p[0] for p in gt_planes]
    out = generate_polyhedron_scan(str(tmp_path / "gem"), verts, n_views=180,
                                   mm_per_px=0.05, width=500, height=500)
    mesh = FacetReconstructor().reconstruct(load_dataset(out), ReconstructionParams())
    assert mesh.is_watertight
    rec_normals = [p[:3] / np.linalg.norm(p[:3])
                   for p in mesh.metadata["facets"]["planes"]]
    errs = _min_normal_error_deg(rec_normals, gt_normals)
    # every recovered non-axial facet matches some GT facet closely
    assert np.median(errs) < 1.0
    # volume within a few percent of the true solid
    truth = trimesh.Trimesh(vertices=verts).convex_hull
    assert abs(mesh.volume - truth.volume) / truth.volume < 0.05
    # meet-points and edges are populated
    assert len(mesh.metadata["facets"]["vertices"]) >= 6
    assert len(mesh.metadata["facets"]["edges"]) >= 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_facet_reconstruct.py -v`
Expected: FAIL with `ImportError: cannot import name 'FacetReconstructor'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to gemscanner/reconstruction/facet_fit.py
import trimesh
from scipy.spatial import HalfspaceIntersection
from scipy.optimize import linprog
from gemscanner.reconstruction.support import support_maps
from gemscanner.reconstruction.base import ReconstructionParams


def _nearest_view(theta, az):
    d = np.angle(np.exp(1j * (theta - az)))   # wrapped difference
    return int(np.argmin(np.abs(d)))


def recover_planes(sm, seeds, params):
    """Refit each seed to an exact plane on the raw support maps; add table/culet."""
    planes = []
    for s in seeds:
        if abs(s["tilt"]) > params.facet_axial_cos:      # near-axial -> extremal
            continue
        best = None
        i0 = _nearest_view(sm.theta, s["azimuth"])
        for di in range(-params.facet_view_search, params.facet_view_search + 1):
            i = (i0 + di) % len(sm.theta)
            alpha, beta, rms, n = fit_affine_support(
                sm.z, sm.h_right[:, i], sm.valid[:, i],
                min_inliers=params.facet_min_inliers)
            if np.isnan(alpha):
                continue
            if best is None or rms < best[0]:
                best = (rms, sm.theta[i], alpha, beta, n)
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
        sm = support_maps(dataset, params)
        planes = recover_planes(sm, seeds, params)
        if len(planes) < 4:
            raise ValueError("facet recovery failed: too few planes")
        mesh, verts, edges = planes_to_polytope(planes)
        mesh.metadata["facets"] = {
            "planes": [p["plane"] for p in planes],
            "vertices": verts, "edges": edges}
        return mesh
```

Note: the `facet_*` params this code reads were added in Step 1a above.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_facet_reconstruct.py -v`
Expected: PASS (watertight, median normal error < 1°, volume within 5%).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/facet_fit.py tests/reconstruction/test_facet_reconstruct.py
git commit -m "feat(reconstruction): plane recovery + half-space assembly (FacetReconstructor)"
```

---

### Task 7: Params, pipeline dispatch, and graceful fallback

Wire `method="facet"` into `ReconstructionParams` and `pipeline.reconstruct_dataset`, with a fallback to the selected smooth method when the stone isn't cleanly faceted.

**Files:**
- Modify: `gemscanner/reconstruction/pipeline.py:9-12` (dispatch)
- Test: `tests/reconstruction/test_pipeline_facet.py`

**Interfaces:**
- Consumes: `FacetReconstructor` (Task 6), `SoftHullReconstructor`, `StripIntersectionReconstructor`, the `facet_*` params added in Task 6 Step 1a.
- Produces: `reconstruct_dataset(path, params)` dispatches `method=="facet"` → `FacetReconstructor`, falling back to strip/soft-hull on failure when `facet_fallback`.

- [ ] **Step 1: Write the failing test**

```python
# tests/reconstruction/test_pipeline_facet.py
import numpy as np
from gemscanner.synthetic.toy_gem import make_toy_gem
from gemscanner.synthetic.generator import (generate_polyhedron_scan,
                                            generate_ellipsoid_scan)
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.pipeline import reconstruct_dataset

def test_pipeline_facet_method(tmp_path):
    verts, _ = make_toy_gem(n=8)
    out = generate_polyhedron_scan(str(tmp_path / "gem"), verts, n_views=180,
                                   mm_per_px=0.05, width=500, height=500)
    mesh = reconstruct_dataset(out, ReconstructionParams(method="facet"))
    assert mesh.is_watertight and "facets" in mesh.metadata

def test_pipeline_facet_falls_back_on_non_faceted(tmp_path):
    # an ellipsoid has no stable facets -> fallback yields a (smooth) mesh, no crash
    out = generate_ellipsoid_scan(str(tmp_path / "ell"), rx=4, ry=4, rz=5,
                                  n_views=60, mm_per_px=0.05, width=400, height=400)
    p = ReconstructionParams(method="facet", facet_fallback=True)
    mesh = reconstruct_dataset(out, p)
    assert mesh.vertices.shape[0] > 0     # produced something instead of raising
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reconstruction/test_pipeline_facet.py -v`
Expected: FAIL — `TypeError`/`AttributeError` on unknown `method="facet"` fields, or the second test raises `ValueError`.

- [ ] **Step 3: Write minimal implementation**

The `facet_*` params were added in Task 6 Step 1a; this task only adds dispatch.

```python
# gemscanner/reconstruction/pipeline.py — replace the body of reconstruct_dataset
def reconstruct_dataset(dataset_path, params=None):
    dataset = load_dataset(dataset_path)
    params = params if params is not None else ReconstructionParams()
    if params.method == "facet":
        from gemscanner.reconstruction.facet_fit import FacetReconstructor
        try:
            return FacetReconstructor().reconstruct(dataset, params)
        except Exception as exc:
            if not params.facet_fallback:
                raise
            # facet is the highest-quality tier; degrade to the smooth
            # metrology method (soft_hull), and never fail silently so a real
            # regression (or a non-faceted stone) is visible, not masked.
            warnings.warn(f"facet reconstruction failed ({exc}); falling back "
                          "to soft_hull", RuntimeWarning)
            from gemscanner.reconstruction.soft_hull import SoftHullReconstructor
            return SoftHullReconstructor().reconstruct(dataset, params)
    if params.method == "soft_hull":
        from gemscanner.reconstruction.soft_hull import SoftHullReconstructor
        return SoftHullReconstructor().reconstruct(dataset, params)
    return StripIntersectionReconstructor().reconstruct(dataset, params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reconstruction/test_pipeline_facet.py -v && pytest -q`
Expected: PASS (both new tests, and the full suite stays green).

- [ ] **Step 5: Commit**

```bash
git add gemscanner/reconstruction/base.py gemscanner/reconstruction/pipeline.py tests/reconstruction/test_pipeline_facet.py
git commit -m "feat(reconstruction): wire method=facet into pipeline with fallback"
```

---

### Task 8: GUI picker entry

Add "Faceted gem (planar)" to the reconstruction panel so a user can select the method when scanning a faceted stone.

**Files:**
- Modify: `gemscanner/gui/reconstruction_panel.py:12-21` (append to `CHOICES`)
- Test: `tests/gui/test_reconstruction_panel.py` (create or append if it exists)

**Interfaces:**
- Consumes: existing `ReconstructionPanel` pattern.
- Produces: a 5th choice mapping to `{"method": "facet", "edge_median_rows": 0, "axial_median_rows": 0}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_reconstruction_panel.py  (append; create with this import guard if new)
import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from gemscanner.gui.reconstruction_panel import ReconstructionPanel

def _app():
    return QApplication.instance() or QApplication([])

def test_faceted_choice_present_and_maps_to_facet_method():
    _app()
    panel = ReconstructionPanel()
    labels = [c[0] for c in ReconstructionPanel.CHOICES]
    assert "Faceted gem (planar)" in labels
    idx = labels.index("Faceted gem (planar)")
    panel.set_index(idx)
    assert panel.selected_kwargs()["method"] == "facet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/gui/test_reconstruction_panel.py -v`
Expected: FAIL — `"Faceted gem (planar)" not in labels`.

- [ ] **Step 3: Write minimal implementation**

```python
# gemscanner/gui/reconstruction_panel.py — append inside the CHOICES list
        ("Faceted gem (planar)",
         {"method": "facet", "edge_median_rows": 0, "axial_median_rows": 0}),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/gui/test_reconstruction_panel.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gemscanner/gui/reconstruction_panel.py tests/gui/test_reconstruction_panel.py
git commit -m "feat(gui): add 'Faceted gem (planar)' reconstruction choice"
```

---

### Task 9: gem04 validation (real-scan verification)

Prove the method on the real faceted scan and record the numbers the design promised: per-facet planarity, sharp edges, watertightness, dimensions vs the existing `gem.stl`. This task delivers a runnable script and a short results note — no product code.

**Files:**
- Create: `scripts/validate_facet_gem04.py`
- Create: `docs/superpowers/notes/2026-07-11-facet-gem04-results.md`

**Interfaces:**
- Consumes: `pipeline.reconstruct_dataset`, `storage.mesh_io` (existing STL loader — confirm function name in `gemscanner/storage/mesh_io.py`), `trimesh`.
- Produces: printed metrics + a written results note.

- [ ] **Step 1: Write the validation script**

```python
# scripts/validate_facet_gem04.py
"""Reconstruct scans/gem04 with method=facet and report facet-quality metrics."""
import numpy as np, trimesh
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.pipeline import reconstruct_dataset

SCAN = "scans/gem04"

def main():
    mesh = reconstruct_dataset(SCAN, ReconstructionParams(method="facet"))
    fac = mesh.metadata.get("facets", {})
    planes = fac.get("planes", [])
    print(f"facets={len(planes)}  vertices(meet-points)={len(fac.get('vertices', []))}"
          f"  edges={len(fac.get('edges', []))}")
    print(f"watertight={mesh.is_watertight}  volume={mesh.volume:.2f} mm^3")
    ext = mesh.bounding_box.extents
    print(f"extents (mm): {ext[0]:.3f} x {ext[1]:.3f} x {ext[2]:.3f}")
    # planarity: max distance of assigned hull vertices to each plane (um)
    V = np.asarray(mesh.vertices)
    worst = 0.0
    for (a, b, c, d) in planes:
        dist = np.abs(V @ np.array([a, b, c]) - d)
        worst = max(worst, 1000.0 * dist[dist < 0.02].max() if (dist < 0.02).any() else 0)
    print(f"worst on-facet planarity residual: {worst:.1f} um")
    try:
        ref = trimesh.load(f"{SCAN}/gem.stl")
        print(f"reference gem.stl extents (mm): {ref.bounding_box.extents}")
    except Exception as e:
        print(f"(no reference comparison: {e})")
    mesh.export("scans/gem04/gem_facet.stl")
    print("wrote scans/gem04/gem_facet.stl")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run: `python scripts/validate_facet_gem04.py`
Expected: prints facet count, watertight=True, extents matching `gem.stl` to within a few tens of µm, and a planarity residual far below the ~68 µm terracing baseline recorded in the striation notes.

- [ ] **Step 3: Record results**

Write `docs/superpowers/notes/2026-07-11-facet-gem04-results.md` with the printed numbers, a one-line verdict (does it beat the terracing baseline and stay dimensionally faithful?), and any threshold tuning applied (`facet_merge_deg`, `facet_min_inliers`). If facets are over/under-segmented, note the adjusted params.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_facet_gem04.py docs/superpowers/notes/2026-07-11-facet-gem04-results.md
git commit -m "test(reconstruction): validate faceted method on gem04 real scan"
```

---

## Self-Review

**Spec coverage:**
- §2/§2.1 support-function insight → Tasks 3, 4. ✓
- §4.1 support sampling → Task 3. ✓
- §4.2 Gauss-sphere seed → Task 5. ✓
- §4.3 refit + azimuth refine + merge → Task 6 (`recover_planes`, `_merge_planes`). ✓
- §4.4 table/culet extremal planes → Task 6 (`recover_planes` extremal branch). ✓
- §4.5 half-space assembly, edges, meet-points → Task 6 (`planes_to_polytope`). ✓
- §4.6 fallback → Task 7. ✓
- §5 data structures → Task 6 `mesh.metadata["facets"]` (planes/vertices/edges). Note: the spec's richer `FacetModel` (inter-facet angles, symmetry order) is deferred to metadata basics; angle/symmetry tables are optional gemology extras, flagged in §10 open items, not required for artifact-free geometry. ✓ (scoped)
- §6 params + pipeline + GUI → Tasks 7, 8. ✓
- §7 synthetic GT + gem04 validation → Tasks 1, 2, 9. ✓
- §9a build order → Tasks ordered synthetic-GT-first. ✓

**Placeholder scan:** No TBD/TODO; every code step has concrete code; commands have expected output. ✓

**Type consistency:** `plane` tuples are `(a,b,c,d)` everywhere; `plane_from_affine` returns that; `recover_planes`/`_merge_planes`/`planes_to_polytope` all consume `p["plane"]` as `(a,b,c,d)`; `seed_facets` dict keys (`normal/azimuth/tilt/area`) match `recover_planes` usage; `support_maps` fields (`z/theta/h_right/h_left/valid`) match Task 4/6 usage. ✓

**Ordering check:** `facet_*` params are added in Task 6 Step 1a (where first used); Task 7 only adds pipeline dispatch. No forward dependency remains. ✓
