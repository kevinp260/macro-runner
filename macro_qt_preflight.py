"""Reviewable pre-run findings with navigation to the original tree action."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)


class PreflightDialog(QDialog):
    def __init__(self, findings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workflow validation")
        self.resize(720, 360)
        self.navigation_index = None
        self.findings = list(findings)
        self.has_errors = any(f.severity == "error" for f in self.findings)

        layout = QVBoxLayout(self)
        errors = sum(f.severity == "error" for f in self.findings)
        warnings = len(self.findings) - errors
        summary = QLabel(
            f"{errors} blocking error(s), {warnings} warning(s). "
            + ("Fix errors before running." if errors else
               "Review warnings before continuing."))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Severity", "Action", "Issue / suggested fix"])
        self.table.setRootIsDecorated(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for finding in self.findings:
            item = QTreeWidgetItem([
                finding.severity.upper(),
                f"#{finding.index + 1}" if finding.index is not None else "Workflow",
                finding.message,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, finding.index)
            item.setToolTip(2, finding.message)
            self.table.addTopLevelItem(item)
        layout.addWidget(self.table)
        self.table.currentItemChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.go_to_action())

        hint = QLabel(
            "Choose a finding and Go to action to locate it in the editor. "
            "Offscreen warnings may be valid on another monitor.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox()
        self.goto_button = buttons.addButton(
            "Go to action", QDialogButtonBox.ButtonRole.ActionRole)
        self.goto_button.clicked.connect(self.go_to_action)
        buttons.addButton(
            "Close" if self.has_errors else "Cancel",
            QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)
        self.run_button = None
        if not self.has_errors:
            self.run_button = buttons.addButton(
                "Run anyway", QDialogButtonBox.ButtonRole.AcceptRole)
            self.run_button.clicked.connect(self.accept)
        layout.addWidget(buttons)
        if self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self._selection_changed()

    def _selection_changed(self, *_):
        item = self.table.currentItem()
        self.goto_button.setEnabled(
            item is not None and item.data(0, Qt.ItemDataRole.UserRole) is not None)

    def go_to_action(self):
        item = self.table.currentItem()
        if item is None:
            return
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.navigation_index = index
            self.reject()
