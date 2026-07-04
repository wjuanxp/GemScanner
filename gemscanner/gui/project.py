from dataclasses import dataclass, field, asdict
import yaml
from gemscanner.config import ScannerConfig


@dataclass
class GemJob:
    name: str
    holder_mask_rows: int = 0
    axis_column: float = 0.0
    exposure_us: float | None = None
    gain: float | None = None
    out: str = ""


@dataclass
class Project:
    camera_backend: str = "mock"
    camera: dict = field(default_factory=dict)
    serial_port: str = "COM3"
    serial_baud: int = 115200
    mm_per_px: float = 0.0
    steps_per_rev: int = 0
    gems: list = field(default_factory=list)
    calibration_path: str = "calibration.json"

    def save(self, path):
        data = asdict(self)  # dataclass GemJob -> dict recursively
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        gems = [GemJob(**g) for g in data.pop("gems", [])]
        return cls(gems=gems, **data)

    def to_scanner_config(self, gem: GemJob) -> ScannerConfig:
        camera = dict(self.camera)
        if gem.exposure_us is not None:
            camera["exposure_us"] = gem.exposure_us
        if gem.gain is not None:
            camera["gain"] = gem.gain
        return ScannerConfig(
            camera_backend=self.camera_backend,
            camera=camera,
            serial_port=self.serial_port,
            serial_baud=self.serial_baud,
            scan={"n_views": 180, "settle_ms": 150,
                  "holder_mask_rows": gem.holder_mask_rows},
            calibration_path=self.calibration_path,
        )
