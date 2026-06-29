"""Grab one frame from the configured camera and save it (camera bring-up)."""
import argparse

import cv2

import _common as C


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=C.DEFAULT_CONFIG)
    p.add_argument("-e", "--exposure-us", type=float, default=None,
                   help="override exposure for this grab")
    p.add_argument("-o", "--out", default="grab.png")
    a = p.parse_args()

    cfg = C.load_config(a.config)
    if a.exposure_us is not None:
        cfg.camera["exposure_us"] = a.exposure_us
    cam = C.build_camera(cfg)
    with cam:
        if a.exposure_us is not None:
            cam.set_exposure(a.exposure_us)
        f = cam.grab()
    cv2.imwrite(a.out, f)
    print(f"{a.out}: shape={f.shape} dtype={f.dtype} "
          f"min={int(f.min())} max={int(f.max())} mean={f.mean():.1f}")


if __name__ == "__main__":
    main()
