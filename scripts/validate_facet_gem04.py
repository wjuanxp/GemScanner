# scripts/validate_facet_gem04.py
"""Reconstruct scans/gem04 with method=facet (v2.3) and report facet-quality
metrics + quantitative gate verdicts against the pre-verified az-74 reference.
Note: the Z-extent gate (~50um) is a known out-of-scope gap (+77um = sharp culet
apex vs the smoothed reference's rounded tip); user accepted at visual sign-off
(pavilion tiers ~= +27/+39/+45/+50 deg, crown ~= -58 deg, per-tier rms
4.7-8.0 um)."""
import math
import warnings
import numpy as np
import trimesh
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.reconstruction.pipeline import reconstruct_dataset

SCAN = "scans/gem04"
# gem04's silhouette includes the pedestal post below the gem; the manifest
# does not carry holder_mask_rows, so it must be supplied explicitly (see
# config.example.yaml, which documents 705 for this rig/mount). Confirmed
# empirically: sweeping holder_mask_rows against the existing gem.stl shows
# 705 matches gem.stl's X/Y/Z extents to within a few um (0 makes the
# reconstruction include the pedestal and blow extents up ~5x).
HOLDER_MASK_ROWS = 705

GATE_RMS_MEDIAN_UM = 15.0
GATE_EXTENT_TOL_UM = 50.0


def tilt_deg(plane):
    a, b, c, _d = plane
    return math.degrees(math.atan2(c, math.hypot(a, b)))


def main():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mesh = reconstruct_dataset(
            SCAN, ReconstructionParams(method="facet", holder_mask_rows=HOLDER_MASK_ROWS))
        fallback_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        for w in caught:
            print(f"WARNING: {w.category.__name__}: {w.message}")

    fac = mesh.metadata.get("facets", {})
    planes = fac.get("planes", [])
    rms_list = fac.get("rms", [])
    if not planes:
        print("FACET RECOVERY FELL BACK: mesh.metadata has no 'facets' key "
              "(or empty planes) -> this is a soft_hull mesh, not a faceted one.")

    tangent = [(p, r) for p, r in zip(planes, rms_list) if r != 0.0]
    extremal = [(p, r) for p, r in zip(planes, rms_list) if r == 0.0]

    print(f"facets={len(planes)}  tangent={len(tangent)}  extremal={len(extremal)}"
          f"  vertices(meet-points)={len(fac.get('vertices', []))}"
          f"  edges={len(fac.get('edges', []))}")
    print(f"watertight={mesh.is_watertight}  volume={mesh.volume:.2f} mm^3")

    ext = mesh.bounding_box.extents
    print(f"extents (mm): {ext[0]:.4f} x {ext[1]:.4f} x {ext[2]:.4f}")

    ref = None
    try:
        ref = trimesh.load(f"{SCAN}/gem.stl")
        ref_ext = ref.bounding_box.extents
        print(f"reference gem.stl extents (mm): {ref_ext[0]:.4f} x {ref_ext[1]:.4f} x {ref_ext[2]:.4f}")
        delta_um = (ext - ref_ext) * 1000.0
        print(f"extent delta vs gem.stl (um): X={delta_um[0]:+.1f}  Y={delta_um[1]:+.1f}  Z={delta_um[2]:+.1f}")
        vol_delta = mesh.volume - ref.volume
        print(f"volume delta vs gem.stl: {vol_delta:+.3f} mm^3 ({100.0 * vol_delta / ref.volume:+.2f}%)")
    except Exception as e:
        print(f"(no reference comparison: {e})")
        delta_um = None

    # --- tangent-facet rms stats (um) ---
    if tangent:
        rms_um = np.array([r * 1000.0 for _p, r in tangent])
        rms_median = float(np.median(rms_um))
        rms_max = float(np.max(rms_um))
        print(f"tangent-facet rms (um): median={rms_median:.1f}  max={rms_max:.1f}"
              f"  min={rms_um.min():.1f}  n={len(rms_um)}")
    else:
        rms_median = rms_max = float("nan")
        print("tangent-facet rms: NO TANGENT FACETS RECOVERED")

    # --- tilt ladder (sorted), tangent facets only ---
    print("tilt ladder (deg, tangent facets, sorted) with per-facet rms (um):")
    tilts = sorted(((tilt_deg(p), r * 1000.0) for p, r in tangent), key=lambda t: t[0])
    for t, r in tilts:
        print(f"  {t:+7.2f} deg   rms={r:6.1f} um")

    # --- extremal / culet-cap check ---
    print("extremal planes (source: table/culet caps):")
    culet_cap_present = False
    table_cap_count = 0
    for p, _r in extremal:
        a, b, c, d = p
        role = "TOP CAP (c>0)" if c > 0 else ("BOTTOM/TABLE CAP (c<0)" if c < 0 else "?")
        if c > 0:
            culet_cap_present = True
        if c < 0:
            table_cap_count += 1
        print(f"  plane=({a:+.4f},{b:+.4f},{c:+.4f},{d:+.4f})  tilt={tilt_deg(p):+.2f} deg  -> {role}")

    # --- gate verdicts ---
    print("\n=== GATE VERDICTS ===")
    g1 = len(fallback_warnings) == 0
    print(f"[{'PASS' if g1 else 'FAIL'}] G1 no fallback RuntimeWarning "
          f"({len(fallback_warnings)} fallback warning(s))")

    g2 = (not math.isnan(rms_median)) and rms_median <= GATE_RMS_MEDIAN_UM
    print(f"[{'PASS' if g2 else 'FAIL'}] G2 tangent rms median <= {GATE_RMS_MEDIAN_UM} um "
          f"(got {rms_median:.1f} um)")

    if delta_um is not None:
        g3 = bool(np.all(np.abs(delta_um) <= GATE_EXTENT_TOL_UM))
        worst = float(np.max(np.abs(delta_um)))
        print(f"[{'PASS' if g3 else 'FAIL'}] G3 extents within {GATE_EXTENT_TOL_UM} um/axis of gem.stl "
              f"(worst axis delta {worst:.1f} um)")
    else:
        g3 = False
        print("[FAIL] G3 extents within tolerance of gem.stl (no reference available)")

    g4 = bool(mesh.is_watertight)
    print(f"[{'PASS' if g4 else 'FAIL'}] G4 watertight (got {mesh.is_watertight})")

    g5 = not culet_cap_present
    print(f"[{'PASS' if g5 else 'FAIL'}] G5 no culet cap (extremal plane with c>0) "
          f"(culet_cap_present={culet_cap_present})")

    g6 = table_cap_count == 1
    print(f"[{'PASS' if g6 else 'FAIL'}] G6 exactly one table cap (c<0 extremal plane) "
          f"(got {table_cap_count})")

    all_pass = g1 and g2 and g3 and g4 and g5 and g6
    print(f"\nALL GATES: {'PASS' if all_pass else 'FAIL'}")

    mesh.export("scans/gem04/gem_facet.stl")
    print("wrote scans/gem04/gem_facet.stl")


if __name__ == "__main__":
    main()
