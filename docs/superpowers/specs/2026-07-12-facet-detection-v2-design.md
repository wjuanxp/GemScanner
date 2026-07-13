# Facet Detection v2 — segment-and-cluster on raw support data

**Date:** 2026-07-12
**Status:** Design approved (conversation), supersedes the *detection front-end* of
`2026-07-11-faceted-gem-reconstruction-design.md`. The exact-refit and
half-space-assembly back-end of that design is retained unchanged.

---

## 1. Why v1 detection failed (root cause, verified on gem04)

v1 seeded facet candidates by Gauss-sphere clustering of the **soft-hull**
mesh's face normals. On synthetic ground truth this worked (the hull of an
already-perfect polyhedron keeps sharp faces). On the real gem04 it failed
completely — visual comparison shows the output does not represent the actual
facets:

- The soft hull is smooth **by construction**; its normals are a coarse angular
  sampling of a rounded surface, not real facets. Evidence: the girdle ring
  collapsed to **1** normal cluster (53 seeds total, none girdle-vertical).
- Scans are captured **culet-up** (table down). v1 unconditionally capped both
  z-extremes with horizontal planes → a flat lid over the culet *point*.
- Net result: a crude convex envelope (+5–6 % oversize), wrong facet layout,
  blunted apex. Numbers (watertight, 32.8 µm median fit) looked plausible while
  the geometry was wrong — **numerical validation without visual verification
  against the real stone was the process failure.**

Root causes: (A) culet cap — a bug; (B) soft-hull seed — architectural: it
destroys the facet information before detection starts.

## 2. Spike result that validates v2 (gem04, real data)

Segmenting the **raw** support function `H(z)` per view into affine pieces
(after a k≈9 median along z) recovers the step-cut structure directly:

- ~17–20 affine segments per principal azimuth, typical **rms ≈ 5 µm**
  (v1: 32.8 µm median / 165 µm max).
- Clean tilt ladder from table to culet: ≈27° → 39° → 45° → 51° → 60°
  (pavilion steps), plus crown ≈ −55° tiers below the girdle — unmistakably the
  real step cut.
- Girdle cross-section (strip slices, sharp) shows ~4 principal sides at
  ≈74°/162°/252°/342°.
- Dropping the culet cap: assembly stays watertight and converges to a single
  apex vertex; extents move toward gem.stl (8.88 → 8.61 mm X).

The facet information is present and sharp in the raw data; only the soft-hull
front-end was discarding it.

## 3. Scope

- Cuts: **step cuts and brilliant cuts** (general convex faceted stones); no
  cut template, unsupervised.
- Orientation: capture protocol is **culet-up (table down)**; v2 detects
  orientation from the silhouette width profile rather than assuming it.
- Validation: **gem04 (real step cut) is the acceptance bar**, including a
  visual facet-layout comparison. Brilliant validation deferred until a real
  brilliant scan exists. Synthetic toy-gem e2e remains as a regression test —
  explicitly necessary-not-sufficient.

## 4. Pipeline (replaces v1 stages 2–3; everything else retained)

`method="facet"` in `FacetReconstructor.reconstruct`:

1. **Support maps** — existing `support_maps(dataset, params)`. Unchanged.
2. **Per-view affine segmentation** (new, productionized spike):
   for each view `i`, estimate the local slope `dH/dz` by sliding-window
   Theil–Sen (window `facet_seg_median_rows`, default 17 — rank-robust, no
   pre-filtering: a blanket median staircases sloped columns), split into
   segments at run-maxima of the two-sided slope jump above `facet_slope_jump`
   (default 0.12), trim the k-row transition zone, and fit each segment with
   the frozen robust `fit_affine_support`, with minimum segment span
   `facet_min_seg_mm` (default 0.25 mm) and ≥ `facet_min_inliers` rows. Per
   segment record `(i, z_lo, z_hi, α, β, rms)`. (Revised from the original
   slope-derivative criterion, which was numerically verified noise-fragile.)
3. **Facet azimuths from cross-slice polygon edges** (new — AMENDED 2026-07-12,
   user-approved): the strip cross-section polygons' edges ARE the facet traces.
   Cluster all slice-polygon edges (outward-normal azimuth, length-weighted)
   across z into azimuth families; edges shorter than `facet_min_edge_mm`
   (default 0.35 mm, above the carve quantum R·Δθ) are noise from view
   quantization at polygon corners and are skipped. Each family = one facet
   azimuth θ\* (length-weighted circular mean; 0.2° accuracy on the toy gate).
   *The spec's original cross-view chain clustering was pre-verified to FAIL
   the toy gate (2.5° median): chains conflate facet traces with polygon-corner
   (arris) traces — crown chains center on vertex directions. `cluster_segments`
   remains in the module (tested) but is not used by the facet path.*
4. **Per-azimuth tier segmentation + exact refit** — at each family's nearest
   view, `segment_support` splits the raw `H(z)` into affine tiers
   (`facet_seg_median_rows` default 17: at 1-px support quantization the
   Theil–Sen slope noise is ≈ pixel/(2k·Δz); k=8 keeps it under half the
   0.12 jump threshold — verified on the toy gate and gem04); each tier is
   refit by the frozen `fit_affine_support` → `plane_from_affine` → exact
   plane `(a,b,c,d)`. Girdle facets are the α≈0 tiers; no special case.
   Note: tiers narrower than ~(2k+8) rows are absorbed into neighbours — on
   gem04 the absorbed spans still fit ONE plane at ≤8 µm rms (they were
   over-segmentation in the spike, not real distinct tiers).
5. **Table/culet, orientation-aware** (new):
   - Orientation from the silhouette width profile: the z-extreme whose
     silhouette is wide + flat (width > `facet_table_width_frac` (default 0.3)
     of the girdle width over a plateau) is the **table** → emit horizontal
     plane there. The converging extreme is the **culet** → **no cap**; the
     pavilion planes close the apex.
   - If neither extreme qualifies as a table (unusual), emit no extremal
     planes; if assembly then fails to bound, the existing fallback fires.
6. **Assembly** — existing `_merge_planes` (scale-relative) →
   `planes_to_polytope` → watertight mesh, `metadata["facets"]` =
   {planes, rms, vertices, edges}. Unchanged.

**Removed from the facet path:** SoftHullReconstructor seeding, `seed_facets`
usage, `annotate_seed_z_extent`. (`seed_facets` stays in the module — harmless,
tested — but the facet path no longer calls it. soft_hull remains a standalone
method and the fallback target.)

## 5. Params (replace v1 facet knobs where noted)

```
facet_seg_median_rows: int = 17     # Theil-Sen slope window (rows)
facet_slope_jump: float = 0.12      # min two-sided slope jump between tiers
facet_min_seg_mm: float = 0.25      # min tier z-span
facet_min_edge_mm: float = 0.35     # min slice-polygon edge (carve-quantum filter)
facet_table_width_frac: float = 0.3 # table plateau width vs girdle width
facet_min_inliers: int = 8          # min rows per tier / refit inliers
# retained: facet_merge_deg, facet_fallback
# dropped: facet_view_search, facet_axial_cos (v1-seed), facet_min_views,
#          facet_slope_tol (chain clustering, superseded by edge azimuths)
```

## 6. Acceptance criteria (gates, in order)

1. **Toy-gem synthetic e2e** still passes (median normal error <1°, watertight,
   volume <5%) — regression only.
2. **gem04 quantitative**: per-facet refit rms at spike levels (median ≤15 µm);
   tilt tiers match the spike ladder (≈27/39/45/51/60° pavilion, ≈−55° crown);
   extents within ~50 µm of gem.stl per axis; watertight; single-vertex apex at
   the culet end (no horizontal cap plane with normal toward the culet).
3. **gem04 visual (the gate v1 skipped)**: side-by-side render of
   `gem_facet.stl` vs `gem.stl`; the facet layout (tier boundaries, side
   azimuths) must visibly match the real stone. Deliver the rendered image for
   the user's judgement — user sign-off required before merge.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Cross-view clustering splits/merges facets | gem04 segments are extremely clean (5 µm); spike output is the debugging reference; `facet_min_views`/`facet_slope_tol` tunable |
| Segment breakpoints drift with noise | median-along-z pre-filter (rank-based, facet-preserving — same property as the shipped de-terracing) |
| Brilliant cuts untested | explicitly deferred; design has no step-cut-specific assumption (clustering is generic) |
| holder_mask_rows still not in manifest | unchanged known product gap (F1); validation script supplies 705 |

## 8. Non-goals

- No brilliant-cut validation in this iteration (deferred; no real scan).
- No multi-axis capture, no concave facets, no cut identification.
- No change to strip/soft_hull methods, GUI wiring, or fallback semantics.
