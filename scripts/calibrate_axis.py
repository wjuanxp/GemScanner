"""Fit the rotation-axis column from silhouette centroids over a revolution.

Rotates the stage through n_probe equal steps, extracts the silhouette centroid
column at each, and least-squares fits u(theta) = c + a*cos + b*sin -> axis_column.
Needs steps_per_rev (run calibrate_steps.py first).
"""
import argparse

import _common as C


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("--res", type=int, default=None,
                   help="steps per rev (default: from calibration.json)")
    p.add_argument("-n", "--n-probe", type=int, default=12)
    p.add_argument("--threshold", type=int, default=None,
                   help="fixed silhouette threshold (default: Otsu)")
    p.add_argument("--holder-mask-rows", type=int, default=None,
                   help="mask this many bottom rows (pedestal+stage); "
                        "default: config scan.holder_mask_rows")
    p.add_argument("--write", action="store_true",
                   help="write axis_column into calibration.json")
    a = p.parse_args()

    cfg = C.load_config(a.config)
    cal = C.load_cal(cfg.calibration_path)
    res = C.resolve_res(a, cal)
    if res <= 0:
        p.error("no steps_per_rev: pass --res or run calibrate_steps.py first")
    holder = C.resolve_holder(a, cfg)

    cam = C.build_camera(cfg)
    stage = C.build_stage(cfg)
    stage.set_resolution(res)
    from gemscanner.calibration.axis_probe import probe_axis

    def _progress(done, total):
        print(f"  probe {done}/{total}")

    axis, amp = probe_axis(cam, stage, n_probe=a.n_probe, threshold=a.threshold,
                           holder_mask_rows=holder, progress=_progress)
    print(f"axis_column = {axis:.2f}   (centroid swing amplitude {amp:.2f} px)")
    if a.write:
        cal["axis_column"] = axis
        C.save_cal(cal, cfg.calibration_path)


if __name__ == "__main__":
    main()
