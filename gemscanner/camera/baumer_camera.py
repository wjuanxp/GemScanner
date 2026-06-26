import numpy as np
from gemscanner.camera.base import CameraBackend


class BaumerCamera(CameraBackend):
    def __init__(self, serial=None, exposure_us=None, pixel_format="Mono8"):
        self.serial = serial
        self.exposure_us = exposure_us
        self.pixel_format = pixel_format
        self._cam = None

    def open(self):
        import neoapi
        self._cam = neoapi.Cam()
        self._cam.Connect(self.serial) if self.serial else self._cam.Connect()
        self._cam.f.PixelFormat.SetString(self.pixel_format)
        if self.exposure_us is not None:
            self._cam.f.ExposureTime.Set(float(self.exposure_us))

    def set_exposure(self, us):
        if self._cam is not None:
            self._cam.f.ExposureTime.Set(float(us))

    def close(self):
        if self._cam is not None:
            self._cam.Disconnect()
            self._cam = None

    def grab(self):
        img = self._cam.GetImage()
        arr = img.GetNPArray()
        if arr.ndim == 3:
            arr = arr[..., 0]
        return np.ascontiguousarray(arr, dtype=np.uint8)
