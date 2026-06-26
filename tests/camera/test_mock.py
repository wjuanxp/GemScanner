import numpy as np
from gemscanner.camera.mock import MockCamera


def test_returns_frames_in_order():
    f0 = np.zeros((4, 4), np.uint8)
    f1 = np.ones((4, 4), np.uint8)
    cam = MockCamera(frames=[f0, f1])
    cam.open()
    assert np.array_equal(cam.grab(), f0)
    assert np.array_equal(cam.grab(), f1)
    cam.close()


def test_frame_provider_called():
    calls = {"n": 0}

    def provider():
        calls["n"] += 1
        return np.full((2, 2), calls["n"], np.uint8)

    cam = MockCamera(frame_provider=provider)
    assert cam.grab()[0, 0] == 1
    assert cam.grab()[0, 0] == 2


def test_context_manager():
    with MockCamera(frames=[np.zeros((2, 2), np.uint8)]) as cam:
        assert cam.grab().shape == (2, 2)
