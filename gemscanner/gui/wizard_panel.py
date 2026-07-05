from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QProgressBar)

STEPS = ["Mount gem", "Align lighting", "Holder mask",
         "Calibrate axis", "Scan", "Reconstruct", "Next gem"]


class WizardPanel(QWidget):
    """The per-gem guided step sequence."""

    mountConfirmed = Signal()
    calibrateRequested = Signal()
    scanRequested = Signal()
    reconstructRequested = Signal()
    nextGemRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self._heading = QLabel(objectName="panelTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        buttons = QHBoxLayout()
        self._btn_mount = QPushButton("Mounted")
        self._btn_cal = QPushButton("Calibrate axis")
        self._btn_scan = QPushButton("Scan")
        self._btn_recon = QPushButton("Reconstruct")
        self._btn_next = QPushButton("Next gem")
        self._btn_cancel = QPushButton("Cancel")
        self._btn_mount.clicked.connect(self.mountConfirmed)
        self._btn_cal.clicked.connect(self.calibrateRequested)
        self._btn_scan.clicked.connect(self.scanRequested)
        self._btn_recon.clicked.connect(self.reconstructRequested)
        self._btn_next.clicked.connect(self.nextGemRequested)
        self._btn_cancel.clicked.connect(self.cancelRequested)
        for b in (self._btn_mount, self._btn_cal, self._btn_scan,
                  self._btn_recon, self._btn_next, self._btn_cancel):
            buttons.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addWidget(self._heading)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        self.set_step(0)

    def step(self):
        return self._step

    def set_step(self, index):
        self._step = int(index)
        self._heading.setText(f"Step {self._step + 1}/{len(STEPS)} — {STEPS[self._step]}")
