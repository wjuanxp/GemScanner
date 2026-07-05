from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider


class ControlsPanel(QWidget):
    """Exposure and gain sliders for live camera tuning."""

    exposureChanged = Signal(float)
    gainChanged = Signal(float)

    # slider integer ranges map 1:1 to device units
    EXPOSURE_MIN, EXPOSURE_MAX = 50, 20000     # microseconds
    GAIN_MIN, GAIN_MAX = 0, 24                  # dB-ish, device dependent

    def __init__(self, parent=None):
        super().__init__(parent)
        self._exp = QSlider(Qt.Horizontal)
        self._exp.setRange(self.EXPOSURE_MIN, self.EXPOSURE_MAX)
        self._exp_val = QLabel(objectName="statsLabel")
        self._gain = QSlider(Qt.Horizontal)
        self._gain.setRange(self.GAIN_MIN, self.GAIN_MAX)
        self._gain_val = QLabel(objectName="statsLabel")
        self._exp.valueChanged.connect(self._on_exposure)
        self._gain.valueChanged.connect(self._on_gain)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Camera", objectName="panelTitle"))
        for label, slider, val in (("Exposure (us)", self._exp, self._exp_val),
                                   ("Gain", self._gain, self._gain_val)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(slider, 1)
            row.addWidget(val)
            layout.addLayout(row)
        self.set_values(self.EXPOSURE_MIN, self.GAIN_MIN)

    def exposure_us(self):
        return float(self._exp.value())

    def gain(self):
        return float(self._gain.value())

    def set_exposure_us(self, us):
        self._exp.blockSignals(True)
        self._exp.setValue(int(us))
        self._exp.blockSignals(False)
        self._exp_val.setText(str(int(us)))

    def set_gain(self, gain):
        self._gain.blockSignals(True)
        self._gain.setValue(int(gain))
        self._gain.blockSignals(False)
        self._gain_val.setText(str(int(gain)))

    def set_values(self, exposure_us, gain):
        self.set_exposure_us(exposure_us)
        self.set_gain(gain)

    def _on_exposure(self, value):
        self._exp_val.setText(str(int(value)))
        self.exposureChanged.emit(float(value))

    def _on_gain(self, value):
        self._gain_val.setText(str(int(value)))
        self.gainChanged.emit(float(value))
