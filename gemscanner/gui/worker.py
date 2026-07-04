import queue
from PySide6.QtCore import QThread, Signal


class HardwareWorker(QThread):
    """The single owner of camera + stage. Polls grab() for live preview and
    runs long ops (calibrate/scan/reconstruct) off the UI thread.

    Preview auto-pauses (camera closed) whenever a queued op runs, so the
    existing `with camera:` blocks inside those ops never overlap the preview.
    """

    frameReady = Signal(object, object)   # frame, FrameAnalysis
    progress = Signal(str, int, int)      # op, done, total
    result = Signal(str, object)          # op, payload
    failed = Signal(str, str)             # op, message

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._cmds = queue.Queue()
        self._preview = False
        self._cam_open = False
        self._cancel = False
        self._running = True
        self._threshold = None
        self._holder = 0

    # ---- called from the UI thread ----
    def set_view(self, threshold, holder_mask_rows):
        self._threshold = threshold
        self._holder = int(holder_mask_rows)

    def start_preview(self):
        self._preview = True

    def stop_preview(self):
        self._preview = False

    def cancel(self):
        self._cancel = True

    def post(self, op, **kwargs):
        self._cmds.put((op, kwargs))

    def shutdown(self):
        self._running = False
        self._cmds.put(("_stop", {}))

    # ---- runs on this thread ----
    def run(self):
        while self._running:
            try:
                op, kwargs = self._cmds.get(timeout=0.03)
            except queue.Empty:
                if self._preview:
                    self._preview_frame()
                continue
            if op == "_stop":
                break
            self._pause_preview()
            self._cancel = False
            handler = getattr(self, f"_op_{op}", None)
            if handler is None:
                self.failed.emit(op, f"unknown op {op!r}")
                continue
            try:
                handler(**kwargs)
            except Exception as exc:                     # surface, don't crash
                self.failed.emit(op, str(exc))
        self._pause_preview()

    def _pause_preview(self):
        self._preview = False
        if self._cam_open:
            try:
                self._session.camera.close()
            finally:
                self._cam_open = False

    def _preview_frame(self):
        try:
            if not self._cam_open:
                self._session.camera.open()
                self._cam_open = True
            frame = self._session.camera.grab()
            analysis = self._session.analyze(frame, self._threshold, self._holder)
            self.frameReady.emit(frame, analysis)
        except Exception as exc:
            self._preview = False
            self.failed.emit("preview", str(exc))

    def _op_calibrate(self, n_probe=12):
        axis, amp = self._session.calibrate_axis(
            n_probe=n_probe, threshold=self._threshold, holder_mask_rows=self._holder,
            progress=lambda d, n: self.progress.emit("calibrate", d, n),
            cancel=lambda: self._cancel)
        self.result.emit("calibrate", (axis, amp))

    def _op_scan(self, out_dir, params):
        self._session.scan(
            out_dir, params,
            progress=lambda d, n: self.progress.emit("scan", d, n),
            cancel=lambda: self._cancel)
        self.result.emit("scan", out_dir)

    def _op_reconstruct(self, out_dir, holder_mask_rows=0, smooth=0):
        _, watertight, extents = self._session.reconstruct(
            out_dir, holder_mask_rows=holder_mask_rows, smooth=smooth)
        self.result.emit("reconstruct", (watertight, extents))
