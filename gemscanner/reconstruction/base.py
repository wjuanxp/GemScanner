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
    # "strip" = fast per-slice visual hull (default); "soft_hull" = anti-aliased
    # volumetric visual hull + marching cubes (metrology-grade, needs scikit-image)
    method: str = "strip"
    # facet method (method="facet"): unsupervised facet-plane recovery from
    # the raw support function (v2.1: facet azimuths from cross-slice polygon
    # edges + per-azimuth affine tier segmentation; no soft-hull seed)
    facet_min_inliers: int = 8         # min rows per tier / refit inliers
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
