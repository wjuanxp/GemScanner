# gemscanner/synthetic/generator.py
import os
import math
import numpy as np
import cv2
from gemscanner.coords import projection_to_column, z_to_row
from gemscanner.storage.manifest import ScanManifest


def generate_ellipsoid_scan(out_dir, rx, ry, rz, n_views=180, mm_per_px=0.05,
                            width=400, height=400, center_offset=(0.0, 0.0)):
    """Render orthographic silhouettes of an ellipsoid rotating about the vertical
    axis. The ellipsoid center sits at object-frame (cx, cy) and rotates with the
    object (eccentric placement). Background is bright (255), silhouette dark (0)."""
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    axis_column = (width - 1) / 2.0
    v0 = (height - 1) / 2.0
    cx, cy = center_offset
    angles = [i * 360.0 / n_views for i in range(n_views)]
    frame_files = []
    for i, ang in enumerate(angles):
        th = math.radians(ang)
        img = np.full((height, width), 255, dtype=np.uint8)
        p_c = cx * math.cos(th) - cy * math.sin(th)        # projected center swing
        for v in range(height):
            z = (v0 - v) * mm_per_px
            if abs(z) >= rz:
                continue
            s = math.sqrt(max(0.0, 1.0 - (z / rz) ** 2))
            half = s * math.sqrt((rx * math.cos(th)) ** 2 + (ry * math.sin(th)) ** 2)
            left = projection_to_column(p_c - half, axis_column, mm_per_px)
            right = projection_to_column(p_c + half, axis_column, mm_per_px)
            lo = max(0, int(math.ceil(left)))
            hi = min(width - 1, int(math.floor(right)))
            if hi >= lo:
                img[v, lo:hi + 1] = 0
        fname = f"{i:04d}.png"
        cv2.imwrite(os.path.join(out_dir, "frames", fname), img)
        frame_files.append(f"frames/{fname}")
    manifest = ScanManifest(
        angles_deg=angles, mm_per_px=mm_per_px, axis_column=axis_column,
        axis_tilt_rad=0.0, image_width=width, image_height=height,
        frame_files=frame_files,
        metadata={"shape": "ellipsoid", "rx": rx, "ry": ry, "rz": rz,
                  "center_offset": [cx, cy]},
    )
    manifest.save(os.path.join(out_dir, "manifest.json"))
    return out_dir


def generate_polyhedron_scan(out_dir, vertices, n_views=180, mm_per_px=0.05,
                             width=400, height=400):
    """Render orthographic silhouettes of a convex polyhedron rotating about the
    vertical (z) axis. Silhouette = filled 2D convex hull of projected vertices.
    Background bright (255), silhouette dark (0)."""
    os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
    vertices = np.asarray(vertices, dtype=float)
    axis_column = (width - 1) / 2.0
    angles = [i * 360.0 / n_views for i in range(n_views)]
    frame_files = []
    for i, ang in enumerate(angles):
        th = math.radians(ang)
        p = vertices[:, 0] * math.cos(th) - vertices[:, 1] * math.sin(th)  # horiz proj
        cols = projection_to_column(p, axis_column, mm_per_px)
        rows = z_to_row(vertices[:, 2], height, mm_per_px)
        pts = np.column_stack([cols, rows]).astype(np.float32)
        img = np.full((height, width), 255, dtype=np.uint8)
        hull = cv2.convexHull(pts)
        cv2.fillConvexPoly(img, hull.astype(np.int32), 0)
        fname = f"{i:04d}.png"
        cv2.imwrite(os.path.join(out_dir, "frames", fname), img)
        frame_files.append(f"frames/{fname}")
    manifest = ScanManifest(
        angles_deg=angles, mm_per_px=mm_per_px, axis_column=axis_column,
        axis_tilt_rad=0.0, image_width=width, image_height=height,
        frame_files=frame_files,
        metadata={"shape": "polyhedron", "n_vertices": int(len(vertices))},
    )
    manifest.save(os.path.join(out_dir, "manifest.json"))
    return out_dir
