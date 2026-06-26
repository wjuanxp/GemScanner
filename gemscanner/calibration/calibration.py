from dataclasses import dataclass, asdict
import json


@dataclass
class Calibration:
    mm_per_px: float
    axis_column: float
    axis_tilt_rad: float = 0.0
    steps_per_rev: int = 0
    eccentricity_mm: float = None

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(**json.load(f))
