import math
import numpy as np
from gemscanner.camera.base import CameraBackend
from gemscanner.coords import projection_to_column


class SceneCamera(CameraBackend):
    """Renders the orthographic silhouette of an ellipsoid at the firmware's
    current rotation angle. Test double linking motion to imaging."""

    def __init__(self, stage_fw, rx, ry, rz, mm_per_px, width, height,
                 center_offset=(0.0, 0.0)):
        self._fw = stage_fw
        self.rx, self.ry, self.rz = rx, ry, rz
        self.mm_per_px = mm_per_px
        self.width, self.height = width, height
        self.cx, self.cy = center_offset
        self.axis_column = (width - 1) / 2.0
        self.v0 = (height - 1) / 2.0

    def open(self): pass
    def close(self): pass

    def _angle_rad(self):
        spr = self._fw.steps_per_rev or 1
        return math.radians(self._fw.pos_steps / spr * 360.0)

    def grab(self):
        th = self._angle_rad()
        img = np.full((self.height, self.width), 255, np.uint8)
        p_c = self.cx * math.cos(th) - self.cy * math.sin(th)
        for v in range(self.height):
            z = (self.v0 - v) * self.mm_per_px
            if abs(z) >= self.rz:
                continue
            s = math.sqrt(max(0.0, 1.0 - (z / self.rz) ** 2))
            half = s * math.sqrt((self.rx * math.cos(th)) ** 2 + (self.ry * math.sin(th)) ** 2)
            left = projection_to_column(p_c - half, self.axis_column, self.mm_per_px)
            right = projection_to_column(p_c + half, self.axis_column, self.mm_per_px)
            lo = max(0, int(math.ceil(left)))
            hi = min(self.width - 1, int(math.floor(right)))
            if hi >= lo:
                img[v, lo:hi + 1] = 0
        return img
