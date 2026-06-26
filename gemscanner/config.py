# gemscanner/config.py
from dataclasses import dataclass, field, asdict
import yaml


@dataclass
class ScannerConfig:
    camera_backend: str = "mock"
    camera: dict = field(default_factory=dict)
    serial_port: str = "COM3"
    serial_baud: int = 115200
    scan: dict = field(default_factory=lambda: {"n_views": 180, "settle_ms": 150})
    calibration_path: str = "calibration.json"

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(asdict(self), f, sort_keys=False)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


def default_config():
    return ScannerConfig()
