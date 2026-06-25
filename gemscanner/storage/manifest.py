# gemscanner/storage/manifest.py
from dataclasses import dataclass, field, asdict
import json


@dataclass
class ScanManifest:
    angles_deg: list
    mm_per_px: float
    axis_column: float
    axis_tilt_rad: float = 0.0
    eccentricity_mm: float = None
    image_width: int = 0
    image_height: int = 0
    frame_files: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
