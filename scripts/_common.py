"""Shared helpers for the bench scripts.

Run scripts as ``python scripts\\<name>.py`` (the scripts dir lands on sys.path[0],
so this sibling import works). All scripts read the same YAML config and the
incrementally-built calibration.json.
"""
import json
import os

from gemscanner.config import ScannerConfig
from gemscanner.camera.factory import create_camera
from gemscanner.motion.transport import SerialTransport
from gemscanner.motion.stage import RotaryStage

DEFAULT_CONFIG = "config.example.yaml"


def load_config(path=DEFAULT_CONFIG):
    return ScannerConfig.load(path)


def build_camera(cfg):
    return create_camera(cfg)


def build_stage(cfg):
    return RotaryStage(SerialTransport(cfg.serial_port, cfg.serial_baud))


def _blank_cal():
    return {"mm_per_px": 0.0, "axis_column": 0.0, "axis_tilt_rad": 0.0,
            "steps_per_rev": 0, "eccentricity_mm": None}


def load_cal(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return _blank_cal()


def save_cal(cal, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2)
    print(f"wrote {path}: {cal}")


def resolve_res(args, cal):
    """steps_per_rev from --res, else calibration.json."""
    res = getattr(args, "res", None) or int(cal.get("steps_per_rev") or 0)
    return res
