"""Offscreen Qt tests for target selection and persistence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_qt_windows import WindowPickerDialog
from macro_windows import (WindowBinding, WindowInfo, WindowManager,
                           WindowUnavailable, target_from_window)
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


def info():
    return WindowInfo(101, "Example editor", "ExampleClass", 600,
                      200, 120, 800, 600)


class FakeBackend:
    def windows(self):
        return [info()]

    def foreground_handle(self):
        return info().handle

    def activate(self, handle):
        pass


class WindowUIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = MacroWindow()

    def tearDown(self):
        close_test_window(self.window)

    def test_target_picker_shows_geometry_and_process(self):
        dialog = WindowPickerDialog(WindowManager(FakeBackend()))
        try:
            self.assertEqual(dialog.table.rowCount(), 1)
            self.assertEqual(dialog.table.item(0, 0).text(), "Example editor")
            self.assertEqual(dialog.table.item(0, 2).text(), "600")
            self.assertEqual(dialog.table.item(0, 3).text(), "800 × 600")
            self.assertEqual(dialog.table.item(0, 4).text(), "(200, 120)")
            dialog.table.selectRow(0)
            dialog.choose()
            self.assertEqual(dialog.selected, info())
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        finally:
            dialog.close()

    def test_pick_action_populates_workflow_target_and_dirty_marker(self):
        w = self.window
        class Dialog:
            selected = info()
            def __init__(self, manager, parent): pass
            def exec(self): return QDialog.DialogCode.Accepted
        with patch("macro_qt.WindowManager", return_value=object()), patch(
                "macro_qt.WindowPickerDialog", Dialog):
            w.pick_target_window()
        self.assertEqual(w.window_target["title"], info().title)
        self.assertTrue(w.target_relative.isChecked())
        self.assertTrue(w.target_activate.isChecked())
        self.assertTrue(w._is_dirty())
        self.assertTrue(w.windowTitle().startswith("* "))
        w.target_activate.setChecked(False)
        self.assertFalse(w.window_target["activate"])
        w.target_relative.setChecked(False)
        self.assertFalse(w.window_target["relative"])
        w.target_clear.click()
        self.assertIsNone(w.window_target)
        self.assertFalse(w._is_dirty())

    def test_target_round_trip_undo_state_and_autosave(self):
        w = self.window
        spec = target_from_window(info())
        w._replace_actions([Action(kind="click", x=10, y=20)])
        w._set_window_target(spec)
        file = self.root / "targeted.json"
        with patch("macro_qt.QFileDialog.getSaveFileName",
                   return_value=(str(file), "")):
            self.assertTrue(w.save_workflow())
        self.assertFalse(w._is_dirty())
        actions, settings = parse_document(json.loads(file.read_text()))
        self.assertEqual(actions, w.actions)
        self.assertEqual(settings["window_target"], spec)
        self.assertEqual(w.window_target, spec)
        w.target_relative.setChecked(False)
        self.assertTrue(w._is_dirty())
        w._write_recovery()
        self.assertEqual(w.recovery_store.read().window_target["relative"], False)
        # Clean up the real recovery file before any later tests.
        w._mark_clean()
        w.new_workflow()
        self.assertIsNone(w.window_target)
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(file), "")):
            w.open_workflow()
        self.assertEqual(w.window_target, spec)
        self.assertFalse(w._is_dirty())

    def test_conversion_rejects_positions_outside_client(self):
        w = self.window
        w._set_window_target(target_from_window(info()))
        fake_binding = WindowBinding(w.window_target, WindowManager(FakeBackend()))
        with patch("macro_qt.WindowBinding", return_value=fake_binding):
            self.assertEqual(w._client_coordinates(220, 155), (20, 35))
            self.assertEqual(w._client_coordinates(220, 155, 60, 70),
                             (20, 35, 60, 70))
            with self.assertRaises(WindowUnavailable):
                w._client_coordinates(5, 5)
            with self.assertRaises(WindowUnavailable):
                w._client_coordinates(940, 155, 100, 40)

    def test_bad_target_file_never_replaces_current_editor(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="important")])
        original = w.actions[:]
        doc = serialize_document([Action(kind="wait", seconds=1)], 1, 0)
        doc["settings"]["window_target"] = {"title": "invalid"}
        file = self.root / "malformed.json"
        file.write_text(json.dumps(doc), encoding="utf-8")
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(file), "")), patch(
                   "macro_qt.QMessageBox.warning") as warning:
            w.open_workflow()
        warning.assert_called_once()
        self.assertEqual(w.actions, original)
        self.assertTrue(w._is_dirty())

    def test_window_target_controls_locked_during_execution(self):
        w = self.window
        w._set_window_target(target_from_window(info()))
        w.record_pending = True
        w._update_controls()
        self.assertFalse(w.target_pick.isEnabled())
        self.assertFalse(w.target_relative.isEnabled())
        self.assertFalse(w.target_activate.isEnabled())
        w.record_pending = False
        w._update_controls()
        self.assertTrue(w.target_pick.isEnabled())


if __name__ == "__main__":
    unittest.main()
