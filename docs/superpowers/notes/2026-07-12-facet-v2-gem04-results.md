# V2 Task 5: gem04 real-scan validation of the v2.1 faceted reconstruction

Date: 2026-07-12. Branch: `feat/faceted-gem-reconstruction`. Script:
`scripts/validate_facet_gem04.py` (`ReconstructionParams(method="facet",
holder_mask_rows=705)`; `HOLDER_MASK_ROWS = 705` is the rig calibration for
gem04, unrelated to facet detection — see the 2026-07-11 note / memory for how
it was recovered, the manifest still doesn't carry it).

gem04 is scanned **culet-up** (pointed top, flat table at the bottom) and is
not a perfect step cut.

## Verdict (one line)

**5 of 6 gates PASS.** Facet recovery is fast, does not fall back, is
watertight, has excellent per-facet fit quality (median 5.0 µm, well under
the 15 µm gate), and correctly places exactly one table cap with **no culet
cap** (the v1 "flat lid over the culet" bug is gone). The one failing gate is
dimensional fidelity to `gem.stl`: the bounding box is **80–330 µm** off per
axis depending on tuning, which is **1.6×–6.6× over** the ~50 µm/axis gate.
Modest tuning within the brief's specified ranges narrows X from 332 µm to
80 µm but cannot bring all three axes under 50 µm simultaneously, and no
combination tried passes G3. This is reported as a real, unresolved gap, not
papered over.

## Baseline run (default params: `facet_seg_median_rows=17`,
`facet_slope_jump=0.12`, `facet_min_edge_mm=0.35`)

Full captured stdout:

```
facets=41  tangent=40  extremal=1  vertices(meet-points)=78  edges=228
watertight=True  volume=140.14 mm^3
extents (mm): 8.6700 x 7.9967 x 5.5788
reference gem.stl extents (mm): 8.3381 x 7.8366 x 5.5005
extent delta vs gem.stl (um): X=+331.9  Y=+160.1  Z=+78.3
volume delta vs gem.stl: +2.964 mm^3 (+2.16%)
tangent-facet rms (um): median=5.0  max=14.5  min=3.5  n=40
tilt ladder (deg, tangent facets, sorted) with per-facet rms (um):
   -59.19 deg   rms=   6.0 um
   -58.66 deg   rms=   5.1 um
   -57.92 deg   rms=   5.8 um
   -57.84 deg   rms=   5.1 um
   -57.29 deg   rms=   4.9 um
   -57.06 deg   rms=   5.0 um
   -56.49 deg   rms=   4.9 um
   -56.03 deg   rms=   4.8 um
   -54.24 deg   rms=   4.8 um
   +19.95 deg   rms=  14.5 um
   +23.08 deg   rms=   8.0 um
   +23.44 deg   rms=   9.7 um
   +23.88 deg   rms=  12.5 um
   +24.16 deg   rms=   5.3 um
   +24.55 deg   rms=  10.8 um
   +24.93 deg   rms=   4.8 um
   +25.56 deg   rms=   8.8 um
   +25.59 deg   rms=   9.8 um
   +26.03 deg   rms=   4.8 um
   +34.66 deg   rms=   4.9 um
   +37.94 deg   rms=   4.9 um
   +38.19 deg   rms=   4.9 um
   +38.77 deg   rms=   5.2 um
   +39.61 deg   rms=   5.0 um
   +39.64 deg   rms=   5.0 um
   +40.28 deg   rms=   4.8 um
   +40.62 deg   rms=   5.0 um
   +43.55 deg   rms=   4.8 um
   +43.57 deg   rms=   4.7 um
   +44.09 deg   rms=   4.7 um
   +44.99 deg   rms=   5.5 um
   +45.19 deg   rms=   3.5 um
   +46.39 deg   rms=   5.9 um
   +46.93 deg   rms=   4.6 um
   +47.52 deg   rms=   4.9 um
   +49.55 deg   rms=   5.1 um
   +49.94 deg   rms=   5.6 um
   +50.54 deg   rms=   5.3 um
   +53.02 deg   rms=   5.3 um
   +53.47 deg   rms=   4.9 um
extremal planes (source: table/culet caps):
  plane=(+0.0000,+0.0000,-1.0000,+4.5363)  tilt=-90.00 deg  -> BOTTOM/TABLE CAP (c<0)

=== GATE VERDICTS ===
[PASS] G1 no fallback RuntimeWarning (0 fallback warning(s))
[PASS] G2 tangent rms median <= 15.0 um (got 5.0 um)
[FAIL] G3 extents within 50.0 um/axis of gem.stl (worst axis delta 331.9 um)
[PASS] G4 watertight (got True)
[PASS] G5 no culet cap (extremal plane with c>0) (culet_cap_present=False)
[PASS] G6 exactly one table cap (c<0 extremal plane) (got 1)

ALL GATES: FAIL
wrote scans/gem04/gem_facet.stl
```

Wall-clock: the whole reconstruction (support maps + slicing + facet
recovery + half-space assembly) completed in well under a minute, confirming
the brief's "tens of seconds, no soft-hull seed" expectation for v2.1.

## Gate-by-gate

| Gate | Requirement | Result | Verdict |
|---|---|---|---|
| G1 | No fallback `RuntimeWarning` | 0 fallback warnings | **PASS** |
| G2 | Tangent-facet rms median ≤ 15 µm | 5.0 µm (max 14.5 µm, min 3.5 µm, n=40) | **PASS** |
| G3 | Extents within ~50 µm/axis of `gem.stl` | X +331.9, Y +160.1, Z +78.3 µm | **FAIL** |
| G4 | Watertight | `True` | **PASS** |
| G5 | No culet cap (no extremal plane with c>0) | none present | **PASS** |
| G6 | Exactly one table cap (c<0 extremal plane) | 1 (at z=−4.536 mm) | **PASS** |

## Tilt ladder vs the az-74 reference

Reference (one side of the stone, pre-verified): pavilion tiers ≈
+27/+39/+45/+50°, crown ≈ −58°, per-tier rms 4.7–8.0 µm.

Full-stone structure recovered here groups into the same tier bands, each
containing several distinct facets (expected for a multi-facet step cut —
main + star/upper-girdle facets at nearby but not identical angles around
the stone), not a flat single plane per tier:

| Band | Reference | Recovered range | n facets | rms range (µm) |
|---|---|---|---|---|
| Crown | ≈ −58° | −59.19° … −54.24° | 9 | 4.8 – 6.0 |
| Pavilion tier 1 | ≈ +27° | +19.95° … +26.03° | 10 | 4.8 – 14.5 |
| Pavilion tier 2 | ≈ +39° | +34.66° … +40.62° | 8 | 4.8 – 5.2 |
| Pavilion tier 3 | ≈ +45° | +43.55° … +47.52° | 9 | 3.5 – 5.9 |
| Pavilion tier 4 | ≈ +50° | +49.55° … +53.47° | 4 | 4.9 – 5.6 |

The four-tier pavilion + single-band crown structure matches the az-74
reference qualitatively and the per-facet rms values (mostly 4.7–8 µm,
median 5.0 µm) match the reference's 4.7–8.0 µm range closely. The lowest
tier (~+20–26° vs reference +27°) is systematically ~1–5° shallower and has
the two worst-fit facets in the whole mesh (14.5 µm, 12.5 µm) — a plausible
signal that this tier (nearest the table/widest part of the stone) is where
the dimensional-fidelity error (G3) is concentrated, though this was not
independently confirmed. No spurious 19-step over-segmentation of a single
facet was observed — each band's facet count is a plausible one-per-real-facet
count for a step cut, not spec-noted micro-slicing artifacts.

## Tuning log (honesty rule: report real numbers, do not tune to fake a pass)

Swept `facet_slope_jump` (0.10–0.15), `facet_seg_median_rows` (13–21), and
`facet_min_edge_mm` (0.25–0.5) individually and in a few combinations, all
against the same `holder_mask_rows=705` dataset:

| params (delta from default) | n planes | fallback | rms med/max (µm) | extent Δ (µm) X/Y/Z | watertight |
|---|---|---|---|---|---|
| default | 41 | 0 | 5.0 / 14.5 | +331.9 / +160.1 / +78.3 | True |
| slope_jump=0.10 | 41 | 0 | 5.0 / 12.5 | +339.2 / +150.3 / +78.3 | True |
| slope_jump=0.15 | 41 | 0 | 5.0 / 25.5 | +332.4 / +173.1 / +77.7 | True |
| seg_median_rows=13 | 45 | 0 | 5.0 / 19.5 | **+80.2** / +151.4 / +75.5 | True |
| seg_median_rows=21 | 41 | 0 | 5.1 / 21.7 | +292.8 / +181.4 / +78.5 | True |
| min_edge_mm=0.25 | 43 | 0 | 5.0 / 39.1 | +331.9 / +142.2 / +77.2 | True |
| min_edge_mm=0.5 | 40 | 0 | 5.0 / 14.5 | +331.9 / +160.8 / +78.4 | True |
| slope_jump=0.15, min_edge_mm=0.5 | 39 | 0 | 5.0 / 26.0 | +332.4 / +174.0 / +77.6 | True |
| slope_jump=0.10, min_edge_mm=0.25 | 43 | 0 | 5.0 / 39.1 | +339.2 / +132.5 / +77.2 | True |
| seg_median_rows=21, slope_jump=0.15 | 41 | 0 | 5.1 / 21.7 | +292.8 / +181.4 / +78.5 | True |
| seg_median_rows=13, slope_jump=0.10 | 45 | 0 | 5.0 / 19.5 | +80.2 / +151.4 / +77.5 | True |
| seg_median_rows=13, slope_jump=0.15 | 45 | 0 | 5.0 / 19.5 | +81.0 / +152.3 / +75.5 | True |
| seg_median_rows=13, min_edge_mm=0.25 | 46 | 0 | 5.0 / 19.5 | +80.2 / **+125.0** / +75.5 | True |
| seg_median_rows=13, min_edge_mm=0.5 | 42 | 0 | 5.0 / 19.5 | +80.2 / +129.0 / +76.1 | True |

Findings:
- `facet_seg_median_rows=13` (down from default 17) is the only lever that
  moves X meaningfully — from +331.9 µm to +80.2 µm — by recovering more,
  finer-segmented tangent facets (41→45 planes) that hug the true surface
  more tightly in X/Y. It is the best single change tried.
- No tested combination gets **all three axes** under the 50 µm gate at once.
  Best observed: `seg_median_rows=13, min_edge_mm=0.25` → X +80.2, Y +125.0,
  Z +75.5 µm — still 1.5–2.5× over on every axis.
- `facet_slope_jump` alone (0.10/0.15) has almost no effect on extents
  (X stays ~332–339 µm) but does move worst-facet rms (12.5→25.5 µm as jump
  loosens/tightens), a fit-quality/oversegmentation trade-off orthogonal to
  the dimensional-fidelity problem.
- `facet_min_edge_mm` alone has negligible effect on X/Z and a small,
  non-monotonic effect on Y; tightening it (0.25) roughly doubles worst-facet
  rms (14.5→39.1 µm) by admitting shorter, noisier polygon edges as facet
  candidates — a real quality/coverage trade-off, not a free improvement.
- Z delta is essentially invariant (75.5–78.5 µm) across every configuration
  tried. Z is set by the two z-extreme sample rows plus the single extremal
  table plane, none of which are touched by any of the three tuning knobs
  in scope for this task — consistent with the 2026-07-11 v1 note's finding
  that Z offset is a separate question from facet-clustering thresholds.
- Given G2 (fit quality) is comfortably passing (5.0 µm median vs the 15 µm
  gate) under every configuration, and no in-scope tuning combination clears
  G3, the script ships with the pipeline **defaults** rather than a
  cherry-picked config — consistent with the honesty rule ("do not tune to
  fake a pass"). The `seg_median_rows=13` finding is left as a documented
  lead for future (out-of-scope) work, not adopted as the new default.

## What changed vs the v1 (2026-07-11) result

- v1: 43 facets, rms only obtainable via ad-hoc instrumentation (not in
  metadata), median 32.8 µm / max 165.8 µm, extents +538/+430/+150 µm.
- v2.1 (this run): 41 facets, rms threaded into `mesh.metadata["facets"]["rms"]`
  natively (no instrumentation needed), median 5.0 µm / max 14.5 µm — a
  **~6.5× improvement in median fit quality** and dramatically tighter worst
  case (165.8→14.5 µm). Extents also improved (X +332 vs +538 µm, Y +160 vs
  +430 µm, Z +78 vs +150 µm) but are still outside the ~50 µm/axis gate.
  Reconstruction is also much faster (no soft_hull seed mesh required).

## Limitations / concerns

1. **G3 (dimensional fidelity) genuinely fails** and is not fixable within
   this task's tuning scope. `seg_median_rows=13` is the most promising lead
   (halves the X error) but was not adopted as it doesn't clear the gate on
   its own and touches fit-granularity trade-offs (facet count 41→45,
   worst-facet rms 14.5→19.5 µm) that deserve their own investigation rather
   than a last-minute default change under a validation task.
2. **Z delta (~75–78 µm) is structurally decoupled** from all three tuning
   knobs available here; per the 2026-07-11 note it likely comes from the
   extremal-plane sample-extent floor (`sm.z` min/max over any valid view),
   which is source code the brief does not authorize touching in this task.
3. **The lowest pavilion tier (~+20–26° vs reference +27°) has the worst
   individual-facet fits** (12.5, 14.5 µm) in the mesh; plausibly correlated
   with the overall dimensional error, but not independently confirmed here.
4. This validation is numeric/structural only. Per the task brief, the
   **visual gate (rendering `gem_facet.stl` next to `gem.stl` for user
   sign-off) is a separate, subsequent step** owned by the controller —
   not performed in this task.

## Candid verdict

The v2.1 facet detector is a clear, measured improvement over v1: it no
longer needs the soft-hull seed, runs in seconds instead of minutes, never
fell back during this validation or any tuning sweep, produces a correctly
watertight polyhedron with the correct table-only cap structure (no more
"flat lid over the culet" — the v1 visual bug this task exists to catch is
absent here), and its per-facet fit quality is excellent (5.0 µm median, well
inside the 15 µm gate) and qualitatively matches the pre-verified az-74 tilt
reference. But it is not yet dimensionally tight enough to pass the ~50
µm/axis fidelity gate — real, worst axis 80–330 µm off depending on
configuration, with no combination of the three sanctioned tuning knobs
closing that gap. **5 of 6 quantitative gates pass; G3 fails honestly.** This
is a real, load-bearing finding for the merge decision, not swept under the
rug — and it does not by itself confirm or deny the still-pending visual
gate.

## Files

- `scripts/validate_facet_gem04.py` — updated per the V2 Task 5 brief:
  prints tangent-vs-extremal split, per-facet rms in µm from
  `mesh.metadata["facets"]["rms"]`, the tilt ladder, extent/volume deltas vs
  `gem.stl` in µm, culet-cap / table-cap checks, and PASS/FAIL for all 6
  gates.
- `scans/gem04/gem_facet.stl` — overwritten with the v2.1 default-params
  output (41 planes; the run reported above).
- This note.
