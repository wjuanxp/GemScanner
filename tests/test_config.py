from gemscanner.config import ScannerConfig, default_config


def test_roundtrip(tmp_path):
    c = default_config()
    c.serial_port = "COM7"
    c.scan["n_views"] = 360
    p = tmp_path / "cfg.yaml"
    c.save(p)
    loaded = ScannerConfig.load(p)
    assert loaded.serial_port == "COM7"
    assert loaded.scan["n_views"] == 360
    assert loaded.camera_backend == "mock"


def test_defaults():
    c = default_config()
    assert c.serial_baud == 115200
    assert c.camera_backend in ("mock", "opencv", "baumer")
