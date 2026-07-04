import os
from gemscanner.camera.factory import create_camera
from gemscanner.motion.transport import SerialTransport
from gemscanner.motion.stage import RotaryStage
from gemscanner.acquisition.scan_controller import ScanController
from gemscanner.acquisition.prescan import prescan_fov_check
from gemscanner.calibration.axis_probe import probe_axis
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.reconstruction.base import ReconstructionParams
from gemscanner.smoothing import smooth_mesh
from gemscanner.storage.mesh_io import export_mesh
from gemscanner.gui.analysis import analyze_frame


class ScanSession:
    """Owns one camera + one stage and exposes the operations the GUI drives.

    Qt-free so it can be unit-tested headless with SceneCamera + FakeFirmware.
    """

    def __init__(self, config, camera=None, stage=None):
        self.config = config
        self.camera = camera if camera is not None else create_camera(config)
        self.stage = stage if stage is not None else RotaryStage(
            SerialTransport(config.serial_port, config.serial_baud))

    def configure_stage(self, steps_per_rev, settle_ms=150):
        self.stage.set_resolution(steps_per_rev)
        self.stage.set_settle(settle_ms)

    def set_exposure(self, us):
        self.camera.set_exposure(us)

    def grab(self):
        with self.camera:
            return self.camera.grab()

    def analyze(self, frame, threshold=None, holder_mask_rows=0):
        return analyze_frame(frame, threshold, holder_mask_rows)

    def calibrate_axis(self, n_probe=12, threshold=None, holder_mask_rows=0,
                       progress=None, cancel=None):
        return probe_axis(self.camera, self.stage, n_probe=n_probe,
                          threshold=threshold, holder_mask_rows=holder_mask_rows,
                          progress=progress, cancel=cancel)

    def prescan(self, axis_column, mm_per_px, holder_mask_rows=0, n_probe=12):
        return prescan_fov_check(self.camera, self.stage, axis_column, mm_per_px,
                                 n_probe=n_probe, holder_mask_rows=holder_mask_rows)

    def scan(self, out_dir, params, progress=None, cancel=None):
        return ScanController(self.camera, self.stage).run(
            out_dir, params, progress=progress, cancel=cancel)

    def reconstruct(self, out_dir, holder_mask_rows=0, smooth=0):
        mesh = reconstruct_dataset(
            out_dir, ReconstructionParams(holder_mask_rows=holder_mask_rows))
        mesh = smooth_mesh(mesh, smooth)
        export_mesh(mesh, os.path.join(out_dir, "gem.stl"))
        return mesh, bool(mesh.is_watertight), tuple(mesh.bounding_box.extents)
