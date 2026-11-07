"""Small editor for typed workflow defaults and unsaved run overrides."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QDialogButtonBox, QMessageBox, QAbstractItemView,
)

from macro_variables import (TYPES, VariableContext, format_value,
                             parse_value, validate_variables)


class VariablesDialog(QDialog):
    def __init__(self, definitions, overrides=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workflow variables")
        self.resize(850, 420)
        self.definitions = None
        self.overrides = None
        outer = QVBoxLayout(self)
        help_text = QLabel(
            "Defaults are saved in the workflow. Run overrides are local to "
            "this editor session and reset each whole-workflow repeat. "
            "Blank default can be explicitly marked Unset for action outputs. "
            "Coordinates use x,y; booleans use true/false. "
            "Values are never included in Run History.")
        help_text.setWordWrap(True)
        outer.addWidget(help_text)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Default", "Unset", "Run override", "Use override"])
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 125)
        self.table.setColumnWidth(2, 145)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 155)
        self.table.setColumnWidth(5, 104)
        outer.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton("Add variable")
        add.clicked.connect(lambda: self.add_row())
        row.addWidget(add)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self.remove_rows)
        row.addWidget(remove)
        row.addStretch()
        outer.addLayout(row)
        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self._accept)
        actions.rejected.connect(self.reject)
        outer.addWidget(actions)
        for item in definitions:
            self.add_row(item, overrides or {})

    def add_row(self, item=None, overrides=None):
        if item is None:
            used = {self.table.item(i, 0).text()
                    for i in range(self.table.rowCount())
                    if self.table.item(i, 0) is not None}
            index = 1
            while f"var_{index}" in used:
                index += 1
            item = {"name": f"var_{index}", "type": "text", "default": ""}
        index = self.table.rowCount()
        self.table.insertRow(index)
        self.table.setItem(index, 0, QTableWidgetItem(item["name"]))
        type_picker = QComboBox()
        type_picker.addItems(TYPES)
        type_picker.setCurrentText(item["type"])
        self.table.setCellWidget(index, 1, type_picker)
        self.table.setItem(index, 2, QTableWidgetItem(
            format_value(item["default"], item["type"])))
        unset = QCheckBox()
        unset.setChecked(item["default"] is None)
        self.table.setCellWidget(index, 3, unset)
        value = (overrides or {}).get(item["name"])
        self.table.setItem(index, 4, QTableWidgetItem(
            format_value(value, item["type"])))
        use_override = QCheckBox()
        use_override.setChecked((overrides or {}).get(item["name"], None) is not None)
        self.table.setCellWidget(index, 5, use_override)

    def remove_rows(self):
        for index in sorted({i.row() for i in self.table.selectionModel()
                             .selectedRows()}, reverse=True):
            self.table.removeRow(index)

    def _accept(self):
        definitions = []
        overrides = {}
        try:
            for index in range(self.table.rowCount()):
                name_item = self.table.item(index, 0)
                default_item = self.table.item(index, 2)
                override_item = self.table.item(index, 4)
                name = name_item.text().strip() if name_item else ""
                kind = self.table.cellWidget(index, 1).currentText()
                default_text = default_item.text() if default_item else ""
                is_unset = self.table.cellWidget(index, 3).isChecked()
                default = (None if is_unset else
                           default_text if kind == "text" else
                           parse_value(default_text, kind))
                if default is None and not is_unset:
                    raise ValueError(f"Default for {name} is blank. Check Unset.")
                definitions.append({
                    "name": name, "type": kind, "default": default})
                if self.table.cellWidget(index, 5).isChecked():
                    override_text = override_item.text() if override_item else ""
                    value = (override_text if kind == "text" else
                             parse_value(override_text, kind))
                    if value is None:
                        raise ValueError(f"Run override for {name} cannot be blank.")
                    overrides[name] = value
            definitions = validate_variables(definitions)
            VariableContext(definitions, overrides)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid variable", str(exc))
            return
        self.definitions = definitions
        self.overrides = overrides
        self.accept()
