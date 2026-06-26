from gemscanner.camera.base import CameraBackend


class MockCamera(CameraBackend):
    def __init__(self, frames=None, frame_provider=None):
        self._frames = list(frames) if frames is not None else None
        self._provider = frame_provider
        self._i = 0

    def open(self):
        self._i = 0

    def close(self):
        pass

    def grab(self):
        if self._provider is not None:
            return self._provider()
        frame = self._frames[self._i]
        self._i = min(self._i + 1, len(self._frames) - 1)
        return frame
