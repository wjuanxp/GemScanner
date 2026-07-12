from dataclasses import dataclass
import numpy as np
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans
from gemscanner.reconstruction.base import ReconstructionParams


@dataclass
class SupportMaps:
    z: np.ndarray          # (H,)
    theta: np.ndarray      # (V,)
    h_right: np.ndarray    # (H, V)
    h_left: np.ndarray     # (H, V)
    valid: np.ndarray      # (H, V) bool


def support_maps(dataset, params=None):
    """Build per-row/per-view support maps h_right/h_left from silhouettes.
    Assumes a full 360-degree turntable scan: downstream facet recovery only
    consumes h_right, so a half-turn scan would silently omit facets facing
    the unscanned hemisphere."""
    params = params if params is not None else ReconstructionParams()
    m = dataset.manifest
    H, mmpp = m.image_height, m.mm_per_px
    V = dataset.frame_count()

    z = np.array([row_to_z(v, H, mmpp) for v in range(H)])
    theta = np.radians(np.asarray(m.angles_deg, float))
    h_right = np.full((H, V), np.nan)
    h_left = np.full((H, V), np.nan)

    for i in range(V):
        img = dataset.load_frame(i)
        mask = extract_silhouette(img, params.threshold, params.holder_mask_rows)
        spans = row_spans(mask)
        for v in range(H):
            L, R = spans[v]
            if L < 0:
                continue
            axc = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            pmin = column_to_projection(L, axc, mmpp)
            pmax = column_to_projection(R, axc, mmpp)
            h_right[v, i] = pmax
            h_left[v, i] = -pmin

    valid = ~np.isnan(h_right)
    return SupportMaps(z=z, theta=theta, h_right=h_right, h_left=h_left, valid=valid)
