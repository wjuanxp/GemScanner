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


@dataclass
class SliceResult:
    z_mm: float
    polygon: object = None     # np.ndarray (N,2) in object-frame mm, or None
