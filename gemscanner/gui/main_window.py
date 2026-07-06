import os
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QMessageBox
from gemscanner.acquisition.scan_controller import ScanParams
from gemscanner.gui.preview_widget import LivePreviewWidget
from gemscanner.gui.queue_panel import QueuePanel
from gemscanner.gui.wizard_panel import WizardPanel
from gemscanner.gui.controls_panel import ControlsPanel
from gemscanner.gui.reconstruction_panel import ReconstructionPanel
from gemscanner.gui.worker import HardwareWorker


class MainWindow(QMainWindow):
    def __init__(self, project, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GemScanner")
        self.project = project
        self.session = session
        self.worker = HardwareWorker(session)

        self.preview = LivePreviewWidget()
        self.queue = QueuePanel()
        self.wizard = WizardPanel()
        self.controls = ControlsPanel()
        self.reconstruction = ReconstructionPanel()
        self.queue.set_gems(project.gems)

        cam_cfg = project.camera or {}
        self._default_exposure = float(cam_cfg.get("exposure_us", ControlsPanel.EXPOSURE_MIN))
        self._default_gain = float(cam_cfg.get("gain", ControlsPanel.GAIN_MIN))

        central = QWidget()
        root = QHBoxLayout(central)
        left = QVBoxLayout()
        left.addWidget(self.wizard)
        left.addWidget(self.controls)
        left.addWidget(self.reconstruction)
        left.addWidget(self.queue, 1)
        root.addLayout(left, 0)
        root.addWidget(self.preview, 1)
        self.setCentralWidget(central)

        # wiring
        self.preview.maskChanged.connect(self._on_mask_changed)
        self.queue.gemSelected.connect(self._on_gem_selected)
        self.wizard.calibrateRequested.connect(self._start_calibrate)
        self.wizard.scanRequested.connect(self._start_scan)
        self.wizard.reconstructRequested.connect(self._start_reconstruct)
        self.wizard.mountConfirmed.connect(lambda: self.wizard.set_step(1))
        self.wizard.nextGemRequested.connect(self._on_next_gem)
        self.wizard.cancelRequested.connect(self.worker.cancel)
        self.controls.exposureChanged.connect(self._on_exposure_changed)
        self.controls.gainChanged.connect(self._on_gain_changed)
        self.worker.frameReady.connect(self.preview.set_frame)
        self.worker.progress.connect(self._on_progress)
        self.worker.result.connect(self._on_result)
        self.worker.failed.connect(self._on_failed)

        self._current = 0
        if project.gems:
            self.queue.select(0)
        self.worker.start()
        self.worker.set_view(None, self.preview.holder_mask_rows())
        self.worker.set_exposure(self._default_exposure)
        self.worker.set_gain(self._default_gain)
        self.worker.start_preview()

    # ---- slots ----
    def _current_gem(self):
        gems = self.project.gems
        return gems[self._current] if gems else None

    def _on_mask_changed(self, rows):
        self.worker.set_view(None, rows)
        gem = self._current_gem()
        if gem is not None:
            gem.holder_mask_rows = rows
        if self.wizard.step() == 1:
            self.wizard.set_step(2)

    def _start_calibrate(self):
        self.wizard.set_step(3)
        self.worker.post("calibrate", n_probe=12)

    def _on_next_gem(self):
        nxt = self._current + 1
        if nxt < len(self.project.gems):
            self.queue.select(nxt)           # drives _on_gem_selected
            self.wizard.set_step(0)          # back to Mount for the next gem

    def _on_gem_selected(self, index):
        self._current = index
        gem = self._current_gem()
        if gem is not None:
            self.preview.set_holder_mask_rows(gem.holder_mask_rows)
            self.worker.set_view(None, gem.holder_mask_rows)
            exposure = gem.exposure_us if gem.exposure_us is not None else self._default_exposure
            gain = gem.gain if gem.gain is not None else self._default_gain
            self.controls.set_values(exposure, gain)
            self.worker.set_exposure(exposure)
            self.worker.set_gain(gain)

    def _on_exposure_changed(self, us):
        self.worker.set_exposure(us)
        gem = self._current_gem()
        if gem is not None:
            gem.exposure_us = us

    def _on_gain_changed(self, gain):
        self.worker.set_gain(gain)
        gem = self._current_gem()
        if gem is not None:
            gem.gain = gain

    def _start_scan(self):
        gem = self._current_gem()
        if gem is None:
            return
        params = ScanParams(n_views=180, mm_per_px=self.project.mm_per_px,
                            axis_column=gem.axis_column)
        out = gem.out or os.path.join("scans", gem.name)
        self.worker.post("scan", out_dir=out, params=params)

    def _start_reconstruct(self):
        gem = self._current_gem()
        if gem is None:
            return
        out = gem.out or os.path.join("scans", gem.name)
        self.worker.post("reconstruct", out_dir=out,
                         holder_mask_rows=gem.holder_mask_rows,
                         **self.reconstruction.selected_kwargs())

    def _on_progress(self, op, done, total):
        self.wizard.progress.setValue(int(done * 100 / max(total, 1)))

    def _on_result(self, op, payload):
        gem = self._current_gem()
        if op == "calibrate" and gem is not None:
            gem.axis_column = payload[0]
        elif op == "reconstruct":
            watertight, extents = payload
            QMessageBox.information(self, "Reconstruct",
                                    f"watertight={watertight}\nextents={extents}")
        if op == "calibrate":
            self.wizard.set_step(4)          # -> Scan
        elif op == "scan":
            self.wizard.set_step(5)          # -> Reconstruct
        elif op == "reconstruct":
            self.wizard.set_step(6)          # -> Next gem
        self.worker.set_view(None, self.preview.holder_mask_rows())
        self.worker.start_preview()

    def _on_failed(self, op, message):
        QMessageBox.warning(self, f"{op} failed", message)
        self.worker.start_preview()

    def closeEvent(self, event):
        self.worker.shutdown()
        self.worker.wait(3000)
        super().closeEvent(event)
