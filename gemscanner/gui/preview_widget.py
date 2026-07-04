import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSlider, QHBoxLayout


class LivePreviewWidget(QWidget):
    """Live camera frame with silhouette tint, a draggable holder-mask line,
    a FoV state chip, and min/max/mean stats."""

    maskChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QLabel(alignment=Qt.AlignCenter)
        self._image.setMinimumSize(320, 240)
        self._image.setObjectName("previewImage")
        self._stats = QLabel("—", objectName="statsLabel")
        self._fov = QLabel("no frame", objectName="fovChip")
        self._slider = QSlider(Qt.Vertical)
        self._slider.setRange(0, 100)
        self._slider.valueChanged.connect(self._on_slider)

        row = QHBoxLayout()
        row.addWidget(self._image, 1)
        row.addWidget(self._slider)
        top = QVBoxLayout(self)
        top.addLayout(row, 1)
        info = QHBoxLayout()
        info.addWidget(self._fov)
        info.addWidget(self._stats, 1)
        top.addLayout(info)

        self._img_h = 100
        self._holder = 0

    def holder_mask_rows(self):
        return int(self._holder)

    def set_holder_mask_rows(self, rows):
        self._holder = int(rows)
        self._slider.blockSignals(True)
        self._slider.setValue(int(rows))
        self._slider.blockSignals(False)

    def _on_slider(self, value):
        self._holder = int(value)
        self.maskChanged.emit(self._holder)

    def set_frame(self, frame, analysis):
        gray = frame if frame.ndim == 2 else frame[..., 0]
        h, w = gray.shape
        self._img_h = h
        self._slider.setRange(0, h)
        rgb = np.stack([gray, gray, gray], axis=-1).copy()
        if analysis.mask is not None:
            rgb[analysis.mask, 0] = 220           # red tint on silhouette
            rgb[analysis.mask, 1] = 40
            rgb[analysis.mask, 2] = 40
        if self._holder > 0:
            rgb[h - self._holder:, :, :] = (rgb[h - self._holder:, :, :] * 0.35).astype(np.uint8)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self._image.setPixmap(QPixmap.fromImage(qimg).scaled(
            self._image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        ok = analysis.bbox is not None and not analysis.touches_border
        self._fov.setText("ready" if ok else ("clips border" if analysis.touches_border else "no gem"))
        self._fov.setProperty("state", "ok" if ok else "warn")
        self._fov.style().unpolish(self._fov)
        self._fov.style().polish(self._fov)
        self._stats.setText(
            f"min {analysis.min}  max {analysis.max}  mean {analysis.mean:.1f}")
