import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gemscanner.gui.analysis import analyze_frame
from gemscanner.gui.preview_widget import LivePreviewWidget


def test_preview_widget_accepts_frame_and_mask(qtbot):
    w = LivePreviewWidget()
    qtbot.addWidget(w)
    img = np.full((100, 100), 255, np.uint8)
    img[30:70, 40:60] = 0
    w.set_frame(img, analyze_frame(img))          # must not raise

    w.set_holder_mask_rows(25)
    assert w.holder_mask_rows() == 25

    received = []
    w.maskChanged.connect(received.append)
    w.set_holder_mask_rows(40)
    w.maskChanged.emit(w.holder_mask_rows())       # simulate drag commit
    assert received[-1] == 40
