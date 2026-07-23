# Clean-room silhouette → faceted-gemstone bake-off: results + recommendation

Date: 2026-07-22. Branch: `feat/cleanroom-silhouette-facet-bakeoff`.
Spec: `docs/superpowers/specs/2026-07-22-clean-room-silhouette-to-facet-design.md`.
Harness: `scratchpad/cleanroom/bakeoff.py` (+ `render.py`).

## 1. What this was and why

This was a **clean-room re-derivation** of the silhouette → faceted-convex-polytope
reconstruction problem, done deliberately without reusing or extending
`gemscanner/reconstruction/`. The shipped `method="facet"` pipeline (v2.3) is
already merged and user-signed-off on `gem04` (56 planes, watertight, 5 µm
median facet RMS, extents X+16/Y+40/Z+77 µm vs `gem.stl`). The user asked for
an independent investigation anyway: re-derive the problem from first
principles, survey what the literature offers, and empirically bake off the
most promising method families against the same real scan — to learn whether
an independent approach matches, beats, or teaches something the shipped one
does not (notably the residual Z +77 µm gap).

The investigation was run as **survey → down-select → three candidates +
negative control, benchmarked against v2.3** (v2.3 is a benchmark to
match/beat, not one of the three candidates under test). All three
candidates and the control consume only the same clean-room support-function
front-end (`h(θ,z)`, rebuilt independently from the raw silhouettes) and
produce a mesh with no import from `gemscanner/reconstruction/`.

## 2. The survey table (from the design spec)

| # | Family | Core idea | Strike-line-prone? | Fit for this rig |
|---|--------|-----------|:---:|---|
| 1 | Space carving / per-slice visual hull | Intersect back-projected silhouette cones on a voxel/slice grid | **Yes** (each layer independent) | The known failure; keep only as negative control |
| 2 | Support-function half-space fitting | Detect facet directions, fit affine `h(θ,z)=β+αz` per facet, intersect half-spaces | No (planes span all z) | The shipped v2.3; strong fit — the benchmark |
| 3 | Dual-space convex reconstruction | Each tangent plane = a point in polar-dual space; body = polar dual of dual-point hull; merge near-coplanar faces | No (global convex hull) | Elegant, nearly parameter-free, exploits convexity directly |
| 4 | Tangent-plane RANSAC | Every (edge point, local tangent) votes a plane hypothesis; RANSAC/cluster in plane-parameter space | No (planes global) | Robust, standard, assumption-light |
| 5 | EGI / Minkowski (normals + areas) | Cluster tangent normals on the Gauss sphere → facet normals, then solve offsets | No | Clean for convex polytopes; offset solve is fiddly |
| 6 | Parametric cut template | Fit a known brilliant/step-cut model to silhouettes | No | Robust *if* cut known; fails on irregular cuts — too specific |
| 7 | Differentiable silhouette rendering (SDF/mesh + planarity prior) | Optimize a surface so rendered silhouettes match, regularized to planarity | No | Modern but disproportionate to a benchtop tool — future work |

**Down-select rationale.** Families 2/3/4/5 are the strike-line-free,
convexity-exploiting contenders — all fit a model that spans *z*, so none has
a per-row degree of freedom left to strike (see §3). Family 2 is already the
shipped benchmark, so the three clean-room candidates were drawn from
families 3, 4, 5:

- **Cand-A** — Tangent-plane RANSAC (family 4): every silhouette edge point +
  local tangent votes a 3D plane hypothesis; cluster in (normal, offset)
  space; intersect the winning half-spaces.
- **Cand-B** — Dual-space convex reconstruction (family 3): tangent planes →
  dual points → convex hull → dualize back → merge near-coplanar faces.
  Nearly parameter-free; the cleanest expression of "the gem is convex."
- **Cand-C** — EGI / Gauss-sphere clustering (family 5): cluster tangent
  normals on the sphere to get facet *directions* first, then solve each
  offset from its support samples (direction-first vs point/plane-first).

Family 6 (parametric cut template) and Family 7 (differentiable rendering)
were recorded but explicitly out of scope — too cut-specific / disproportionate
to a benchtop tool.

## 3. The root-cause principle for strike-lines (the sorting axis)

A horizontal strike-line is a **z-to-z inconsistency**: consecutive height
rows land at radii that disagree by noise ε because each row was decided from
its own silhouette edges *independently*. Space-carving and per-slice visual
hull do exactly this — every z-layer is an independent 2D decision, so
silhouette edge noise is written straight into a horizontal ridge.

> **Principle that eliminates strike-lines:** never fix a surface point from a
> single row in isolation. Any method that fits a model spanning *z* — an
> affine support piece, a global plane, a parametric cut, an implicit surface
> — averages per-row noise into the fit and has no per-row degree of freedom
> left to strike.

Every family in the survey table is sorted on this one axis, and it is the
whole reason families 2–5 were candidates in the first place while family 1
is kept only as the negative control.

## 4. The bake-off metrics table (harness output on gem04, verbatim)

```
$ .venv/Scripts/python.exe -m scratchpad.cleanroom.bakeoff
building support samples...
support grid: 1944 rows x 180 views (333 rows have any valid data) -- no subsampling applied (see module docstring)
rms_tol_mm = 0.7 for all three candidates (retuned from 0.15; see module docstring)
Cand-A RANSAC: 216 tangent facets, watertight=True, 2.0s -> scratchpad/cleanroom/cand_a_gem04.stl
Cand-B dual: 20 tangent facets, watertight=True, 0.9s -> scratchpad/cleanroom/cand_b_gem04.stl
Cand-C EGI: 84 tangent facets, watertight=True, 9.1s -> scratchpad/cleanroom/cand_c_gem04.stl
CONTROL strip: 116640 faces, watertight=True, 15.3s
BENCH v2.3: 208 faces, watertight=True, 17.5s

wrote scratchpad/cleanroom/bakeoff_gem04.png
total wall-clock: 61.3s
```

| method | facets | watertight | dX (µm) | dY (µm) | dZ (µm) | rmsMed (µm) | strike (µm) | sec |
|---|---:|:--:|---:|---:|---:|---:|---:|---:|
| Cand-A RANSAC | 216 | True | +1532 | +1075 | +159 | 411.5 | 0.0 | 2.0 |
| Cand-B dual | 20 | True | +1845 | +1210 | +151 | 341.1 | 0.0 | 0.9 |
| Cand-C EGI | 84 | True | +645 | +401 | −226 | 353.6 | 0.0 | 9.1 |
| CONTROL strip | 116640 | True | +1 | −1 | −2 | -- | **6.8** | 15.3 |
| BENCH v2.3 | 208 | True | +16 | +40 | +77 | -- | 0.0 | 17.5 |

(`d*` = extents delta vs `scans/gem04/gem.stl`, µm; `strike` = strike-line
high-pass energy, µm; reference `gem.stl`: extents `[8.338, 7.837, 5.501]` mm,
volume 137.18 mm³, watertight, 116640 faces, 58322 vertices.)

Reproduced independently by the reviewer during Task 7 review, byte-for-byte:
strike energy for CONTROL = 6.822677793901232 µm; every candidate/benchmark
strike energy ≈ 5.7e-13 µm (genuinely zero, not a NaN artifact).

## 5. The headline result: the strike metric separates on real data

**Confirmed, and by a wide margin.** CONTROL strip (space-carving,
per-row-independent) scores **6.8 µm** strike energy. Every faceted method —
Cand-A, Cand-B, Cand-C, and BENCH v2.3 — scores **0.0 µm**. This is corroborated
visually in `scratchpad/cleanroom/bakeoff_gem04.png` (panels: `gem.stl`,
Cand-A, Cand-B, Cand-C, CONTROL strip, BENCH v2.3): the CONTROL panel is
densely terraced (visibly rougher/fuzzier, especially on the near-vertical
girdle walls), while Cand-A/B/C and BENCH v2.3 all show clean, flat facets
with sharp edges and no visible striping. The central hypothesis of the whole
investigation — that per-row-independent carving writes noise into
horizontal ridges, and any model spanning z averages it out — **holds** on
real, noisy, full-resolution scan data, exactly as it held on the earlier
synthetic fixtures (`gemscanner-striation-fix` memory).

## 6. The major methodological finding: `gem.stl` is not independent ground truth

**`scans/gem04/gem.stl` is not an independent dimensional reference.**
Controller-verified: it has **116640 faces and 58322 vertices** — identical,
not merely similar, to the CONTROL strip mesh generated fresh in this
investigation (180 views × 324 valid slices × 2 triangles/quad = 116640
faces). `gem.stl` is itself a strip/visual-hull output of the same scan, not
an independent CAD model or caliper/CMM measurement. Its own strike-line
energy is **1.256 µm** — non-zero, and the fine terracing texture is visible
in the leftmost panel of the comparison render.

**Consequence, stated plainly:** every "extents delta vs `gem.stl`" number in
this investigation — and in the shipped v2.3 validation, including its
**±50 µm G3 acceptance gate** — measures agreement with a visual-hull
reconstruction of the same scan, not agreement with the true physical stone.
A candidate or benchmark can score well on this metric purely by resembling
another space-carved reconstruction of identical input data. An independent
physical measurement (CMM, certificate, or hand micrometer on facet
dimensions) would be required for the extents/G3 numbers to mean what they
appear to mean. This applies retroactively to v2.3's own sign-off, not just to
this bake-off. It does not mean the shape/volume comparison is worthless (it
is still a reasonable proxy for gross correctness), but the precision implied
by a ±50 µm gate against this particular reference is not established.

This is arguably the single most valuable output of the whole investigation,
and it was not something either candidate accuracy or the strike metric was
designed to surface — it fell out of simply checking the reference mesh's own
provenance.

## 7. The honest negative results

- **Candidates are 10–100× less dimensionally accurate than v2.3 on real
  data.** v2.3: dX/dY/dZ = +16/+40/+77 µm. Candidates: Cand-A +1532/+1075/+159,
  Cand-B +1845/+1210/+151, Cand-C +645/+401/−226 µm. All three are
  systematically *larger* than `gem.stl` in X/Y, not merely noisier.

- **All three needed `rms_tol_mm` loosened 0.15 → 0.7 uniformly just to
  produce a mesh at all.** At 0.15 (the value tuned on exact, noise-free
  synthetic fixtures) all three fail outright on real gem04 data:
  `planes_to_mesh` raises `ValueError` because the raw half-space hypotheses
  don't bound a closed region (Cand-A: 3 tangent facets survive; Cand-B: 0;
  Cand-C: 1). The same 0.7 mm was applied to all three so the comparison
  stayed apples-to-apples, not tuned per-candidate to flatter it — reported
  even though the resulting facet counts (216/20/84) are wildly different at
  equal tolerance.

- **The girdle prediction held, and generalized.** `gem.stl`'s girdle facets
  are genuinely near-vertical (3538/116640 faces, ~3% of face count and
  surface area, have `|normal_z| < 0.15`). At `rms_tol_mm=0.7`, **all three
  candidates emit zero near-vertical facets** (min `|alpha|`: A=0.383,
  B=0.429, C=0.413) — via two distinct mechanisms: Candidate A *does*
  generate near-vertical raw hypotheses (35 of 1474), but every one has
  `facet_rms` in [1.27, 1.69] mm, well above the 0.7 mm tolerance, so the same
  gate needed to reject garbage also kills genuine thin girdle facets;
  Candidates B and C never propose a near-vertical hypothesis in the first
  place. This was originally flagged (Task 5) as a Candidate-A-specific risk
  from `kink_step_deg=15°`, but it turned out to be a structural blind spot
  shared by all three clean-room methods on real, noisy data near thin
  facet bands.

- **Candidate offset asymmetry — the corrected finding.** Only Candidate A
  (`cand_a_ransac.py:121`) and Candidate B (`cand_b_dual.py:107`) use
  envelope max-snap (`β = max_z(h(θ,z) − αz)`), which is a *guaranteed
  supporting tangent* — the resulting half-space intersection can never carve
  real volume away, only expand outward. Candidate C uses a **median-based**
  offset (`β = median(h − αz)`, `cand_c_egi.py:110`), which is not a
  guaranteed tangent. Correspondingly, Candidate C has the smallest X/Y error
  of the three (+645/+401 µm vs A's +1532/+1075 and B's +1845/+1210), but is
  the *only* candidate with a **negative** dZ (−226 µm) — its median offset
  can and does place a plane inside the true body, carving real volume away,
  something the max-snap methods structurally cannot do. This is a genuine
  accuracy-vs-safety trade-off between the candidates, and the bake-off did
  **not** equalize it — each `reconstruct_*` was called unmodified. A future
  comparison should either equalize the offset estimator across all three or
  report this explicitly, as done here.

- **The plan's own reference algorithms for EGI (Cand-C) and RANSAC (Cand-A)
  were geometrically wrong as originally specified.** Naive per-azimuth
  `dh/dz` tracks the *shared edge* between two facets (the arris), not either
  facet's own normal — the same "facet vs arris" trap the shipped v2.1
  pipeline independently had to solve. Both implementers rediscovered this
  and fixed it independently (Cand-C: local-minima-of-`|dh/dz|` azimuth
  filter; Cand-A: full-azimuth kink mask at facet-spacing step + envelope-snap
  offset instead of least-squares).

- **The controller's original strike metric was itself wrong** on the first
  attempt: a median-filter high-pass false-positived at facet slope-kinks —
  a clean, sloped bipyramid (no striping at all) read ~5 µm. It was replaced
  with a median-of-second-difference (`d2 = r[i-1] - 2r[i] + r[i+1]`,
  aggregated by median absolute value), which reads exactly 0 µm on any
  straight facet, flat or sloped, and only lights up on genuine per-row
  disagreement.

- **Known metric limitation, carried forward:** `median(|d2|)` has a 50%
  breakdown point per azimuth — striping affecting fewer than half an
  azimuth's rows reads as 0. This is valid for this investigation (the strip
  control strikes pervasively, on nearly every row) but is **not** a valid
  detector for localized or partial striping.

- **Candidates A and C are not fully independent methods.** Both share the
  "kink"/local-minimum-of-slope azimuth-selection principle and the same
  `rms_tol_mm` gate value. The bake-off should be read as two genuinely
  distinct approaches (B: primal convex-hull geometry, no differentiation;
  A/C: numerical differentiation of the support grid with slightly different
  clustering) plus a shared-lineage variant, not three independent methods.

## 8. Per-candidate verdict and recommendation

| candidate | watertight | strike-free (metric+visual) | extents vs v2.3 | girdle facets | independence | notes |
|---|:--:|:--:|---|:--:|---|---|
| Cand-A RANSAC | Yes | Yes (0.0 µm, clean render) | 10–100× worse | None (gate kills near-vertical hyps) | shares kink+tol with C | most facets (216), slowest to tune-fail, safest offset (max-snap) |
| Cand-B dual | Yes | Yes (0.0 µm, clean render) | 10–100× worse (worst of the three) | None (never generated) | genuinely distinct | fewest facets (20), fastest (0.9s), cleanest/most parameter-free method, safest offset (max-snap) |
| Cand-C EGI | Yes | Yes (0.0 µm, clean render) | 10–100× worse (best of the three) | None (never generated) | shares kink+tol with A | slowest (9.1s), best X/Y accuracy but only candidate that can carve inward (median offset) |

**Recommendation: v2.3 remains the production method.** No candidate beats it
on dimensional accuracy, and none closes the residual Z +77 µm gap that
motivated the investigation — if anything, all three are 10–100× further
from `gem.stl` than v2.3 already is. This is reported plainly, not softened:
the investigation's value here is the comparison itself, not a forced win.
Nothing from Candidates A, B, or C should be ported into
`gemscanner/reconstruction/` as a replacement algorithm.

What the clean-room investigation *did* produce that is worth keeping:

- **(a) The strike-line metric as a reusable objective regression gate.**
  `strike_metric.strike_energy` (median-of-second-difference along z,
  per-azimuth) cleanly separates striped from clean meshes on real data (6.8
  µm vs 0.0 µm) and is cheap to compute. This is worth porting into the
  shipped pipeline's own test/validation suite as an automated regression
  check against re-introducing strike-lines — subject to its known 50%
  breakdown-point limitation (§7).
- **(b) The envelope-snap tangency property as a principled offset
  estimator**, worth keeping in mind for any future offset-fitting work: `β =
  max_z(h(θ,z) − αz)` is provably a supporting half-space (never carves real
  volume, only ever expands outward), a useful safety property distinct from
  a least-squares or median fit that can bias either direction. This is an
  idea worth remembering, not code to port — v2.3 already uses an exact
  frozen refit (`fit_affine_support`→`plane_from_affine`) suited to its own
  segmentation, and swapping in envelope-snap was not tested against v2.3's
  architecture here.
- **(c) The `gem.stl`-is-not-ground-truth finding (§6)**, which is arguably
  the most valuable output of this entire investigation, independent of any
  candidate's performance. It should inform how the ±50 µm G3 gate and any
  future extents-based acceptance criteria are described and trusted, and
  motivates seeking an independent physical reference for gem04 (or any
  future stone) before treating extents-vs-`gem.stl` as an accuracy claim
  rather than a self-consistency check.
- **(d) The girdle-facet blind spot as a known limitation to test for.** Any
  future faceted-reconstruction method (clean-room or production) should be
  explicitly checked for near-vertical/thin-facet recovery on real noisy
  data — this bake-off shows it is easy for a method to look correct on
  synthetic fixtures and still silently drop the entire girdle band on a
  real scan, by more than one mechanism.

None of the three candidate implementations, their tuned tolerances, or their
offset estimators should be ported into `gemscanner/reconstruction/` as-is;
they remain clean-room reference prototypes in `scratchpad/cleanroom/`.

## 9. Reproduction

```bash
.venv/Scripts/python.exe -m scratchpad.cleanroom.bakeoff
.venv/Scripts/python.exe -m pytest scratchpad/cleanroom/ -v   # 15 passed
```

Harness code: `scratchpad/cleanroom/support_samples.py`, `polytope.py`,
`strike_metric.py`, `cand_a_ransac.py`, `cand_b_dual.py`, `cand_c_egi.py`,
`bakeoff.py`, `render.py`. Comparison render:
`scratchpad/cleanroom/bakeoff_gem04.png`. Full per-task detail:
`.superpowers/sdd/task-{1..7}-report.md`; controller ledger:
`.superpowers/sdd/progress.md`.
