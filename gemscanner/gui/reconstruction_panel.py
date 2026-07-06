from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox


class ReconstructionPanel(QWidget):
    """Lets the user pick how the mesh is reconstructed from the silhouettes.

    Each choice maps to reconstruction kwargs (method + de-terracing filters).
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
    ]

    reconstructionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combo = QComboBox()
        for label, _ in self.CHOICES:
            self._combo.addItem(label)
        self._combo.currentIndexChanged.connect(
            lambda _i: self.reconstructionChanged.emit())

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Reconstruction", objectName="panelTitle"))
        layout.addWidget(self._combo)

    def selected_kwargs(self):
        return dict(self.CHOICES[self._combo.currentIndex()][1])

    def set_index(self, index):
        self._combo.setCurrentIndex(int(index))
