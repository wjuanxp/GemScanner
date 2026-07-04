import os
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from gemscanner.gui.analysis import analyze_frame
from gemscanner.gui.preview_widget import LivePreviewWidget
from gemscanner.gui.project import GemJob
from gemscanner.gui.queue_panel import QueuePanel
from gemscanner.gui.wizard_panel import WizardPanel


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


def test_queue_panel_add_and_select(qtbot):
    q = QueuePanel()
    qtbot.addWidget(q)
    q.set_gems([GemJob(name="ruby-01"), GemJob(name="emerald-02")])
    assert [g.name for g in q.gems()] == ["ruby-01", "emerald-02"]
    q.add_gem(GemJob(name="sapphire-03"))
    assert len(q.gems()) == 3

    seen = []
    q.gemSelected.connect(seen.append)
    q.select(2)
    assert q.current_index() == 2
    assert seen[-1] == 2


def test_wizard_panel_steps_and_signals(qtbot):
    w = WizardPanel()
    qtbot.addWidget(w)
    w.set_step(3)
    assert w.step() == 3
    fired = []
    w.calibrateRequested.connect(lambda: fired.append("cal"))
    w.calibrateRequested.emit()
    assert fired == ["cal"]
