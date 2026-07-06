"""Anti-aliased / soft visual-hull reconstruction.

Per view, a signed distance field of the silhouette (positive inside, negative
outside, sub-pixel) is sampled into an object-frame voxel grid; occupancy is the
min over views (approximate visual-hull SDF). Marching cubes at 0 extracts the
surface, coupling all three axes and interpolating sub-voxel -- so the per-row
terracing of the independent 2D carve cannot appear.

Requires scikit-image (marching cubes). Internal silhouette holes (bright
caustics through a translucent gem) are filled first so they don't carve
spurious 3D cavities.
"""
import math
import numpy as np
import cv2
import trimesh
from skimage import measure
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.coords import (row_to_z, z_to_row, axis_column_at_row,
                               column_to_projection)
from gemscanner.reconstruction.base import ReconstructionParams

_BIG = 1e6


def _fill_holes(mask):
    """Fill holes fully enclosed by the silhouette (uint8 0/1) using flood fill."""
    m = (np.asarray(mask) > 0).astype(np.uint8) * 255
    ff = m.copy()
    h, w = m.shape
    cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
    holes = cv2.bitwise_not(ff)                 # background pockets = interior holes
    return ((m | holes) > 0).astype(np.uint8)


class SoftHullReconstructor:
    def reconstruct(self, dataset, params=None, vox_mm=None, target_dim=220,
                    margin_vox=3, keep_largest=True, cap_base=True,
                    zlim=None, rlim=None):
        params = params if params is not None else ReconstructionParams()
        m = dataset.manifest
        H, W, mmpp = m.image_height, m.image_width, m.mm_per_px

        sdfs, cos, sin = [], [], []
        row_valid = np.zeros(H, bool)
        pmax_abs = 0.0
        for i in range(dataset.frame_count()):
            img = dataset.load_frame(i)
            mask = extract_silhouette(img, params.threshold, params.holder_mask_rows)
            mask = _fill_holes(mask)
            din = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
            dout = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 3)
            sdfs.append((din - dout).astype(np.float32))
            th = math.radians(m.angles_deg[i])
            cos.append(math.cos(th)); sin.append(math.sin(th))
            rows = np.where(mask.any(axis=1))[0]
            if rows.size:
                row_valid[rows] = True
                cols = np.where(mask.any(axis=0))[0]
                pmax_abs = max(pmax_abs,
                               abs(column_to_projection(cols[0], m.axis_column, mmpp)),
                               abs(column_to_projection(cols[-1], m.axis_column, mmpp)))

        vrows = np.where(row_valid)[0]
        if vrows.size < 2:
            raise ValueError("no silhouette found")
        zmax = row_to_z(vrows[0], H, mmpp); zmin = row_to_z(vrows[-1], H, mmpp)
        R = pmax_abs * 1.05
        if zlim is not None:
            zmin, zmax = max(zmin, zlim[0]), min(zmax, zlim[1])
        if rlim is not None:
            R = min(R, rlim)
        if vox_mm is None:
            vox_mm = max(2 * R, zmax - zmin) / target_dim
        pad = margin_vox * vox_mm
        xs = np.arange(-R - pad, R + pad, vox_mm)
        ys = np.arange(-R - pad, R + pad, vox_mm)
        zs = np.arange(zmin - pad, zmax + pad, vox_mm)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        nx, ny, nz = len(xs), len(ys), len(zs)
        vol = np.full((nx, ny, nz), -_BIG, np.float32)

        for k, z in enumerate(zs):
            v = z_to_row(z, H, mmpp)
            if v < 0 or v > H - 1:
                continue
            vlo = int(math.floor(v)); fv = v - vlo
            axc = axis_column_at_row(m.axis_column, m.axis_tilt_rad, v, H)
            occ = np.full((nx, ny), _BIG, np.float32)
            for i in range(len(sdfs)):
                line = sdfs[i][vlo] * (1 - fv) + sdfs[i][min(vlo + 1, H - 1)] * fv
                u = axc + (X * cos[i] - Y * sin[i]) / mmpp
                ulo = np.floor(u).astype(np.int32); fu = u - ulo
                ok = (ulo >= 0) & (ulo + 1 < W)
                uc = np.clip(ulo, 0, W - 2)
                samp = np.where(ok, line[uc] * (1 - fu) + line[uc + 1] * fu, -_BIG)
                np.minimum(occ, samp, out=occ)
            vol[:, :, k] = occ * mmpp

        verts, faces, _, _ = measure.marching_cubes(
            vol, level=0.0, spacing=(vox_mm, vox_mm, vox_mm))
        verts += np.array([xs[0], ys[0], zs[0]])
        mesh = trimesh.Trimesh(verts, faces, process=True)
        if keep_largest:
            comps = mesh.split(only_watertight=False)
            if len(comps):
                mesh = max(comps, key=lambda c: c.area)
        if cap_base:
            trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_normals(mesh)
        return mesh
