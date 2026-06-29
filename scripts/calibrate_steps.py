"""Set steps_per_rev in calibration.json - directly, empirically, or computed.

Empirical (most reliable): command a known microstep count, measure the actual
degrees turned against an index mark, pass both.
"""
import argparse

import _common as C
from gemscanner.calibration.fit import steps_per_rev_from


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--value", type=int, help="steps_per_rev directly")
    g.add_argument("--empirical", nargs=2, type=float, metavar=("STEPS", "DEGREES"),
                   help="commanded microsteps and measured degrees turned")
    g.add_argument("--compute", nargs=3, type=float, metavar=("MOTORSTEPS", "MICROSTEP", "GEAR"),
                   help="motor full-steps/rev, microstep factor, gear ratio")
    a = p.parse_args()

    if a.value is not None:
        spr = int(a.value)
    elif a.empirical is not None:
        steps, deg = a.empirical
        if deg == 0:
            p.error("measured degrees must be non-zero")
        spr = int(round(steps * 360.0 / deg))
    else:
        spr = steps_per_rev_from(*a.compute)

    print(f"steps_per_rev = {spr}")
    cfg = C.load_config(a.config)
    cal = C.load_cal(cfg.calibration_path)
    cal["steps_per_rev"] = spr
    C.save_cal(cal, cfg.calibration_path)


if __name__ == "__main__":
    main()
