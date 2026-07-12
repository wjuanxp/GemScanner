# Task 9: facet method validation on real gem04 scan

Date: 2026-07-11 (research/run date; see repo log for actual commit date)

## Verdict (one line)

Facet recovery **succeeded** (no fallback to soft_hull) on the real gem04 scan
and produced a watertight 43-facet polyhedron whose median per-facet fit
residual (32.8 µm) beats the 68 µm terracing baseline, **but** it is only
dimensionally faithful to `gem.stl` to within a few **hundred** µm (X +538 µm
/ +6.4%, Y +430 µm / +5.5%, Z +150 µm / +2.7%), not the "few tens of µm"
the design hoped for — and roughly a quarter of individual facets (11/41) have
fit residuals above the 68 µm baseline, so the result is real but imperfect.

## Critical pre-condition found: `holder_mask_rows` must be set

The very first run (script with `ReconstructionParams(method="facet")` and no
`holder_mask_rows`, i.e. default 0) "succeeded" mechanically — no
`RuntimeWarning`, `mesh.metadata["facets"]` populated — but the result was
garbage: only **10 facets**, extents **52.29 x 46.96 x 12.06 mm** vs
`gem.stl`'s **8.34 x 7.84 x 5.50 mm** (~5-6x too large). Root cause: gem04's
raw silhouette includes the pedestal post and stage below the gem (per
`[[gemscanner-bench-calibration]]`, "without it axis fit / FoV / reconstruction
all break"); `holder_mask_rows` defaults to 0 in `ReconstructionParams` and is
not stored in `scans/gem04/manifest.json`, so it must be supplied explicitly
by the caller. This is **not a facet-fit bug** — the same pedestal-inclusive
blow-up reproduces identically with plain `method="strip"` and `method=
"soft_hull"` on the same dataset (41.25 x 41.25 x 17.50 mm for both, matching
each other almost exactly, confirming the issue is upstream of facet-specific
code).

Fix: swept `holder_mask_rows` against `gem.stl`'s known extents using
`method="strip"` (fast) and found **705** reproduces gem.stl's X/Y/Z bounds to
within a few µm (X: 8.3387 vs 8.3381 mm, Y: 7.8361 vs 7.8366 mm, Z bounds
[-5.234..0.962] at hmr=705 give z_min -4.536 vs gem.stl's -4.538 mm). 705 is
exactly the value already documented in `config.example.yaml` ("2026-07-03
gem2 in focus... holder_mask_rows: 705") — so gem04 was evidently scanned
under the same rig/mount calibration as that config comment, it just isn't
recorded in the scan's own manifest. `scripts/validate_facet_gem04.py` now
hardcodes `HOLDER_MASK_ROWS = 705` with a comment explaining why, since the
manifest can't supply it. **This is a real gap**: any dataset lacking a
recorded holder_mask_rows silently reconstructs the pedestal along with the
gem, and nothing currently detects or warns about it.

## Actual script output (after the holder_mask_rows fix)

```
facets=43  vertices(meet-points)=80  edges=234
watertight=True  volume=142.34 mm^3
extents (mm): 8.876 x 8.267 x 5.651
worst on-facet planarity residual: 17.4 um
reference gem.stl extents (mm): [8.33805108 7.83664012 5.50051087]
wrote scans/gem04/gem_facet.stl
```

No `RuntimeWarning` was emitted (facet recovery did not fall back to
soft_hull).

### Caveat on the "planarity residual" metric in the script

The brief's script measures the max distance from mesh *vertices* to each
facet plane (over vertices within 0.02 mm of that plane). For a mesh built by
`HalfspaceIntersection`, every hull vertex sits *exactly* on the ≥3 planes
that define it by construction, so this number (17.4 µm here) mostly reflects
solver/geometric tolerance, not how well a plane fits the real measured
data. The honest per-facet quality number is the affine-fit RMS residual
computed in `recover_planes()` against the raw support-map samples *before*
half-space assembly — obtained by adding debug prints and calling
`seed_facets`/`recover_planes` directly:

- 41 tangent-facet fits (2 more planes are the extremal table/culet, fit
  exactly by definition, rms=0): **median 32.8 µm, mean 49.6 µm, min 4.7 µm,
  max 165.8 µm**.
- 30/41 facets (73%) are below the 68 µm terracing baseline; **11/41 (27%)
  exceed it**, up to 165.8 µm — a real limitation, not universal success.
- Raw Gauss-normal clustering (`seed_facets` before merge/axial-skip)
  returned **53 clusters** on the soft_hull seed mesh; 1 was the near-vertical
  table (routed to the extremal branch), 52 were tangent candidates, and
  **all 52 fit successfully** on the first try (`di=0`, nearest-azimuth view)
  — `facet_min_inliers` and `facet_view_search` never had to fall back to a
  neighboring view or reject a fit for insufficient inliers on this dataset.
  After merge (6°), 41 tangent + 2 extremal = 43 final planes.

## Threshold tuning tried

Reused the same (expensive, ~ minutes) soft_hull seed mesh across all
configs and only re-ran `seed_facets`/`recover_planes`/`planes_to_polytope`
(cheap) for each:

| facet_merge_deg | facet_min_inliers | facet_view_search | n_planes | extents (mm) | rms median / max (µm) | facets over 68µm |
|---|---|---|---|---|---|---|
| 6 (default) | 12 | 4 | 43 | 8.876 x 8.267 x 5.651 | 32.8 / 165.8 | 11/41 |
| 4 | 12 | 4 | 36 | 9.278 x 8.595 x 5.651 | 25.0 / 174.3 | 8/34 |
| 10 | 12 | 4 | 31 | 8.794 x 8.086 x 5.651 | 40.9 / 206.7 | 10/29 |
| 6 | 8 | 4 | 43 | (identical to default) | 32.8 / 165.8 | 11/41 |
| 6 | 20 | 4 | 43 | (identical to default) | 32.8 / 165.8 | 11/41 |
| 6 | 12 | 3 | 43 | (identical to default) | 32.8 / 165.8 | 11/41 |
| 6 | 12 | 6 | 43 | (identical to default) | 32.8 / 165.8 | 11/41 |

Findings:
- `facet_min_inliers` (8/12/20) and `facet_view_search` (3/4/6) have **zero**
  effect on gem04 in the tested ranges — every seed's nearest-azimuth view
  (`di=0`) already had 25-238 inliers, far above even the 20-inlier floor, so
  neither threshold is a binding constraint on this dataset.
- `facet_merge_deg` is the only lever that matters, and it's a genuine
  trade-off, not a free win: looser merging (4°) keeps more, better-individually-fit
  facets (median rms drops to 25.0 µm) but pushes the overall bounding box
  further from `gem.stl` (+940 µm in X). Tighter merging (10°) pulls the
  bounding box closer to `gem.stl` in X/Y (+456 µm / +249 µm, better than
  default) but degrades individual fit quality (median 40.9 µm, max 206.7 µm,
  evidence that some genuinely distinct facets are being merged together).
  No single value in the tested 4-10° range cleanly wins on both axes, so the
  shipped script keeps the pipeline default (6°) rather than picking a value
  post-hoc to make one number look best.
- Z extent (5.651 mm across every config) is set entirely by the two
  extremal table/culet planes, which don't participate in merging, so no
  merge_deg value changes it. Its +150 µm offset from gem.stl (5.501 mm) is a
  separate question from facet clustering — the extremal branch uses the
  bare max/min of `sm.z` over any valid view, which folds in a few extra rows
  of noise/valid-mask slop at the sample extremes; not investigated further
  here (out of scope for "modest tuning of the facet-clustering thresholds").

## Failure modes / limitations found

1. **No manifest-carried `holder_mask_rows`.** gem04's manifest doesn't store
   the pedestal-mask row count used at capture time; a caller must know/guess
   it (here, recovered by sweeping against `gem.stl`). Any future dataset
   missing this value will silently reconstruct pedestal + gem as one blob
   under every method (`strip`, `soft_hull`, `facet` alike) with no error or
   warning — a real gap worth a follow-up (e.g. persist it in the manifest at
   capture time, or add a sanity check comparing silhouette top/bottom widths).
2. **Facet count is plausible but unverified against ground truth.** 43
   facets is a plausible count for a moderately complex cut, but we have no
   independent facet-count ground truth for the physical gem04 stone (unlike
   the synthetic polyhedron test), so "plausible" is as far as this validation
   can honestly go.
3. **~27% of recovered facets have fit residual above the terracing
   baseline** (up to 165.8 µm on the worst outlier), meaning some real
   facets are recovered less well than others — likely narrower/steeper
   facets with fewer usable support-map rows (`n_inliers` as low as 25-50 vs
   ~150-240 for larger facets).
4. **Dimensional fidelity is good but not tight**: +5-6% in X/Y, +2.7% in Z,
   +3.8% in volume vs `gem.stl` — real and repeatable across every merge_deg
   tested, not fixable by the tuning knobs available in this task's scope.
5. **The brief's planarity-residual metric is close to tautological** for a
   half-space-intersection mesh (see caveat above); the meaningful per-facet
   quality signal is the pre-assembly affine-fit RMS, not post-hoc
   vertex-to-plane distance on the final polytope.

## Files

- `scripts/validate_facet_gem04.py` — validation script (hardcodes
  `HOLDER_MASK_ROWS = 705`, required since the manifest doesn't carry it).
- `scans/gem04/gem_facet.stl` — the reconstructed facet mesh from the final
  run (written by the script; not committed to git as source, just a repo
  artifact left in place per the script's own behavior).
- This note.
