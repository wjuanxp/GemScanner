"""Fit the rotation-axis column from silhouette centroids over a revolution.

Rotates the stage through n_probe equal steps, extracts the silhouette centroid
column at each, and least-squares fits u(theta) = c + a*cos + b*sin -> axis_column.
Needs steps_per_rev (run calibrate_steps.py first).
"""
import argparse

import numpy as np

import _common as C
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.calibration.fit import fit_rotation_axis


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("--res", type=int, default=None,
                   help="steps per rev (default: from calibration.json)")
    p.add_argument("-n", "--n-probe", type=int, default=12)
    p.add_argument("--threshold", type=int, default=None,
                   help="fixed silhouette threshold (default: Otsu)")
    p.add_argument("--write", action="store_true",
                   help="write axis_column into calibration.json")
    a = p.parse_args()

    cfg = C.load_config(a.config)
    cal = C.load_cal(cfg.calibration_path)
    res = C.resolve_res(a, cal)
    if res <= 0:
        p.error("no steps_per_rev: pass --res or run calibrate_steps.py first")

    cam = C.build_camera(cfg)
    stage = C.build_stage(cfg)
    stage.set_resolution(res)
    inc = 360.0 / a.n_probe
    angles, cols = [], []
    with cam:
        for k in range(a.n_probe):
            if k:
                stage.move_deg(inc)
            mask = extract_silhouette(cam.grab(), a.threshold)
            ys, xs = np.where(mask)
            if xs.size == 0:
                print(f"  angle {k * inc:6.1f}: empty silhouette, skipped")
                continue
            cols.append(float(xs.mean()))
            angles.append(k * inc)
            print(f"  angle {k * inc:6.1f}: centroid col {xs.mean():8.2f}")
        stage.move_deg(inc)  # complete the revolution back to start

    if len(cols) < 3:
        p.error("not enough silhouettes to fit (need >= 3)")
    axis, amp = fit_rotation_axis(angles, cols)
    print(f"axis_column = {axis:.2f}   (centroid swing amplitude {amp:.2f} px)")
    if a.write:
        cal["axis_column"] = axis
        C.save_cal(cal, cfg.calibration_path)


if __name__ == "__main__":
    main()
