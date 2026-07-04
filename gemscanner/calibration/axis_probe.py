import numpy as np
from gemscanner.vision.silhouette import extract_silhouette
from gemscanner.calibration.fit import fit_rotation_axis


def probe_axis(camera, stage, n_probe=12, threshold=None, holder_mask_rows=0,
               progress=None, cancel=None):
    """Rotate one revolution, fit the rotation-axis column from silhouette centroids.

    Returns (axis_column, amplitude). Raises ValueError with < 3 usable silhouettes.
    """
    inc = 360.0 / n_probe
    angles, cols = [], []
    cancelled = False
    with camera:
        for k in range(n_probe):
            if cancel is not None and cancel():
                cancelled = True
                break
            if k:
                stage.move_deg(inc)
            mask = extract_silhouette(camera.grab(), threshold, holder_mask_rows)
            xs = np.where(mask)[1]
            if xs.size:
                cols.append(float(xs.mean()))
                angles.append(k * inc)
            if progress is not None:
                progress(k + 1, n_probe)
        if not cancelled:
            stage.move_deg(inc)   # complete the revolution back to start
    if len(cols) < 3:
        raise ValueError("not enough silhouettes to fit axis (need >= 3)")
    return fit_rotation_axis(angles, cols)
