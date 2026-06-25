# tests/storage/test_dataset.py
from gemscanner.synthetic.generator import generate_ellipsoid_scan
from gemscanner.storage.dataset import load_dataset

def test_load_and_iterate(tmp_path):
    out = generate_ellipsoid_scan(str(tmp_path / "scan"), rx=4, ry=3, rz=5,
                                  n_views=6, mm_per_px=0.05, width=200, height=200)
    ds = load_dataset(out)
    assert ds.frame_count() == 6
    frames = list(ds.iter_frames())
    assert len(frames) == 6
    angle, img = frames[0]
    assert angle == 0.0
    assert img.shape == (200, 200)
