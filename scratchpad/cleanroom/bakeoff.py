"""gem04 bake-off: the three clean-room candidates vs a space-carving
control and the shipped v2.3 facet benchmark, on the REAL gem04 scan.

Runtime note (no subsampling needed): the naive worry going in was that
support samples at full image resolution (1944 rows x 180 views) would make
candidate B's per-z-slice LP intractable. In practice `build_support_samples`
only yields 333 valid z-rows out of 1944 for gem04 (holder_mask_rows=705
plus rows above/below the stone in frame are NaN) -- smaller than the 220
row synthetic fixture the candidates were developed against. All three
candidates run on the FULL, unsubsampled support grid in well under a
minute combined; no z-decimation was applied to any candidate.

Tuning note (rms_tol_mm retuned 0.15 -> 0.7 for ALL THREE candidates):
`rms_tol_mm=0.15` was tuned on EXACT synthetic support data (zero sensor
noise). On real gem04 data every candidate's raw (pre-merge) facet_rms
population starts well above 0.15mm (min observed: A 0.122, B 0.153, C
0.147 -- so 0.15 keeps only a handful of hypotheses) and at 0.15 all three
candidates fail outright: `planes_to_mesh` raises ValueError (their
half-spaces do not bound a closed region) with 0-3 surviving tangent
facets. This is not a hidden defect being patched over: real silhouette
threshold/quantization noise sets a real, non-zero facet_rms floor that the
synthetic-tuned tolerance never had to clear.

0.7mm was chosen by inspecting the raw rms distributions before filtering
(see `.superpowers/sdd/task-7-report.md` for the full histograms):
  - Candidate B (dual/hull) shows the clearest signal: its 31 raw hull-face
    clusters split into three well-separated bands -- 21 clusters at
    rms<=0.65mm (real facets), 3 at rms in [1.39, 1.58]mm (girdle-crossing
    hull artifacts, exactly the failure mode its own docstring predicts),
    and 7 at rms>=4.7mm (gross outliers). 0.7mm sits cleanly in the gap
    between the first two bands.
  - Candidates A and C have no such clean gap (their rms populations are
    continuous), but their mesh extents vs tolerance stabilize (diminishing
    marginal change) once tol reaches ~0.7-1.0mm; 0.7mm is the conservative
    (fewer low-quality facets admitted) end of that plateau.
The SAME 0.7mm is used for all three so the bake-off stays apples-to-apples
(one shared, data-justified tolerance) rather than a per-candidate value
picked to flatter any one method. This is reported, not hidden.
"""
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
RMS_TOL_MM = 0.7   # retuned from the synthetic-fixture default of 0.15mm; see module docstring


def _assemble(planes_fn, samples, rms_tol_mm):
    recs = merge_planes(planes_fn(samples, rms_tol_mm=rms_tol_mm))
    recs = recs + extremal_caps(samples)
    tangent = [r for r in recs if r["rms"] > 0]
    mesh, verts, edges = planes_to_mesh([r["plane"] for r in recs])
    return mesh, recs, tangent


def _metrics(name, mesh, tangent, ref):
    ext = mesh.bounding_box.extents
    dvec = (ext - ref.bounding_box.extents) * 1000.0
    rms = np.array([r["rms"] * 1000.0 for r in tangent]) if tangent else np.array([np.nan])
    return dict(name=name, planes=len(tangent), watertight=bool(mesh.is_watertight),
                extents=ext, dX=dvec[0], dY=dvec[1], dZ=dvec[2],
                vol=mesh.volume, dvol=mesh.volume - ref.volume,
                rms_med=float(np.nanmedian(rms)), rms_max=float(np.nanmax(rms)),
                strike=strike_energy(mesh))


def _failed_row(name, tangent_count, err):
    return dict(name=name, planes=tangent_count, watertight=False, extents=None,
                dX=np.nan, dY=np.nan, dZ=np.nan, vol=np.nan, dvol=np.nan,
                rms_med=np.nan, rms_max=np.nan, strike=np.nan, failed=str(err))


def main():
    t_start = time.time()
    ds = load_dataset(SCAN)
    ref = trimesh.load(f"{SCAN}/gem.stl")
    print("building support samples...")
    s = build_support_samples(ds, holder_mask_rows=HOLDER)
    n_valid_rows = int(s.valid.any(axis=1).sum())
    print(f"support grid: {s.h.shape[0]} rows x {s.h.shape[1]} views "
          f"({n_valid_rows} rows have any valid data) -- no subsampling applied "
          f"(see module docstring)")
    print(f"rms_tol_mm = {RMS_TOL_MM} for all three candidates (retuned from 0.15; "
          f"see module docstring)")

    rows = []
    meshes = []
    for name, slug, fn in [("Cand-A RANSAC", "cand_a", reconstruct_ransac),
                            ("Cand-B dual", "cand_b", reconstruct_dual),
                            ("Cand-C EGI", "cand_c", reconstruct_egi)]:
        t0 = time.time()
        try:
            mesh, recs, tangent = _assemble(fn, s, RMS_TOL_MM)
        except ValueError as exc:
            # planes_to_mesh: half-spaces don't bound a closed region. This is
            # a real finding (too few/degenerate planes at this tolerance) --
            # record it and keep going, do not abort the harness.
            try:
                recs = merge_planes(fn(s, rms_tol_mm=RMS_TOL_MM))
                tangent_count = len([r for r in recs if r["rms"] > 0])
            except Exception:
                tangent_count = -1
            m = _failed_row(name, tangent_count, exc)
            m["sec"] = time.time() - t0
            rows.append(m)
            meshes.append((name + " [FAILED]", None))
            print(f"{name}: FAILED ({exc}) -- {tangent_count} tangent facets, "
                  f"{time.time() - t0:.1f}s")
            continue
        m = _metrics(name, mesh, tangent, ref)
        m["sec"] = time.time() - t0
        rows.append(m)
        meshes.append((name, mesh))
        out_path = f"scratchpad/cleanroom/{slug}_gem04.stl"
        mesh.export(out_path)
        print(f"{name}: {len(tangent)} tangent facets, watertight={mesh.is_watertight}, "
              f"{m['sec']:.1f}s -> {out_path}")

    # control (space carving = shipped strip) and benchmark (shipped v2.3 facet)
    # -- the ONE sanctioned exception to the clean-room import rule, clearly labelled.
    from gemscanner.reconstruction.pipeline import reconstruct_dataset
    from gemscanner.reconstruction.base import ReconstructionParams
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ctrl = reconstruct_dataset(SCAN, ReconstructionParams(method="strip", holder_mask_rows=HOLDER))
    ctrl_sec = time.time() - t0
    t0 = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bench = reconstruct_dataset(SCAN, ReconstructionParams(method="facet", holder_mask_rows=HOLDER))
    bench_sec = time.time() - t0
    for name, mesh, sec in [("CONTROL strip", ctrl, ctrl_sec), ("BENCH v2.3", bench, bench_sec)]:
        ext = mesh.bounding_box.extents
        dvec = (ext - ref.bounding_box.extents) * 1000.0
        rows.append(dict(name=name, planes=len(getattr(mesh, "faces", [])),
                          watertight=bool(mesh.is_watertight), extents=ext,
                          dX=dvec[0], dY=dvec[1], dZ=dvec[2], vol=mesh.volume,
                          dvol=mesh.volume - ref.volume, rms_med=np.nan, rms_max=np.nan,
                          strike=strike_energy(mesh), sec=sec))
        meshes.append((name, mesh))
        print(f"{name}: {len(getattr(mesh, 'faces', []))} faces, "
              f"watertight={mesh.is_watertight}, {sec:.1f}s")

    hdr = f"{'method':<16}{'facets':>7}{'wt':>4}{'dX':>8}{'dY':>8}{'dZ':>8}" \
          f"{'rmsMed':>8}{'strike':>8}{'sec':>7}"
    print("\n" + hdr); print("-" * len(hdr))
    for m in rows:
        wt_str = str(m["watertight"])[0] if not m.get("failed") else "F"
        dX = f"{m['dX']:>8.0f}" if np.isfinite(m['dX']) else f"{'--':>8}"
        dY = f"{m['dY']:>8.0f}" if np.isfinite(m['dY']) else f"{'--':>8}"
        dZ = f"{m['dZ']:>8.0f}" if np.isfinite(m['dZ']) else f"{'--':>8}"
        rms_med = f"{m['rms_med']:>8.1f}" if np.isfinite(m['rms_med']) else f"{'--':>8}"
        strike = f"{m['strike']:>8.1f}" if np.isfinite(m['strike']) else f"{'--':>8}"
        print(f"{m['name']:<16}{m['planes']:>7}{wt_str:>4}{dX}{dY}{dZ}"
              f"{rms_med}{strike}{m['sec']:>7.1f}")
    print("\n(units: d* um vs gem.stl, rmsMed um, strike um high-pass energy; "
          "wt='F' = planes_to_mesh FAILED, not a watertight=False mesh)")

    # markdown block for the note
    print("\n" + "| method | facets | watertight | dX(um) | dY(um) | dZ(um) | "
          "rmsMed(um) | strike(um) | sec |")
    print("|---|---:|:--:|---:|---:|---:|---:|---:|---:|")
    for m in rows:
        wt = "FAIL" if m.get("failed") else str(m["watertight"])
        dX = f"{m['dX']:.0f}" if np.isfinite(m['dX']) else "--"
        dY = f"{m['dY']:.0f}" if np.isfinite(m['dY']) else "--"
        dZ = f"{m['dZ']:.0f}" if np.isfinite(m['dZ']) else "--"
        rms_med = f"{m['rms_med']:.1f}" if np.isfinite(m['rms_med']) else "--"
        strike = f"{m['strike']:.1f}" if np.isfinite(m['strike']) else "--"
        print(f"| {m['name']} | {m['planes']} | {wt} | {dX} | {dY} | {dZ} | "
              f"{rms_med} | {strike} | {m['sec']:.1f} |")

    render_side_by_side([("gem.stl", ref)] + meshes,
                        "scratchpad/cleanroom/bakeoff_gem04.png")
    print("\nwrote scratchpad/cleanroom/bakeoff_gem04.png")
    print(f"\ntotal wall-clock: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
