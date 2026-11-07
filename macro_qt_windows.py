"""Visible-window picker for native Windows and X11 targets."""
import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QAbstractItemView,
                               QDialogButtonBox, QPushButton, QHBoxLayout)

from macro_windows import WindowManager


class WindowPickerDialog(QDialog):
    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager or WindowManager()
        self.selected = None
        self.windows = []
        self.setWindowTitle("Choose target window")
        self.resize(850, 460)
        layout = QVBoxLayout(self)
        label = QLabel(
            "Select a visible application window. MacroRunner will bring it "
            "to the front before sending input, not inject into covered windows.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Title", "Class", "PID", "Client area", "Client origin"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 290)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 65)
        self.table.setColumnWidth(3, 110)
        layout.addWidget(self.table)
        bottom = QHBoxLayout()
        refresh = QPushButton("Refresh windows")
        refresh.clicked.connect(self.refresh)
        bottom.addWidget(refresh)
        bottom.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.choose)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)
        self.table.itemDoubleClicked.connect(lambda _item: self.choose())
        self.refresh()

    def refresh(self):
        own_handle = int(self.parent().winId()) if self.parent() is not None else None
        self.windows = [w for w in self.manager.windows()
                        if w.pid != os.getpid() and w.handle != own_handle]
        self.table.setRowCount(len(self.windows))
        for row, info in enumerate(self.windows):
            for column, text in enumerate((
                    info.title, info.class_name, str(info.pid or "unknown"),
                    f"{info.width} × {info.height}",
                    f"({info.x}, {info.y})")):
                self.table.setItem(row, column, QTableWidgetItem(text))
        if self.windows:
            self.table.selectRow(0)

    def choose(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.windows):
            self.selected = self.windows[row]
            self.accept()
