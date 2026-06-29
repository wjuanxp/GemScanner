"""Compute mm_per_px from a gauge of known length, optionally save to calibration.json."""
import argparse

import _common as C
from gemscanner.calibration.fit import mm_per_px_from_gauge


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--px", type=float, required=True, help="measured length in pixels")
    p.add_argument("--mm", type=float, required=True, help="known length in millimetres")
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("--write", action="store_true",
                   help="write mm_per_px into calibration.json")
    a = p.parse_args()

    mmpp = mm_per_px_from_gauge(a.px, a.mm)
    print(f"mm_per_px = {mmpp:.6f}   ({a.mm} mm / {a.px} px)")
    if a.write:
        cfg = C.load_config(a.config)
        cal = C.load_cal(cfg.calibration_path)
        cal["mm_per_px"] = mmpp
        C.save_cal(cal, cfg.calibration_path)


if __name__ == "__main__":
    main()
