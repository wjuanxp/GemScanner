import numpy as np
from gemscanner.camera.base import CameraBackend


class GenTLCamera(CameraBackend):
    """GenICam/GenTL camera via Harvesters and a vendor .cti producer.

    Works with legacy Baumer GigE cameras (e.g. EXG50) through Baumer's
    ``bgapi2_gige.cti`` producer, which neoAPI does not support. Node names
    differ across camera generations, so feature writes try modern SFNC names
    first and fall back to the legacy names (``ExposureTimeAbs``/``GainAbs``/
    ``TestImageSelector``).
    """

    # (modern, legacy) candidate node names
    _EXPOSURE = ("ExposureTime", "ExposureTimeAbs")
    _GAIN = ("Gain", "GainAbs", "GainRaw")
    _TESTIMAGE = ("TestPattern", "TestImageSelector")

    def __init__(self, cti_path, index=0, serial=None, exposure_us=None,
                 gain=None, pixel_format="Mono8", fetch_timeout=5.0):
        self.cti_path = cti_path
        self.index = index
        self.serial = serial
        self.exposure_us = exposure_us
        self.gain = gain
        self.pixel_format = pixel_format
        self.fetch_timeout = fetch_timeout
        self._h = None
        self._ia = None

    def _node_map(self):
        return self._ia.remote_device.node_map

    def _set_first(self, names, value):
        nm = self._node_map()
        for n in names:
            try:
                getattr(nm, n).value = value
                return n
            except Exception:
                continue
        return None

    def open(self):
        from harvesters.core import Harvester
        self._h = Harvester()
        self._h.add_file(self.cti_path)
        self._h.update()
        if not self._h.device_info_list:
            raise RuntimeError(f"no GenTL devices found via {self.cti_path!r}")
        if self.serial is not None:
            self._ia = self._h.create({"serial_number": str(self.serial)})
        else:
            self._ia = self._h.create(self.index)
        self._set_first(self._TESTIMAGE, "Off")
        if self.pixel_format:
            self._set_first(["PixelFormat"], self.pixel_format)
        if self.exposure_us is not None:
            self.set_exposure(self.exposure_us)
        if self.gain is not None:
            self._set_first(self._GAIN, float(self.gain))
        self._ia.start()

    def set_exposure(self, us):
        if self._ia is not None:
            self._set_first(self._EXPOSURE, float(us))

    def grab(self):
        with self._ia.fetch(timeout=self.fetch_timeout) as buffer:
            comp = buffer.payload.components[0]
            arr = comp.data.reshape(comp.height, comp.width).copy()
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)
        if arr.max() == 0:
            raise RuntimeError("grabbed an all-zero (black) frame")
        return np.ascontiguousarray(arr)

    def close(self):
        if self._ia is not None:
            try:
                self._ia.stop()
            except Exception:
                pass
            self._ia.destroy()
            self._ia = None
        if self._h is not None:
            self._h.reset()
            self._h = None
