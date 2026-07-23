"""Pure-PIL orthographic shaded side-by-side mesh comparison render.

No matplotlib/pyglet dependency: projects each mesh with a fixed
elevation/azimuth, shades faces with a simple directional light, and
rasterizes triangles with a per-panel z-buffer using only numpy + PIL.
"""
import numpy as np
from PIL import Image, ImageDraw


def _project(mesh, elev_deg, azim_deg, size):
    v = mesh.vertices - mesh.vertices.mean(axis=0)
    e, a = np.radians(elev_deg), np.radians(azim_deg)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    p = v @ Rz.T @ Rx.T
    span = np.max(np.ptp(p[:, :2], axis=0)) or 1.0
    scale = 0.8 * size / span
    xy = p[:, :2] * scale + size / 2.0
    xy[:, 1] = size - xy[:, 1]
    fn = mesh.face_normals @ Rz.T @ Rx.T
    return xy, p[:, 2], fn


def render_side_by_side(named_meshes, out_png, elev_deg=15, azim_deg=35, size=320):
    """named_meshes: list[(name, trimesh.Trimesh or None)]. Writes out_png:
    one shaded panel per mesh, tiled horizontally, with a name label on top.
    Never raises -- a None mesh or an empty/degenerate mesh just renders as
    a blank panel."""
    panels = []
    for name, mesh in named_meshes:
        img = Image.new("RGB", (size, size), (245, 245, 245))
        try:
            if mesh is not None and len(mesh.faces):
                px = img.load()
                xy, depth, fn = _project(mesh, elev_deg, azim_deg, size)
                face_depth = depth[mesh.faces].mean(axis=1)
                light = np.array([0.3, 0.3, 0.9]); light /= np.linalg.norm(light)
                shade = np.clip(fn @ light, 0.15, 1.0)
                zbuf = np.full((size, size), -1e9)
                for fi in np.argsort(face_depth):     # painter's: far to near
                    tri = xy[mesh.faces[fi]]
                    col = int(60 + 180 * shade[fi])
                    _fill_tri(px, zbuf, tri, face_depth[fi], (col, col, min(255, col + 30)), size)
        except Exception as exc:                      # pragma: no cover - defensive
            d = ImageDraw.Draw(img)
            d.text((6, size // 2), f"render error: {exc}"[:60], fill=(200, 0, 0))
        panels.append((name, img))
    W = size * len(panels)
    canvas = Image.new("RGB", (W, size + 18), (255, 255, 255))
    for k, (name, img) in enumerate(panels):
        canvas.paste(img, (k * size, 18))
        ImageDraw.Draw(canvas).text((k * size + 6, 4), name, fill=(0, 0, 0))
    canvas.save(out_png)


def _fill_tri(px, zbuf, tri, z, color, size):
    xs = tri[:, 0]; ys = tri[:, 1]
    if not np.all(np.isfinite(tri)):
        return
    x0, x1 = int(max(0, np.floor(xs.min()))), int(min(size - 1, np.ceil(xs.max())))
    y0, y1 = int(max(0, np.floor(ys.min()))), int(min(size - 1, np.ceil(ys.max())))
    if x1 < x0 or y1 < y0:
        return
    (ax, ay), (bx, by), (cx, cy) = tri
    denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(denom) < 1e-9:
        return
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            w0 = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / denom
            w1 = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / denom
            w2 = 1 - w0 - w1
            if w0 >= -0.01 and w1 >= -0.01 and w2 >= -0.01:
                if z > zbuf[xx, yy]:
                    zbuf[xx, yy] = z
                    px[xx, yy] = color
