import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from gemscanner.gui.reconstruction_panel import ReconstructionPanel

def _app():
    return QApplication.instance() or QApplication([])

def test_faceted_choice_present_and_maps_to_facet_method():
    _app()
    panel = ReconstructionPanel()
    labels = [c[0] for c in ReconstructionPanel.CHOICES]
    assert "Faceted gem (planar)" in labels
    idx = labels.index("Faceted gem (planar)")
    panel.set_index(idx)
    assert panel.selected_kwargs()["method"] == "facet"
