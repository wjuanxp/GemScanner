from gemscanner.config import ScannerConfig
from gemscanner.camera.factory import create_camera
from gemscanner.camera.mock import MockCamera


def test_factory_mock():
    cam = create_camera(ScannerConfig(camera_backend="mock",
                                      camera={"frames": []}))
    assert isinstance(cam, MockCamera)


def test_factory_opencv_type_without_opening():
    cam = create_camera(ScannerConfig(camera_backend="opencv",
                                      camera={"index": 0}))
    assert cam.__class__.__name__ == "OpenCvCamera"   # not opened, no device needed
