"""Local snippet library browser. Insertion copies actions; it never creates links."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QFileDialog,
    QInputDialog, QMessageBox,
)

from macro_workflow import from_actions
from macro_model import parse_sequence
from macro_qt_workflow import description


def snippet_preview(snippet):
    """Human-readable structure without disclosing literal clipboard contents."""
    actions = parse_sequence(snippet["actions"])
    lines = [
        f"{snippet['name']}  ·  {len(actions)} raw actions",
        "Insertion: independent copy (never a live link)",
        "",
    ]
    if snippet["variables"]:
        lines.append("Variable dependencies:")
        for item in snippet["variables"]:
            suffix = " (text default omitted)" if item["type"] == "text" else ""
            lines.append(f"  {item['name']}: {item['type']}{suffix}")
        lines.append("Same-name variables use this workflow's existing values.")
        lines.append("")
    lines.append("Actions:")

    def walk(nodes, depth=0):
        for node in nodes:
            lines.append("  " * depth + description(node.action))
            if node.is_group:
                walk(node.children, depth + 1)
                if node.otherwise:
                    lines.append("  " * depth + "Else:")
                    walk(node.otherwise, depth + 1)

    walk(from_actions(actions))
    return "\n".join(lines)


class SnippetLibraryDialog(QDialog):
    def __init__(self, store, save_selection, insert_copy, parent=None):
        super().__init__(parent)
        self.store = store
        self.save_selection = save_selection
        self.insert_copy = insert_copy
        self.setWindowTitle("Workflow snippets — local library")
        self.setMinimumSize(690, 470)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Save selected actions or a whole group; insertion makes an independent copy."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search snippet names…")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        content = QHBoxLayout()
        self.items = QListWidget()
        self.items.itemSelectionChanged.connect(self._preview)
        content.addWidget(self.items, 2)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        content.addWidget(self.preview, 3)
        layout.addLayout(content, 1)

        top = QHBoxLayout()
        self.save_button = QPushButton("Save selection…")
        self.save_button.clicked.connect(self._save)
        top.addWidget(self.save_button)
        self.insert_button = QPushButton("Insert copy")
        self.insert_button.clicked.connect(self._insert)
        top.addWidget(self.insert_button)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._rename)
        top.addWidget(self.rename_button)
        self.replace_button = QPushButton("Replace from selection…")
        self.replace_button.clicked.connect(self._replace)
        top.addWidget(self.replace_button)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        for title, handler in (
            ("Import…", self._import), ("Export…", self._export),
            ("Delete…", self._delete),
        ):
            button = QPushButton(title)
            button.clicked.connect(handler)
            bottom.addWidget(button)
        bottom.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.refresh()

    def _selected_id(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selected_snippet(self):
        ident = self._selected_id()
        if ident is None:
            raise ValueError("Select a saved snippet first.")
        return self.store.read(ident)

    def _error(self, title, error):
        QMessageBox.warning(self, title, str(error))

    def refresh(self, selected_id=None):
        if isinstance(selected_id, bool):
            selected_id = None
        if selected_id is None:
            selected_id = self._selected_id()
        query = self.search.text().strip().casefold()
        self.items.clear()
        for entry in self.store.list():
            if query not in entry["name"].casefold():
                continue
            item = QListWidgetItem(
                f"{entry['name']}  ({entry['actions']} actions)")
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.items.addItem(item)
            if selected_id == entry["id"]:
                self.items.setCurrentItem(item)
        if self.items.currentItem() is None and self.items.count():
            self.items.setCurrentRow(0)
        self._preview()

    def _preview(self):
        try:
            snippet = self._selected_snippet()
            self.preview.setPlainText(snippet_preview(snippet))
        except (OSError, ValueError, TypeError):
            self.preview.setPlainText("Select a valid snippet to preview its actions.")
        selected = self._selected_id() is not None
        for button in (self.insert_button, self.rename_button, self.replace_button):
            button.setEnabled(selected)

    def _save(self):
        name, accepted = QInputDialog.getText(self, "Save snippet", "Snippet name:")
        if not accepted:
            return
        try:
            ident = self.save_selection(name.strip())
            self.refresh(ident)
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot save snippet", exc)

    def _insert(self):
        try:
            self.insert_copy(self._selected_snippet())
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot insert snippet", exc)
            return
        self.accept()

    def _rename(self):
        try:
            snippet = self._selected_snippet()
            ident = self._selected_id()
            name, accepted = QInputDialog.getText(
                self, "Rename snippet", "Snippet name:", text=snippet["name"])
            if accepted:
                self.store.rename(ident, name)
                self.refresh(ident)
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot rename snippet", exc)

    def _replace(self):
        try:
            snippet = self._selected_snippet()
            ident = self._selected_id()
            response = QMessageBox.question(
                self, "Replace saved snippet",
                f"Replace the saved contents of '{snippet['name']}' with the "
                "currently selected workflow actions?\n\n"
                "Existing workflow copies will NOT change.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes:
                return
            self.save_selection(snippet["name"], ident)
            self.refresh(ident)
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot replace snippet", exc)

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import a snippet", "", "Snippet JSON (*.json)")
        if not filename:
            return
        try:
            ident = self.store.import_file(filename)
            self.search.clear()
            self.refresh(ident)
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot import snippet", exc)

    def _export(self):
        try:
            snippet = self._selected_snippet()
            ident = self._selected_id()
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot export snippet", exc)
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export snippet", snippet["name"] + ".json",
            "Snippet JSON (*.json)")
        if not filename:
            return
        response = QMessageBox.question(
            self, "Export local snippet",
            "Exports contain literal action text, file paths and image references. "
            "Do not share a snippet containing credentials or private content. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.export_file(ident, filename)
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot export snippet", exc)

    def _delete(self):
        try:
            snippet = self._selected_snippet()
            ident = self._selected_id()
            response = QMessageBox.question(
                self, "Delete snippet",
                f"Delete '{snippet['name']}' from your local library? "
                "Already inserted workflow copies remain unchanged.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response == QMessageBox.StandardButton.Yes:
                self.store.delete(ident)
                self.refresh()
        except (OSError, ValueError, TypeError) as exc:
            self._error("Cannot delete snippet", exc)
