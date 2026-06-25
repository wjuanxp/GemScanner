from dataclasses import dataclass


@dataclass
class ReconstructionParams:
    n_radial: int = 180
    holder_mask_rows: int = 0
    threshold: int = None
    bbox_mm: float = 50.0


@dataclass
class SliceResult:
    z_mm: float
    polygon: object = None     # np.ndarray (N,2) in object-frame mm, or None
