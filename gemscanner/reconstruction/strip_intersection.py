import math
import numpy as np
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import silhouette_row_spans
from gemscanner.geometry.halfplane import clip_convex_polygon
from gemscanner.reconstruction.base import ReconstructionParams, SliceResult


def median_smooth_spans(spans, window):
    """Median-filter silhouette left/right edge columns along v (image space).

    Rows with L<0 (empty) are left untouched; smoothing runs only over contiguous
    valid segments so facet edges survive while per-row edge outliers (terracing
    source) are rejected. window<2 is identity.
    """
    spans = np.asarray(spans, dtype=float)
    if not window or window < 2:
        return spans
    out = spans.copy()
    valid = spans[:, 0] >= 0
    half = window // 2
    n = len(spans)
    i = 0
    while i < n:
        if not valid[i]:
            i += 1
            continue
        j = i
        while j < n and valid[j]:
            j += 1
        for r in range(i, j):
            lo = max(i, r - half)
            hi = min(j, r + half + 1)
            out[r, 0] = np.median(spans[lo:hi, 0])
            out[r, 1] = np.median(spans[lo:hi, 1])
        i = j
    return out


class StripIntersectionReconstructor:
    def slice_cross_sections(self, dataset, params=None):
        params = params if params is not None else ReconstructionParams()
        m = dataset.manifest
        H = m.image_height
        mmpp = m.mm_per_px

        frames = []
        for i in range(dataset.frame_count()):
            img = dataset.load_frame(i)
            raw = silhouette_row_spans(img, params.threshold,
                                       params.holder_mask_rows,
                                       params.subpixel_edges)
            spans = median_smooth_spans(raw, params.edge_median_rows)
            th = math.radians(m.angles_deg[i])
            normal = np.array([math.cos(th), -math.sin(th)])
            frames.append((spans, normal))

        slices = []
        for v in range(H):
            z = row_to_z(v, H, mmpp)
            axis_col = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            b = params.bbox_mm
            poly = np.array([[-b, -b], [b, -b], [b, b], [-b, b]], dtype=float)
            empty = False
            for spans, normal in frames:
                L, R = spans[v]
                if L < 0:
                    empty = True
                    break
                pmin = column_to_projection(L, axis_col, mmpp)
                pmax = column_to_projection(R, axis_col, mmpp)
                poly = clip_convex_polygon(poly, normal, pmax)
                if len(poly) == 0:
                    empty = True
                    break
                poly = clip_convex_polygon(poly, -normal, -pmin)
                if len(poly) == 0:
                    empty = True
                    break
            if empty or len(poly) < 3:
                slices.append(SliceResult(z, None))
            else:
                slices.append(SliceResult(z, poly))
        return slices

    def reconstruct(self, dataset, params=None):
        from gemscanner.reconstruction.mesh import loft_slices_to_mesh
        params = params if params is not None else ReconstructionParams()
        slices = self.slice_cross_sections(dataset, params)
        return loft_slices_to_mesh(slices, params.n_radial,
                                   params.axial_median_rows)
