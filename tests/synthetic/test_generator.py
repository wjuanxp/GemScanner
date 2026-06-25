# tests/synthetic/test_generator.py
import os
import numpy as np
import cv2
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.manifest import ScanManifest

def test_generates_frames_and_manifest(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=18, mm_per_px=0.05, width=400, height=400)
    m = ScanManifest.load(os.path.join(out, "manifest.json"))
    assert len(m.frame_files) == 18
    assert m.metadata["rx"] == 4
    img = cv2.imread(os.path.join(out, m.frame_files[0]), cv2.IMREAD_GRAYSCALE)
    assert img.shape == (400, 400)
    # silhouette is dark on bright background: both extremes present
    assert img.min() == 0 and img.max() == 255

def test_widest_view_matches_major_axis(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=5, ry=2, rz=5,
                                  n_views=4, mm_per_px=0.05, width=400, height=400)
    m = ScanManifest.load(os.path.join(out, "manifest.json"))
    img = cv2.imread(os.path.join(out, m.frame_files[0]), cv2.IMREAD_GRAYSCALE)  # theta=0
    dark_cols = np.where((img == 0).any(axis=0))[0]
    width_px = dark_cols[-1] - dark_cols[0] + 1
    # theta=0 view shows full 2*rx width => 2*5 / 0.05 = 200 px (within rounding)
    assert abs(width_px - 200) <= 2
