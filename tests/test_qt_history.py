"""Offscreen Qt tests for run history controls and local privacy preferences."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from macro_diagnostics import RunHistoryStore, RunSession
from macro_model import Action
from macro_qt_history import RunHistoryDialog, describe_run
from macro_qt import MacroWindow

app = QApplication.instance() or QApplication([])


class RunHistoryUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RunHistoryStore(Path(self.tmp.name) / "history.json",
                                     max_runs=4, max_screenshots=2)
        self.settings = QSettings("MacroRunner-DiagnosticsTests", "History")
        self.settings.clear()

    def tearDown(self):
        self.settings.clear()
        self.tmp.cleanup()

    def add_run(self, status="completed"):
        session = RunSession([
            Action(kind="key", keys="SECRET_KEYSTROKE", name="SECRET_LABEL")])
        session.add({"event": "action_start", "index": 0})
        session.add({"event": "action_done", "index": 0})
        if status == "error":
            session.add({"event": "action_error", "index": 0,
                         "error": "TimeoutError"})
        self.store.add(session.finish(status))

    def test_table_details_copy_and_safe_export(self):
        self.add_run("completed")
        self.add_run("error")
        dialog = RunHistoryDialog(self.store, self.settings)
        try:
            dialog.show()
            app.processEvents()
            self.assertEqual(dialog.table.rowCount(), 2)
            self.assertEqual(dialog.selected_run()["status"], "error")
            details = dialog.details.toPlainText()
            self.assertIn("Outcome: error", details)
            self.assertIn("Timed out", details)
            self.assertNotIn("SECRET_KEYSTROKE", details)
            self.assertNotIn("SECRET_LABEL", details)
            dialog.copy_selected()
            self.assertEqual(app.clipboard().text(), dialog.details.toPlainText())
            path = str(Path(self.tmp.name) / "export.json")
            with patch("macro_qt_history.QFileDialog.getSaveFileName",
                       return_value=(path, "JSON files (*.json)")):
                dialog.export_history()
            exported = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("SECRET", exported)
            self.assertIn('"schema": 1', exported)
        finally:
            dialog.close()

    def test_screenshots_require_explicit_approval_and_retention(self):
        dialog = RunHistoryDialog(self.store, self.settings)
        try:
            with patch("macro_qt_history.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.No):
                dialog.capture_checkbox.setChecked(True)
            self.assertFalse(dialog.capture_checkbox.isChecked())
            self.assertFalse(self.settings.value(
                "diagnostics_capture_errors", False, type=bool))
            with patch("macro_qt_history.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Yes):
                dialog.capture_checkbox.setChecked(True)
            self.assertTrue(self.settings.value(
                "diagnostics_capture_errors", False, type=bool))
            dialog.max_images.setValue(1)
            self.assertEqual(self.store.max_screenshots, 1)
            self.assertEqual(self.settings.value(
                "diagnostics_capture_limit", 0, type=int), 1)
        finally:
            dialog.close()

    def test_clear_history_is_confirmed(self):
        self.add_run()
        dialog = RunHistoryDialog(self.store, self.settings)
        try:
            with patch("macro_qt_history.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.No):
                dialog.clear_history()
            self.assertEqual(dialog.table.rowCount(), 1)
            with patch("macro_qt_history.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Yes):
                dialog.clear_history()
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertEqual(self.store.runs, [])
        finally:
            dialog.close()

    def test_main_window_writes_completed_run_and_refreshes_history(self):
        window = MacroWindow()
        window.diagnostics_store = self.store
        try:
            actions = [Action(kind="wait", seconds=0)]
            window._run_session = RunSession(actions)
            window._diagnostic_event({"event": "action_start", "index": 0})
            window._diagnostic_event({"event": "action_done", "index": 0})
            window._finished(True, "Workflow completed.")
            self.assertEqual(self.store.runs[-1]["status"], "completed")
            self.assertEqual(self.store.runs[-1]["completed_actions"], 1)
            window.show_run_history()
            app.processEvents()
            self.assertEqual(window.run_history_dialog.table.rowCount(), 1)
            self.assertIsNone(window._run_session)
        finally:
            if window.run_history_dialog:
                window.run_history_dialog.close()
            window.close()

    def test_main_window_stopped_and_error_status_are_distinct(self):
        window = MacroWindow()
        window.diagnostics_store = self.store
        try:
            window._run_session = RunSession([Action(kind="wait", seconds=0)])
            window.executor = SimpleNamespace(
                gate=SimpleNamespace(stopped=SimpleNamespace(is_set=lambda: True)))
            with patch("macro_qt.QMessageBox.warning"):
                window._finished(False, "Stopped.")
            self.assertEqual(self.store.runs[-1]["status"], "stopped")
            window._run_session = RunSession([Action(kind="key", keys="private")])
            window._diagnostic_event({"event": "action_error", "index": 0,
                                      "error": "PermissionError"})
            with patch("macro_qt.QMessageBox.warning"):
                window._finished(False, "private error message")
            rec = self.store.runs[-1]
            self.assertEqual(rec["status"], "error")
            self.assertEqual(rec["error_code"], "PermissionError")
            self.assertNotIn("private error message", json.dumps(rec))
        finally:
            window.executor = None
            window.close()


if __name__ == "__main__":
    unittest.main()
