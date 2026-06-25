import math
import numpy as np
from gemscanner.coords import row_to_z, axis_column_at_row, column_to_projection
from gemscanner.vision.silhouette import extract_silhouette, row_spans
from gemscanner.geometry.halfplane import clip_convex_polygon
from gemscanner.reconstruction.base import ReconstructionParams, SliceResult


class StripIntersectionReconstructor:
    def slice_cross_sections(self, dataset, params=None):
        params = params or ReconstructionParams()
        m = dataset.manifest
        H = m.image_height
        mmpp = m.mm_per_px

        frames = []
        for i in range(dataset.frame_count()):
            img = dataset.load_frame(i)
            mask = extract_silhouette(img, params.threshold, params.holder_mask_rows)
            spans = row_spans(mask)
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
        params = params or ReconstructionParams()
        slices = self.slice_cross_sections(dataset, params)
        return loft_slices_to_mesh(slices, params.n_radial)
