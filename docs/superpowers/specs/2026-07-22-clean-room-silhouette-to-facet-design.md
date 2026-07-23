# Clean-room silhouette → faceted-gemstone investigation

Date: 2026-07-22. Scope: a fresh, independent investigation of the
silhouette → faceted-convex-polytope reconstruction problem, run as a
survey-then-bake-off on the gem04 real scan. This is deliberately a
clean-room exercise: the shipped `method="facet"` (v2.3) pipeline is set
aside as a **benchmark to match/beat**, not reused or extended.

## Why this exists

The shipped v2.3 facet pipeline is already merged, signed off on gem04
(56 planes, watertight, 5 µm median facet RMS, extents X+16 / Y+40 / Z+77 µm
vs `gem.stl`) and is structurally free of horizontal strike-lines. The user
asked for a **clean-room investigation** anyway: re-derive the problem from
first principles, survey the method families the literature offers, and
empirically bake off the most promising ones on the real gem04 frames — to
learn whether an independent approach matches, beats, or teaches us something
the shipped one does not (notably the residual Z +77 µm extent gap).

## The data (gem04)

- 180 backlit silhouettes, 2° turntable steps, full 360°.
- **Orthographic** projection (confirmed: `coords.column_to_projection` is a
  pure linear `mm_per_px` scale, no perspective divide). This is the linchpin
  assumption for the entire support-function / dual-convex framework.
- Known calibration: `mm_per_px`, per-row `axis_column` (+ small `axis_tilt`),
  per-frame angle. `holder_mask_rows = 705` masks the pedestal post (rig
  calibration for this mount; not carried in the manifest — supplied
  explicitly, as in `scripts/validate_facet_gem04.py`).
- Reference: `scans/gem04/gem.stl` (dimensional ground truth).

## The target and the key representation

A cut gem is, to excellent approximation, a **convex polytope** — an
intersection of a few dozen half-spaces (table, crown mains/stars, girdle
facets, pavilion mains, culet). By Minkowski's theorem a convex body is
uniquely determined by its **support function**; a *faceted* convex body has a
**piecewise-affine** support function, each facet being one linear piece.

Under orthographic projection, each silhouette's left/right edge at image row
*v* (→ height *z*) and view angle *θ* is a true **support value** of the
height-*z* cross-section:

```
h(θ, z) = max_{(x,y) ∈ slice(z)} ( x·cosθ − y·sinθ )
```

Stacked over all θ and z, `h(θ, z)` is the shared clean-room input
representation all candidates consume. (This mirrors the shipped
`SupportMaps.h_right/h_left`, but is rebuilt independently in the harness so
the investigation stays clean-room from the silhouettes up.)

## Root cause of horizontal strike-lines (the sorting axis)

A horizontal strike-line is a **z-to-z inconsistency**: consecutive height
rows land at radii that disagree by noise ε because each row was decided from
its own silhouette edges *independently*. Space-carving and per-slice visual
hull do exactly this — every z-layer is an independent 2D decision, so
silhouette edge noise is written straight into a horizontal ridge.

> **Principle that eliminates strike-lines:** never fix a surface point from a
> single row in isolation. Any method that fits a model spanning *z* — an
> affine support piece, a global plane, a parametric cut, an implicit surface —
> averages per-row noise into the fit and has no per-row degree of freedom
> left to strike. Every family below is sorted on this one axis.

## Survey of method families

| # | Family | Core idea | Strike-line-prone? | Fit for this rig |
|---|--------|-----------|:---:|---|
| 1 | Space carving / per-slice visual hull | Intersect back-projected silhouette cones on a voxel/slice grid | **Yes** (each layer independent) | The known failure; keep only as negative control |
| 2 | Support-function half-space fitting | Detect facet directions, fit affine `h(θ,z)=β+αz` per facet, intersect half-spaces | No (planes span all z) | The shipped v2.3; strong fit — the benchmark |
| 3 | Dual-space convex reconstruction | Each tangent plane = a point in polar-dual space; body = polar dual of dual-point hull; merge near-coplanar faces | No (global convex hull) | Elegant, nearly parameter-free, exploits convexity directly |
| 4 | Tangent-plane RANSAC | Every (edge point, local tangent) votes a plane hypothesis; RANSAC/cluster in plane-parameter space | No (planes global) | Robust, standard, assumption-light |
| 5 | EGI / Minkowski (normals + areas) | Cluster tangent normals on the Gauss sphere → facet normals, then solve offsets | No | Clean for convex polytopes; offset solve is fiddly |
| 6 | Parametric cut template | Fit a known brilliant/step-cut model to silhouettes | No | Robust *if* cut known; fails on irregular cuts — too specific |
| 7 | Differentiable silhouette rendering (SDF/mesh + planarity prior) | Optimize a surface so rendered silhouettes match, regularized to planarity | No | Modern but disproportionate to a benchtop tool — future work |

Families 2/3/4/5 are the strike-line-free, convexity-exploiting contenders.
Family 1 is the negative control. Families 6 and 7 are out of scope (too
cut-specific / disproportionate) but recorded for completeness.

## The three candidates (bake-off set)

All three consume the same clean-room `h(θ, z)` support samples and produce a
mesh independently; none imports `gemscanner/reconstruction/`.

- **Cand-A — Tangent-plane RANSAC (family 4).** Each silhouette edge point +
  local tangent → a candidate 3D plane; RANSAC / cluster in (normal, offset)
  space; intersect the winning half-spaces into a polytope. Most general,
  outlier-robust, assumption-light.
- **Cand-B — Dual-space convex reconstruction (family 3).** Convert all
  tangent planes to dual points, take their convex hull, dualize back to the
  polytope, merge near-coplanar faces into facets. Nearly parameter-free; the
  cleanest expression of "the gem is convex."
- **Cand-C — EGI / Gauss-sphere clustering (family 5).** Cluster tangent
  normals on the sphere to get facet *directions* first, then solve each
  offset from its support samples. Tests whether direction-first beats
  point/plane-first.

**Negative control:** space-carving on the same data, to reproduce
strike-lines and confirm A/B/C are free of them in the side-by-side render.

**Benchmark (not a candidate):** the shipped v2.3 facet output
(56 planes; X+16 / Y+40 / Z+77 µm; 5 µm RMS) — the bar to match/beat.

## Shared harness & success criteria

One harness loads gem04 (`holder_mask_rows=705`), builds the clean-room
`h(θ, z)`, and runs each candidate + control + the v2.3 benchmark, reporting
per method:

- **Numeric gates** (reuse `validate_facet_gem04.py`'s structure): facet
  count, watertight, extents vs `gem.stl` (µm/axis), volume delta, per-facet
  RMS median/max.
- **Strike-line metric (new, objective):** high-pass energy of the final
  surface radius along z at fixed azimuth (row-to-row radius variance after
  removing the facet's affine trend). Space-carving scores high; A/B/C should
  be near zero. This makes "strike-line-free" measurable, not just visual.
- **Visual gate (mandatory, per project memory):** render all methods +
  `gem.stl` side-by-side into one comparison image for user sign-off.

**Success** = a candidate that is (a) watertight, (b) objectively and visually
strike-line-free, (c) within a small factor of v2.3 on extents/RMS, and
ideally teaches something new (e.g. Cand-B closing the Z +77 µm gap, or
reaching parity with far fewer tuned parameters).

## Deliverables

1. This design doc (committed).
2. A results note under `docs/superpowers/notes/` — survey + bake-off table +
   verdict + recommendation.
3. Prototype code under `scratchpad/` only (clean-room; does **not** touch
   `gemscanner/reconstruction/`), plus one side-by-side comparison render.
4. A recommendation: adopt-as-is / port one idea into the shipped pipeline /
   v2.3 remains best.

## Explicit non-goals

- No changes to `gemscanner/reconstruction/` in this investigation (any
  adoption is a separate, later task gated on the recommendation).
- Not solving perspective/telecentric calibration — orthographic is given.
- Not the parametric-template or differentiable-rendering families (recorded,
  deferred).
- gem04 is the single test subject; broader multi-scan validation is future
  work (consistent with the v2.3 sign-off caveat).
