"""Preview-first workflow search and bulk replacement dialog (editor-only)."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)

from macro_find_replace import (
    REPLACE_FIELDS, SEARCH_FIELDS, plan_replacements, search_actions,
)

MAX_VISIBLE = 250


def _preview_value(value):
    """Only dialog text: never stored in diagnostics or workflow history."""
    shown = repr(value)
    return shown if len(shown) <= 110 else shown[:107] + "..."


class WorkflowFindReplaceDialog(QDialog):
    def __init__(self, actions, variables, base_dir, highlight, navigate,
                 apply_changes, parent=None):
        super().__init__(parent)
        self.actions = tuple(actions)
        self.variables = list(variables)
        self.base_dir = Path(base_dir) if base_dir is not None else None
        self.highlight = highlight
        self.navigate = navigate
        self.apply_changes = apply_changes
        self.matches = []
        self.plan = None

        self.setWindowTitle("Find and replace workflow actions")
        self.resize(720, 650)
        layout = QVBoxLayout(self)

        filter_form = QFormLayout()
        self.scope = QComboBox()
        for value, title in SEARCH_FIELDS:
            self.scope.addItem(title, value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search actions, names, keys, coordinates, images…")
        filter_form.addRow("Search within", self.scope)
        filter_form.addRow("Find", self.search)
        layout.addLayout(filter_form)

        self.result_label = QLabel("Enter a search term.")
        layout.addWidget(self.result_label)
        self.results = QListWidget()
        self.results.setAlternatingRowColors(True)
        layout.addWidget(self.results, 1)
        hint = QLabel("Choose a result to reveal the action inside its workflow group. "
                      "Structural markers can be found, but not bulk-edited.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        group = QGroupBox("Bulk replace matching compatible action values")
        replace_form = QFormLayout(group)
        self.field = QComboBox()
        for name, (label, _, _) in REPLACE_FIELDS.items():
            self.field.addItem(label, name)
        self.mode = QComboBox()
        self.mode.addItem("Set value", "set")
        self.mode.addItem("Replace substring", "replace")
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Exact substring in the current field")
        self.value = QLineEdit()
        self.value.setPlaceholderText("Replacement value")
        replace_form.addRow("Field to change", self.field)
        replace_form.addRow("Operation", self.mode)
        replace_form.addRow("Find in field", self.find_text)
        replace_form.addRow("New value / text", self.value)
        layout.addWidget(group)

        action_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview changes")
        self.apply_button = QPushButton("Apply changes")
        self.apply_button.setEnabled(False)
        self.cancel_button = QPushButton("Close")
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.apply_button)
        action_row.addStretch(1)
        action_row.addWidget(self.cancel_button)
        layout.addLayout(action_row)
        self.preview_label = QLabel("Preview required before applying any changes.")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.preview_items = QListWidget()
        self.preview_items.setMaximumHeight(145)
        layout.addWidget(self.preview_items)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refresh_search)
        self.search.textChanged.connect(self._schedule_search)
        self.scope.currentIndexChanged.connect(self._schedule_search)
        self.results.itemClicked.connect(self._jump)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self.apply)
        self.cancel_button.clicked.connect(self.reject)
        for control in (self.field, self.mode):
            control.currentIndexChanged.connect(self._invalidate_preview)
        for control in (self.find_text, self.value):
            control.textChanged.connect(self._invalidate_preview)
        self.field.currentIndexChanged.connect(self._update_mode)
        self.mode.currentIndexChanged.connect(self._update_mode)
        self._update_mode()
        self.preview_button.setEnabled(False)

    def _invalidate_preview(self, *_):
        self.plan = None
        self.apply_button.setEnabled(False)
        self.preview_items.clear()
        self.preview_label.setText("Preview required before applying any changes.")

    def _schedule_search(self, *_):
        self._invalidate_preview()
        self.timer.start()

    def _update_mode(self, *_):
        field = self.field.currentData()
        is_text = REPLACE_FIELDS[field][1] == "text"
        if not is_text and self.mode.currentData() == "replace":
            self.mode.setCurrentIndex(0)
        self.mode.model().item(1).setEnabled(is_text)
        self.find_text.setEnabled(self.mode.currentData() == "replace")
        self._invalidate_preview()

    def refresh_search(self):
        self.timer.stop()
        self.matches = search_actions(
            self.actions, self.search.text(), self.scope.currentData())
        self.results.clear()
        for match in self.matches[:MAX_VISIBLE]:
            action = self.actions[match.index]
            title = action.name.strip() or action.kind.replace("_", " ").title()
            result = QListWidgetItem(
                f"#{match.index + 1}  {title}  ·  matched {match.field}")
            result.setData(Qt.ItemDataRole.UserRole, match.index)
            self.results.addItem(result)
        extra = max(0, len(self.matches) - MAX_VISIBLE)
        message = f"{len(self.matches)} action(s) matched."
        if extra:
            message += (f" Showing first {MAX_VISIBLE}; bulk replacement "
                        "will consider ALL matches.")
        self.result_label.setText(message)
        self.preview_button.setEnabled(bool(self.matches))
        self.highlight([m.index for m in self.matches[:MAX_VISIBLE]])
        self._invalidate_preview()

    def _jump(self, item):
        self.navigate(item.data(Qt.ItemDataRole.UserRole))

    def preview(self):
        self.refresh_search()
        try:
            self.plan = plan_replacements(
                self.actions, [m.index for m in self.matches],
                self.field.currentData(), self.value.text(),
                mode=self.mode.currentData(), find_text=self.find_text.text(),
                variables=self.variables, base_dir=self.base_dir)
        except (ValueError, TypeError) as exc:
            self.plan = None
            self.apply_button.setEnabled(False)
            self.preview_label.setText(str(exc))
            return
        self.preview_items.clear()
        for change in self.plan.changes[:MAX_VISIBLE]:
            self.preview_items.addItem(
                f"#{change.index + 1}: {_preview_value(change.old)}  →  "
                f"{_preview_value(change.new)}")
        summary = f"{len(self.plan.changes)} change(s) validated."
        if self.plan.skipped:
            summary += (f" {self.plan.skipped} incompatible, structural or "
                        "variable-bound action(s) skipped.")
        if len(self.plan.changes) > MAX_VISIBLE:
            summary += f" First {MAX_VISIBLE} previews shown; all validated changes apply."
        self.preview_label.setText(summary + " Apply records a single Undo step.")
        self.apply_button.setEnabled(True)

    def apply(self):
        if self.plan is None:
            return
        try:
            self.apply_changes(
                list(self.plan.actions), [change.index for change in self.plan.changes])
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot replace workflow values", str(exc))
            return
        self.accept()

    def done(self, code):
        self.timer.stop()
        self.highlight([])
        super().done(code)
