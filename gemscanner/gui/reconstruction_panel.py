from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox,
                               QCheckBox)


class ReconstructionPanel(QWidget):
    """Lets the user pick how the mesh is reconstructed from the silhouettes.

    Each choice maps to reconstruction kwargs (method + de-terracing filters).
    The sub-pixel-edges checkbox is orthogonal to the method preset: it applies
    to strip/facet (soft_hull ignores it) and is on by default.
    """

    # (label, kwargs) — order defines the combo indices
    CHOICES = [
        ("Fast (visual hull)",
         {"method": "strip", "edge_median_rows": 0, "axial_median_rows": 0}),
        ("Smooth edges (recommended)",
         {"method": "strip", "edge_median_rows": 9, "axial_median_rows": 0}),
        ("Smooth surface",
         {"method": "strip", "edge_median_rows": 0, "axial_median_rows": 9}),
        ("High accuracy (slow)",
         {"method": "soft_hull", "edge_median_rows": 0, "axial_median_rows": 0}),
        ("Faceted gem (planar)",
         {"method": "facet", "edge_median_rows": 0, "axial_median_rows": 0}),
    ]

    reconstructionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combo = QComboBox()
        for label, _ in self.CHOICES:
            self._combo.addItem(label)
        self._combo.currentIndexChanged.connect(
            lambda _i: self.reconstructionChanged.emit())

        self._subpixel = QCheckBox("Sub-pixel edges")
        self._subpixel.setChecked(True)
        self._subpixel.setToolTip(
            "Locate silhouette edges on the intensity crossing instead of the "
            "nearest whole pixel (removes ~1 px edge quantisation). "
            "Applies to Fast/Smooth/Faceted; High accuracy ignores it.")
        self._subpixel.toggled.connect(
            lambda _c: self.reconstructionChanged.emit())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Reconstruction", objectName="panelTitle"))
        layout.addWidget(self._combo)
        layout.addWidget(self._subpixel)

    def selected_kwargs(self):
        kwargs = dict(self.CHOICES[self._combo.currentIndex()][1])
        kwargs["subpixel_edges"] = self._subpixel.isChecked()
        return kwargs

    def set_index(self, index):
        self._combo.setCurrentIndex(int(index))

    def set_subpixel_edges(self, on):
        self._subpixel.setChecked(bool(on))
