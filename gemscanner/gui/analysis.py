from dataclasses import dataclass
import numpy as np
import cv2
from gemscanner.vision.silhouette import extract_silhouette


@dataclass
class FrameAnalysis:
    min: int
    max: int
    mean: float
    histogram: list
    mask: object
    touches_border: bool
    bbox: object          # (rmin, rmax, cmin, cmax) or None
    centroid_col: object  # float or None


def analyze_frame(frame, threshold=None, holder_mask_rows=0, margin_px=2):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    hist = np.bincount(gray.ravel(), minlength=256)[:256].astype(int).tolist()
    mask = extract_silhouette(frame, threshold, holder_mask_rows)
    ys, xs = np.where(mask)
    if xs.size == 0:
        return FrameAnalysis(int(gray.min()), int(gray.max()), float(gray.mean()),
                             hist, mask, False, None, None)
    h, w = mask.shape
    touches = bool(xs.min() <= margin_px or xs.max() >= w - 1 - margin_px or
                   ys.min() <= margin_px or ys.max() >= h - 1 - margin_px)
    bbox = (int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max()))
    return FrameAnalysis(int(gray.min()), int(gray.max()), float(gray.mean()),
                         hist, mask, touches, bbox, float(xs.mean()))
