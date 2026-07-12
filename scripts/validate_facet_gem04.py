# scripts/validate_facet_gem04.py
"""Reconstruct scans/gem04 with method=facet and report facet-quality metrics."""
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


def main():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mesh = reconstruct_dataset(
            SCAN, ReconstructionParams(method="facet", holder_mask_rows=HOLDER_MASK_ROWS))
        for w in caught:
            print(f"WARNING: {w.category.__name__}: {w.message}")

    fac = mesh.metadata.get("facets", {})
    planes = fac.get("planes", [])
    if not planes:
        print("FACET RECOVERY FELL BACK: mesh.metadata has no 'facets' key "
              "(or empty planes) -> this is a soft_hull mesh, not a faceted one.")
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
