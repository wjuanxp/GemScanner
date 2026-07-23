from dataclasses import dataclass
import numpy as np
from scipy.optimize import linprog
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans


@dataclass
class SupportSamples:
    theta: np.ndarray   # (V,) radians
    z: np.ndarray       # (H,) mm
    h: np.ndarray       # (H, V) mm, nan invalid
    valid: np.ndarray   # (H, V) bool


def build_support_samples(dataset, holder_mask_rows=0, threshold=None):
    """Right-edge support h(theta, z) from silhouettes (orthographic).
    theta convention: view normal u=(cos th, -sin th); h_right = +x_max."""
    m = dataset.manifest
    H, mmpp, V = m.image_height, m.mm_per_px, dataset.frame_count()
    z = np.array([row_to_z(v, H, mmpp) for v in range(H)])
    theta = np.radians(np.asarray(m.angles_deg, float))
    h = np.full((H, V), np.nan)
    for i in range(V):
        img = dataset.load_frame(i)
        mask = extract_silhouette(img, threshold, holder_mask_rows)
        spans = row_spans(mask)
        for v in range(H):
            L, R = spans[v]
            if L < 0:
                continue
            axc = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            h[v, i] = column_to_projection(R, axc, mmpp)
    return SupportSamples(theta=theta, z=z, h=h, valid=~np.isnan(h))


def synthetic_support_from_planes(planes, thetas_rad, z_values):
    """Exact support h(theta,z) of the convex body {a x+b y+c z <= d} via LP.
    At height z the slice is {(a,b).(x,y) <= d - c z}; support in direction
    u=(cos th,-sin th) is max u.(x,y) over that polygon (a small linprog)."""
    P = np.asarray(planes, float)
    A2 = P[:, :2]                      # (K,2) horizontal parts
    thetas_rad = np.asarray(thetas_rad, float)
    z_values = np.asarray(z_values, float)
    H, V = len(z_values), len(thetas_rad)
    h = np.full((H, V), np.nan)
    for vi, z in enumerate(z_values):
        b2 = P[:, 3] - P[:, 2] * z     # (K,) rhs at this height
        for ti, th in enumerate(thetas_rad):
            u = np.array([np.cos(th), -np.sin(th)])
            res = linprog(-u, A_ub=A2, b_ub=b2,
                          bounds=[(None, None), (None, None)])
            if res.success:
                h[vi, ti] = float(u @ res.x)
    return SupportSamples(theta=thetas_rad, z=z_values, h=h, valid=~np.isnan(h))
