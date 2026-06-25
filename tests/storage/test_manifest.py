# tests/storage/test_manifest.py
from gemscanner.storage.manifest import ScanManifest

def test_manifest_roundtrip(tmp_path):
    m = ScanManifest(
        angles_deg=[0.0, 2.0, 4.0], mm_per_px=0.05, axis_column=199.5,
        image_width=400, image_height=400, frame_files=["frames/0000.png"],
        metadata={"shape": "ellipsoid"},
    )
    p = tmp_path / "manifest.json"
    m.save(p)
    loaded = ScanManifest.load(p)
    assert loaded.angles_deg == [0.0, 2.0, 4.0]
    assert loaded.mm_per_px == 0.05
    assert loaded.metadata["shape"] == "ellipsoid"
    assert loaded.axis_tilt_rad == 0.0
