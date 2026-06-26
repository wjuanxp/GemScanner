import os
from dataclasses import dataclass
import cv2
from gemscanner.storage.manifest import ScanManifest


@dataclass
class ScanParams:
    n_views: int = 180
    mm_per_px: float = 0.0288
    axis_column: float = 0.0
    axis_tilt_rad: float = 0.0
    eccentricity_mm: float = None


class ScanController:
    def __init__(self, camera, stage):
        self.camera = camera
        self.stage = stage

    def run(self, out_dir, params):
        os.makedirs(os.path.join(out_dir, "frames"), exist_ok=True)
        inc = 360.0 / params.n_views
        angles, files = [], []
        h = w = 0
        with self.camera:
            for i in range(params.n_views):
                if i > 0:
                    self.stage.move_deg(inc)
                frame = self.camera.grab()
                h, w = frame.shape[:2]
                fname = f"{i:04d}.png"
                cv2.imwrite(os.path.join(out_dir, "frames", fname), frame)
                files.append(f"frames/{fname}")
                angles.append(round(i * inc, 6))
        ScanManifest(
            angles_deg=angles, mm_per_px=params.mm_per_px,
            axis_column=params.axis_column, axis_tilt_rad=params.axis_tilt_rad,
            eccentricity_mm=params.eccentricity_mm,
            image_width=w, image_height=h, frame_files=files,
            metadata={"source": "ScanController"},
        ).save(os.path.join(out_dir, "manifest.json"))
        return out_dir
