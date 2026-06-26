import os
from gemscanner.config import ScannerConfig
from gemscanner.camera.factory import create_camera
from gemscanner.motion.transport import SerialTransport
from gemscanner.motion.stage import RotaryStage
from gemscanner.calibration.calibration import Calibration
from gemscanner.acquisition.scan_controller import ScanController, ScanParams
from gemscanner.acquisition.prescan import prescan_fov_check
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def run_scan_from_config(config_path, out_dir):
    cfg = ScannerConfig.load(config_path)
    cal = Calibration.load(cfg.calibration_path)
    cam = create_camera(cfg)
    stage = RotaryStage(SerialTransport(cfg.serial_port, cfg.serial_baud))
    stage.set_resolution(cal.steps_per_rev)
    stage.set_settle(cfg.scan.get("settle_ms", 150))

    pre = prescan_fov_check(cam, stage, cal.axis_column, cal.mm_per_px)
    if not pre.ok:
        print(f"FoV check FAILED: silhouette clips at {pre.offending_angle}°; re-seat the gem.")
        return 2
    print(f"FoV ok; eccentricity ~ {pre.eccentricity_mm:.3f} mm")

    params = ScanParams(n_views=cfg.scan.get("n_views", 180),
                        mm_per_px=cal.mm_per_px, axis_column=cal.axis_column,
                        axis_tilt_rad=cal.axis_tilt_rad,
                        eccentricity_mm=pre.eccentricity_mm)
    ScanController(cam, stage).run(out_dir, params)
    mesh = reconstruct_dataset(out_dir)
    out_mesh = os.path.join(out_dir, "gem.stl")
    export_mesh(mesh, out_mesh)
    print(f"wrote {out_mesh}: watertight={mesh.is_watertight}, extents={mesh.bounding_box.extents}")
    return 0
