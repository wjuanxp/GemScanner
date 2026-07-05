from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel


class QueuePanel(QWidget):
    """Ordered list of gems to scan."""

    gemSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gems = []
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Scan queue", objectName="panelTitle"))
        layout.addWidget(self._list, 1)

    def set_gems(self, gems):
        self._gems = list(gems)
        self._list.clear()
        for g in self._gems:
            self._list.addItem(QListWidgetItem(g.name))

    def gems(self):
        return list(self._gems)

    def add_gem(self, gem):
        self._gems.append(gem)
        self._list.addItem(QListWidgetItem(gem.name))

    def current_index(self):
        return self._list.currentRow()

    def select(self, index):
        self._list.setCurrentRow(index)

    def _on_row(self, row):
        if row >= 0:
            self.gemSelected.emit(row)
