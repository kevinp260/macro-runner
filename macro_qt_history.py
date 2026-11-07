"""Read-only run history viewer, local export and opt-in failure captures."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from macro_diagnostics import ERROR_CODES


def describe_run(run):
    """Pure text presentation; persisted records contain no action values."""
    lines = [
        f"Run: {run['id']}",
        f"Started (UTC): {run['started_at']}",
        f"Finished (UTC): {run['ended_at']}",
        f"Outcome: {run['status']}",
        f"Duration: {run['duration_s']:.2f} seconds",
        f"Mode: {run['mode']} / workflow repeats: {run['repeat_count']}",
        f"Completed actions: {run['completed_actions']} "
        f"(workflow entries: {run['action_count']})",
    ]
    if run.get("error_code"):
        lines.append("Error: " + ERROR_CODES.get(
            run["error_code"], ERROR_CODES["Exception"]))
    if run.get("screenshot"):
        lines.append("Optional failure screenshot saved locally.")
    lines.append("")
    lines.append("Event timeline (action data and typed text are never saved):")
    for item in run.get("events", []):
        label = item["event"].replace("_", " ")
        i = item.get("index")
        prefix = f"  #{i + 1}" if i is not None else ""
        context = " > ".join(x.replace("_", " ") for x in item.get("path", []))
        more = f" · {context}" if context else ""
        if "result" in item:
            more += f" · {'true' if item['result'] else 'false'}"
        if item.get("error"):
            more += " · " + ERROR_CODES.get(item["error"], ERROR_CODES["Exception"])
        if "cycle" in item:
            more += f" · cycle {item['cycle']}"
        lines.append(f"{item['at_s']:>8.3f}s  {label}{prefix}{more}")
    if run.get("dropped_events"):
        lines.append(
            f"... {run['dropped_events']} earlier events omitted to limit storage.")
    return "\n".join(lines)


class RunHistoryDialog(QDialog):
    """History contents live in an app-local bounded store, not workflow JSON."""

    def __init__(self, store, settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.records = []
        self.setWindowTitle("MacroRunner — Run history")
        self.resize(1000, 640)
        self.setMinimumSize(720, 460)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Last {store.max_runs} runs stored locally. No typed text, "
            "clipboard values, action parameters or screenshots are logged by default.")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Started (local)", "Outcome", "Duration", "Actions", "Mode"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selected)
        layout.addWidget(self.table, 3)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 3)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        capture_row = QHBoxLayout()
        self.capture_checkbox = QCheckBox(
            "Save a screenshot on execution error (sensitive)")
        self.capture_checkbox.setToolTip(
            "Opt in. A reduced screenshot may contain passwords, documents, "
            "or personal information. Images stay on your computer.")
        self.capture_checkbox.setChecked(
            self.settings.value("diagnostics_capture_errors", False, type=bool))
        self.capture_checkbox.toggled.connect(self._capture_toggled)
        capture_row.addWidget(self.capture_checkbox)
        capture_row.addWidget(QLabel("Keep last"))
        self.max_images = QSpinBox()
        self.max_images.setRange(0, 20)
        self.max_images.setValue(self.store.max_screenshots)
        self.max_images.valueChanged.connect(self._max_images_changed)
        capture_row.addWidget(self.max_images)
        capture_row.addWidget(QLabel("failure screenshots"))
        capture_row.addStretch()
        layout.addLayout(capture_row)
        self.location = QLabel(f"Local diagnostics: {self.store.path.parent}")
        self.location.setWordWrap(True)
        layout.addWidget(self.location)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.copy_button = QPushButton("Copy selected details")
        self.export_button = QPushButton("Export safe JSON…")
        self.open_button = QPushButton("Open failure screenshot")
        self.clear_button = QPushButton("Clear history and screenshots")
        self.close_button = QPushButton("Close")
        for btn in (self.refresh_button, self.copy_button, self.export_button,
                    self.open_button, self.clear_button, self.close_button):
            actions.addWidget(btn)
        layout.addLayout(actions)
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_button.clicked.connect(self.export_history)
        self.open_button.clicked.connect(self.open_screenshot)
        self.clear_button.clicked.connect(self.clear_history)
        self.close_button.clicked.connect(self.close)
        self.refresh()

    def refresh(self):
        selected = self.selected_run()
        selected_id = selected["id"] if selected else None
        self.records = list(reversed(self.store.runs))
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(self.records))
            for row, item in enumerate(self.records):
                date = item.get("started_at", "")
                try:
                    date = datetime.fromisoformat(date).astimezone().strftime(
                        "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
                values = [
                    date, item["status"], f"{item['duration_s']:.2f}s",
                    str(item["completed_actions"]), item["mode"],
                ]
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    self.table.setItem(row, col, cell)
            preferred = next((i for i, r in enumerate(self.records)
                              if r["id"] == selected_id), 0)
            if self.records:
                self.table.selectRow(preferred)
            else:
                self.table.clearSelection()
        finally:
            self.table.blockSignals(False)
        self._selected()

    def selected_run(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            return self.records[row]
        return None

    def _selected(self):
        current = self.selected_run()
        self.details.setPlainText(describe_run(current) if current else
                                  "No runs have been saved yet.")
        self.copy_button.setEnabled(bool(current))
        self.open_button.setEnabled(bool(current and current.get("screenshot")))
        self.clear_button.setEnabled(bool(self.store.runs))

    def copy_selected(self):
        if self.selected_run():
            QApplication.clipboard().setText(self.details.toPlainText())
            self.message.setText("Selected redacted diagnostics copied.")

    def export_history(self):
        if not self.store.runs:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export redacted diagnostics", "macrorunner-diagnostics.json",
            "JSON files (*.json)")
        if not path:
            return
        try:
            count = self.store.export_safe(path)
            self.message.setText(
                f"Exported {count} run records. No screenshots or input values included.")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot export diagnostics", str(exc))

    def open_screenshot(self):
        record = self.selected_run()
        if not record or not record.get("screenshot"):
            return
        filename = record["screenshot"]
        path = self.store.capture_dir / filename
        if not path.is_file():
            QMessageBox.warning(self, "Screenshot unavailable",
                                "This failure screenshot has been removed.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _capture_toggled(self, checked):
        if checked:
            answer = QMessageBox.question(
                self, "Enable sensitive screenshot capture?",
                "Error screenshots may contain private information, including "
                "passwords or documents visible on screen. "
                "They are stored locally, never exported automatically, and "
                "can be deleted here. Enable this feature?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.capture_checkbox.blockSignals(True)
                self.capture_checkbox.setChecked(False)
                self.capture_checkbox.blockSignals(False)
                return
        self.settings.setValue("diagnostics_capture_errors", checked)
        self.message.setText(
            "Failure screenshot capture enabled." if checked
            else "Failure screenshot capture disabled.")

    def _max_images_changed(self, number):
        try:
            self.store.set_max_screenshots(number)
            self.settings.setValue("diagnostics_capture_limit", number)
        except OSError as exc:
            QMessageBox.warning(self, "Cannot adjust retention", str(exc))
        self.refresh()

    def clear_history(self):
        if QMessageBox.question(
            self, "Clear run history?",
            "Permanently delete local run records and their failure screenshots?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.clear()
            self.refresh()
            self.message.setText("Local run history and failure screenshots deleted.")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot clear history", str(exc))
