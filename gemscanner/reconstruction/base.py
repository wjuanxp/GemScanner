from dataclasses import dataclass


@dataclass
class ReconstructionParams:
    n_radial: int = 180
    holder_mask_rows: int = 0
    threshold: int = None
    bbox_mm: float = 50.0
    # de-terracing (both 0 = off). edge_median_rows smooths the silhouette edge
    # per view (image space, best visual); axial_median_rows smooths the ring
    # radius field along z (mesh space, cheapest). Both median = facet-preserving.
    edge_median_rows: int = 0
    axial_median_rows: int = 0
    # sub-pixel edge localisation: place each silhouette edge where the row's
    # intensity profile crosses the threshold instead of on the nearest whole
    # column. Removes the ~1 px edge quantisation that terracing feeds on.
    # Measured on gem04 (holder_mask_rows=705, 30 views): per-row edge
    # roughness (median |d2 edge/dz2|) 12.62 -> 2.18 um, -83%; mean edge shift
    # only +0.43 um, so it refines rather than rebiases -- real backlit edges
    # are anti-aliased and Otsu lands mid-ramp, making the crossings symmetric.
    # (A hard synthetic step has no ramp and does shift ~half a pixel per side.)
    # Default ON since 2026-07-23: user visually signed off on the gem04 strip
    # + facet sub-pixel meshes ("best so far"), clearing the facet v2.3 visual
    # gate. Disable per-run for a whole-pixel baseline (CLI --no-subpixel-edges,
    # GUI checkbox). Consumed by method="strip" and method="facet"; soft_hull
    # carves from a distance transform and ignores it.
    subpixel_edges: bool = True
    # "strip" = fast per-slice visual hull (default); "soft_hull" = anti-aliased
    # volumetric visual hull + marching cubes (metrology-grade, needs scikit-image)
    method: str = "strip"
    # facet method (method="facet"): unsupervised facet-plane recovery from
    # the raw support function (v2.3: facet azimuths from cross-slice polygon
    # edges w/ extended z-bands + per-azimuth TWO-SCALE affine tier
    # segmentation + girdle-band recovery; no soft-hull seed)
    facet_min_inliers: int = 8         # min rows per coarse tier (fine-pass
                                       # tiers use an internal 5-row floor)
    facet_merge_deg: float = 6.0
    facet_fallback: bool = True
    facet_seg_median_rows: int = 17    # Theil-Sen slope window (rows)
    facet_slope_jump: float = 0.12     # min two-sided slope jump between tiers
    facet_min_seg_mm: float = 0.25     # min tier z-span
    facet_min_edge_mm: float = 0.35    # min slice-polygon edge (carve-quantum filter)
    facet_table_width_frac: float = 0.3  # table plateau width vs girdle width


@dataclass
class SliceResult:
    z_mm: float
    polygon: object = None     # np.ndarray (N,2) in object-frame mm, or None
