# Faceted-Gem Reconstruction (unsupervised facet-plane recovery)

**Date:** 2026-07-11
**Status:** Design approved, pending spec review → implementation plan
**Scope:** A new, user-selectable reconstruction method that turns a turntable
silhouette scan of a *convex faceted* gemstone into a clean flat-faceted
polyhedron — real facets, sharp edges, exact meet-points — with **no** terracing
or reconstruction artifacts.

---

## 1. Problem

The existing pipeline (`strip_intersection` → `mesh.loft_slices_to_mesh`) builds a
turntable **visual hull** by carving each image row's cross-section independently
and lofting the stacked rings. Because rows are carved independently, sloped
surfaces show horizontal "terracing" / strike-lines. The shipped de-terracing
options (`edge_median_rows`, `axial_median_rows`, `soft_hull`) *denoise* this
wobble but never recover the underlying **flat facets** or the **sharp lines and
points where facets meet**. See `[[gemscanner-striation-fix]]`.

For a **faceted** stone we can do better than denoising: we can recover the
actual facet planes and rebuild the stone as the polyhedron they define.

## 2. Key insight — faceting is exactly solvable from the support function

A cut gemstone is (essentially always) a **convex polyhedron**. Silhouette
carving can only ever recover the convex hull anyway, so this assumption costs
nothing. Two consequences:

1. **Every facet is a supporting plane of the hull.** It appears as a straight
   tangent segment of the silhouette in the views where it faces grazing.
2. **Given the facet planes, everything else is exact and free.** Intersecting
   the facet half-spaces yields a watertight convex polytope; its **edges are
   where 2 planes meet** and its **meet-points are where ≥3 planes meet**. Flat
   by construction — no terracing, no re-meshing.

So the problem reduces from *"find edges on a noisy mesh"* to **"recover the set
of facet planes."** Edges and meet-points then fall out of the plane arrangement.

### 2.1 The support-function formulation (the crux)

`strip_intersection` already measures, per view `i` (angle `θ_i`) and per height
`z`, how far the silhouette tangent reaches. In the code's convention the slice
at height `z` satisfies `pmin(i,z) ≤ n_i · (x,y) ≤ pmax(i,z)` with
`n_i = (cos θ_i, −sin θ_i)`. Therefore:

- `H_right(i, z) = pmax(i, z)` = 2D support of the slice in direction `+n_i`
- `H_left(i, z)  = −pmin(i, z)` = 2D support in direction `−n_i`

Stacked over all `i` and `z`, `H` **is the support function of the convex stone**
sampled on horizontal directions, resolved per height. (`H_left(i,·)` equals
`H_right(i+180°, ·)` — a built-in redundancy/calibration check.)

Now take a facet plane with unit outward normal `(a, b, c)` and offset `d`:
`a·x + b·y + c·z = d`, body on the `≤ d` side. Let `m = √(a²+b²)`. At height `z`
the facet contributes a slice edge with 2D outward normal `(a, b)/m`, active in
the single view whose `n_i = (a, b)/m`. At that view:

```
H_right(i*, z) = (d − c·z) / m  =  β + α·z      with  α = −c/m ,  β = d/m
```

**A facet is edge-on in exactly one azimuth, and there its support is an affine
(straight) function of height `z`.** From that one affine fit the whole plane is
recovered exactly (`i*` gives azimuth, unit-normalize with `m²+c² = 1`):

```
m = 1/√(1+α²)              c = −α/√(1+α²)
a =  m·cos θ_{i*}          b = −m·sin θ_{i*}        d = β·m
```

Facet families in this single model:
- **Girdle / vertical facets** (`c ≈ 0`): `α ≈ 0` → support constant in `z`.
- **Crown / pavilion facets** (inclined): general `α`. Captured cleanly.
- **Table / culet** (near-axial normal, `m ≈ 0`): edge-on in *no* horizontal
  view. A single vertical turntable axis only samples horizontal view
  directions, so these are **not** recoverable from tangents. They are recovered
  separately as the **extreme-z horizontal plateaus** (top = table, bottom =
  culet). This is a fundamental limitation of single-axis turntable scanning and
  is handled explicitly, not left to fail.

For a convex stone, every non-axial facet is grazing-visible at its own azimuth,
and we sample all azimuths (180 views / 2°), so **completeness is achievable.**

## 3. Chosen approach — hybrid (approved)

- **Cut priors:** fully unsupervised (no cut type, no facet count).
- **Plane source:** hybrid — a smooth mesh *seeds* how many facets and their
  rough orientation (robust), then each plane is *refit against the raw
  silhouette support samples* (exact, artifact-free).
- **Convexity:** assumed (standard cuts; also the only thing silhouettes recover).

## 4. Pipeline — new `method="facet"`

New module `gemscanner/reconstruction/facet_fit.py`, dispatched from
`pipeline.reconstruct_dataset` (and the `StripIntersectionReconstructor`
neighbourhood) exactly like `soft_hull` is today.

1. **Support sampling.** Reuse the existing per-view carving to build the
   `H_right(i, z)` / `H_left(i, z)` support maps (mm), plus the per-view valid-z
   ranges. No new imaging code; this is the same `row_spans` → projection data
   already computed, retained as arrays instead of only consumed by clipping.

2. **Seed (mesh side of the hybrid).** Run the soft-hull reconstruction (smooth,
   terracing-free normals), then cluster its face normals on the Gauss sphere
   (area-weighted). Output: estimated **facet count** and each facet's rough
   `(azimuth, tilt)` and z-support window. Purpose: avoid over/under-
   segmentation and tell stage 3 where to look. The seed geometry is otherwise
   discarded.

3. **Refit (silhouette side).** For each seed facet, take the raw support
   samples in its azimuth window and its z-window and fit `H = β + α·z` by robust
   (Theil–Sen / RANSAC) regression. Refine the azimuth `i*` by minimizing the
   affine residual (sub-view-step). Convert `(θ_{i*}, α, β)` → exact
   `(a, b, c, d)`. Discard fits with too few inliers or excessive residual;
   merge planes that coincide within tolerance (rotational-symmetry duplicates).

4. **Table / culet.** Fit horizontal planes `z = z_max` (table) and `z = z_min`
   (culet) from the robust z-extents across all views. Include only if a genuine
   flat plateau exists (guards against a pointed culet, which is just a vertex).

5. **Assemble the polytope.** Intersect all facet half-spaces
   `{ x : a·x + b·y + c·z ≤ d }` into a convex polytope (half-space intersection
   about an interior point). Emit:
   - the watertight faceted **mesh** (each facet one planar polygon, fan- or
     ear-triangulated),
   - **edges** (adjacent-plane intersections) and **meet-points** (polytope
     vertices) as first-class outputs.

6. **Fallback.** If facet fitting is unstable — planarity residuals too high,
   facet count won't converge, or the assembled polytope loses volume vs the
   visual hull beyond tolerance — fall back to the currently-selected smooth
   method and surface a clear message ("stone does not appear cleanly faceted").

## 5. Data structures

```
FacetPlane:   normal (a,b,c) unit, offset d, azimuth θ*, (α, β),
              support/inlier count, rms residual (mm), source ∈ {tangent, extremal}
FacetModel:   planes: list[FacetPlane]
              polytope vertices (meet-points), edges (index pairs),
              face→vertex loops, per-facet planarity residual,
              symmetry order (detected), inter-facet angle table
```

`reconstruct(...)` still returns a `trimesh.Trimesh` (drop-in for callers/GUI);
`FacetModel` is attached (e.g. `mesh.metadata["facets"]`) and optionally written
alongside the STL for gemology (facet count, angles, symmetry).

## 6. Integration & outputs

- `ReconstructionParams`: add `method="facet"` plus a small number of tunables
  (`facet_min_inliers`, `facet_merge_deg`, `facet_planarity_tol_mm`,
  `facet_fallback=True`). Keep defaults conservative.
- `pipeline.reconstruct_dataset`: dispatch `method=="facet"` →
  `FacetReconstructor`, mirroring the existing `soft_hull` branch.
- **GUI:** a 5th `ReconstructionPanel` entry, **"Faceted gem (planar)"**, mapping
  to `method="facet"`. Global choice, consistent with the current panel.
- **Deps:** reuses `numpy`, `trimesh`, `scikit-image` (already required by
  soft-hull, used for the seed). Half-space intersection via `scipy.spatial`
  (`HalfspaceIntersection`/`ConvexHull`) — `scipy` is already an indirect dep;
  confirm and pin during planning. No new heavy dependency expected.

## 7. Validation

- **Synthetic faceted ground-truth (build first).** Extend the synthetic
  generator (today only `generate_ellipsoid_scan`) with
  `generate_polyhedron_scan(...)` that renders orthographic silhouettes of a
  *known* convex polyhedron (e.g. a parametric round-brilliant-like solid) using
  the existing projection/manifest conventions. This yields exact ground-truth
  planes / edges / meet-points, enabling unit tests that assert recovery to
  within tight tolerances (normals < ~0.5°, offsets < ~1 voxel). The ellipsoid
  generator cannot test faceting; this closes that gap.
- **Real scan: `scans/gem04`** (180 views / 2°, faceted; its `total` de-terracing
  metric is real facets per `[[gemscanner-striation-fix]]`). Measure:
  per-facet planarity residual (µm), edge sharpness, watertightness, facet count
  / symmetry plausibility, and overall dimensions vs the existing
  `scans/gem04/gem.stl`. Diameter/height must match the visual hull within the
  tolerance already established for the median methods (< ~1 µm bias expected;
  removal of terracing is near zero-mean).
- TDD throughout, matching the repo's existing test discipline.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Facet-count instability (over/under-segmentation) | Gauss-sphere seed + symmetry-aware merge; residual-gated acceptance |
| Girdle vs adjacent shallow facet ambiguity | Azimuth refine by affine-residual minimization; separate near-`α=0` handling |
| Axis / calibration error smears the affine fit | `H_left(i)` vs `H_right(i+180°)` redundancy check; robust regression |
| Table/culet not fittable from tangents | Explicit extremal-z horizontal-plane step; plateau guard |
| Stone not actually cleanly faceted (cabochon, worn) | Confidence gate → fallback to smooth method with a clear message |
| Half-space intersection degeneracy (near-parallel planes) | Merge within `facet_merge_deg`; interior-point solve; keep-largest safety |

## 9. Explicit non-goals (YAGNI)

- No non-convex / concave facet recovery (silhouettes can't see it; out of scope).
- No named-cut template fitting or cut identification (unsupervised only).
- No multi-axis / tilt-scanning to recover table/culet by tangent (hardware change).
- No change to capture, calibration, or the other reconstruction methods.

## 10. Open items for the implementation plan

- Exact clustering method + threshold for the Gauss-sphere seed.
- Half-space intersection library choice (`scipy.spatial`) and interior-point
  seeding; degeneracy handling.
- Acceptance thresholds (inliers, residual, merge angle) — tune on gem04.
- Whether/how to persist `FacetModel` next to the STL, and any GUI surfacing of
  facet count / angles.
