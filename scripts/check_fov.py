"""Pre-scan FoV / eccentricity check over a full revolution.

Aborts (naming the clipping angle) if the silhouette reaches a frame border at
any rotation. Needs axis_column + mm_per_px + steps_per_rev in calibration.json.
"""
import argparse

import _common as C
from gemscanner.acquisition.prescan import prescan_fov_check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("--res", type=int, default=None,
                   help="steps per rev (default: from calibration.json)")
    p.add_argument("-n", "--n-probe", type=int, default=12)
    p.add_argument("--threshold", type=int, default=None)
    p.add_argument("--holder-mask-rows", type=int, default=None,
                   help="mask this many bottom rows (pedestal+stage); "
                        "default: config scan.holder_mask_rows")
    a = p.parse_args()

    cfg = C.load_config(a.config)
    cal = C.load_cal(cfg.calibration_path)
    res = C.resolve_res(a, cal)
    if res <= 0:
        p.error("no steps_per_rev: pass --res or run calibrate_steps.py first")
    holder = C.resolve_holder(a, cfg)
    if not cal.get("axis_column") or not cal.get("mm_per_px"):
        p.error("calibration.json needs axis_column and mm_per_px "
                "(run calibrate_axis.py / calibrate_scale.py first)")

    cam = C.build_camera(cfg)
    stage = C.build_stage(cfg)
    stage.set_resolution(res)
    result = prescan_fov_check(cam, stage, cal["axis_column"], cal["mm_per_px"],
                               n_probe=a.n_probe, threshold=a.threshold,
                               holder_mask_rows=holder)
    print(result)
    if result.ok:
        print(f"OK - eccentricity ~ {result.eccentricity_mm:.3f} mm")
    else:
        print(f"CLIPS at {result.offending_angle} deg - re-seat / re-center the gem")


if __name__ == "__main__":
    main()
