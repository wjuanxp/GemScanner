import cv2
from gemscanner.camera.base import CameraBackend


class OpenCvCamera(CameraBackend):
    def __init__(self, index=0, exposure=None):
        self.index = index
        self.exposure = exposure
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open camera index {self.index}")
        if self.exposure is not None:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def grab(self):
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("frame grab failed")
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame
