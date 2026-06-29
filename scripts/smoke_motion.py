"""Verify the rotary stage end-to-end: SETRES, step, reverse, home."""
import argparse

import _common as C


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("--res", type=int, default=None,
                   help="steps per rev (default: from calibration.json)")
    p.add_argument("--steps", type=int, default=None,
                   help="microsteps to move (default res/4 = 90 deg)")
    p.add_argument("--speed", type=int, default=400)
    p.add_argument("--accel", type=int, default=1000)
    a = p.parse_args()

    cfg = C.load_config(a.config)
    cal = C.load_cal(cfg.calibration_path)
    res = C.resolve_res(a, cal)
    if res <= 0:
        p.error("no steps_per_rev: pass --res or run calibrate_steps.py first")
    steps = a.steps if a.steps is not None else res // 4

    stage = C.build_stage(cfg)
    stage.set_resolution(res)
    stage.set_speed(a.speed)
    stage.set_accel(a.accel)
    print("status:", stage.status())
    print(f"stepping +{steps} ..."); stage.step(steps); print("  ", stage.status())
    print(f"reverse -{steps} ..."); stage.step(-steps); print("  ", stage.status())
    print("home ..."); stage.home(); print("  ", stage.status())
    print("OK - watch that the stage physically turned and reversed smoothly.")


if __name__ == "__main__":
    main()
