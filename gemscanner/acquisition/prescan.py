from dataclasses import dataclass
import numpy as np
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.coords import column_to_projection


@dataclass
class PrescanResult:
    ok: bool
    offending_angle: float
    eccentricity_mm: float
    touched_border: bool


def prescan_fov_check(camera, stage, axis_column, mm_per_px,
                      n_probe=12, threshold=None, margin_px=2, holder_mask_rows=0):
    inc = 360.0 / n_probe
    touched = False
    offending = None
    centroid_cols = []
    with camera:
        for i in range(n_probe):
            if i > 0:
                stage.move_deg(inc)
            mask = extract_silhouette(camera.grab(), threshold, holder_mask_rows)
            ys, xs = np.where(mask)
            if xs.size == 0:
                continue
            h, w = mask.shape
            if (xs.min() <= margin_px or xs.max() >= w - 1 - margin_px or
                    ys.min() <= margin_px or ys.max() >= h - 1 - margin_px):
                touched = True
                if offending is None:
                    offending = round(i * inc, 3)
            centroid_cols.append(xs.mean())
        if n_probe > 1:
            stage.move_deg(inc)   # complete the revolution back to start
    if centroid_cols:
        swing_px = (max(centroid_cols) - min(centroid_cols)) / 2.0
        ecc = abs(column_to_projection(axis_column + swing_px, axis_column, mm_per_px))
    else:
        ecc = 0.0
    return PrescanResult(ok=not touched, offending_angle=offending,
                         eccentricity_mm=ecc, touched_border=touched)
