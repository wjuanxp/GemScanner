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


def test_factory_gentl_type_without_opening():
    cam = create_camera(ScannerConfig(
        camera_backend="gentl",
        camera={"cti_path": r"C:\x\bgapi2_gige.cti", "exposure_us": 60000}))
    assert cam.__class__.__name__ == "GenTLCamera"   # harvesters imported lazily in open()
