"""Offscreen Qt regression tests for dirty prompts and recovery decisions."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_recovery import RecoveryStore
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class RecoveryPrompt:
    Icon = SimpleNamespace(Question=1)
    ButtonRole = SimpleNamespace(AcceptRole=1, DestructiveRole=2)
    decision = "Restore"

    def __init__(self, parent=None):
        self.buttons = {}

    def setWindowTitle(self, value): pass
    def setIcon(self, value): pass
    def setText(self, value): pass
    def setInformativeText(self, value): self.details = value

    def addButton(self, text, role):
        button = object()
        self.buttons[text] = button
        return button

    def exec(self): return None

    def clickedButton(self):
        return self.buttons.get(self.decision)


class QtRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "recovery.json"
        self.window = MacroWindow()
        self.window.recovery_store = RecoveryStore(self.path)

    def tearDown(self):
        close_test_window(self.window)

    def test_dirty_title_and_settings_undo_and_snapshot(self):
        w = self.window
        self.assertFalse(w._is_dirty())
        self.assertNotIn("* ", w.windowTitle())
        w._replace_actions([Action(kind="wait", seconds=1)])
        self.assertTrue(w._is_dirty())
        self.assertTrue(w.windowTitle().startswith("* "))
        w._write_recovery()
        self.assertEqual(w.recovery_store.read().actions, w.actions)
        self.assertTrue(self.path.is_file())
        w.undo()
        self.assertFalse(w._is_dirty())
        self.assertFalse(self.path.exists())
        w.repeats.setValue(5)
        self.assertTrue(w._is_dirty())
        w.repeats.setValue(1)
        self.assertFalse(w._is_dirty())
        w.delay.setValue(5)
        self.assertTrue(w._is_dirty())
        w.delay.setValue(3)
        self.assertFalse(w._is_dirty())

    def test_save_as_clears_dirty_and_never_stores_recovery_in_macro(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="test")])
        w._write_recovery()
        target = self.root / "saved.json"
        with patch("macro_qt.QFileDialog.getSaveFileName",
                   return_value=(str(target), "Macro files")):
            self.assertTrue(w.save_workflow())
        self.assertFalse(w._is_dirty())
        self.assertFalse(self.path.exists())
        self.assertEqual(w.current_file, str(target))
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(parse_document(document)[0], w.actions)
        self.assertNotIn("recovery", document)
        self.assertFalse(w.windowTitle().startswith("* "))

    def test_open_invalid_json_does_not_replace_dirty_document(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="safe")])
        w._write_recovery()
        old = w.actions[:]
        invalid = self.root / "corrupt.json"
        invalid.write_text("not json", encoding="utf-8")
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(invalid), "")), patch(
                   "macro_qt.QMessageBox.warning") as warning, patch(
                   "macro_qt.QMessageBox.question") as question:
            w.open_workflow()
        warning.assert_called_once()
        question.assert_not_called()
        self.assertEqual(w.actions, old)
        self.assertTrue(w._is_dirty())
        self.assertIsNone(w.current_file)
        self.assertTrue(self.path.exists())

    def test_cancel_new_open_close_preserves_edits_and_recovery(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="keep")])
        w._write_recovery()
        target = self.root / "other.json"
        target.write_text(json.dumps(serialize_document(
            [Action(kind="key", keys="other")], 1, 0)), encoding="utf-8")
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Cancel), patch(
                   "macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(target), "")):
            w.new_workflow()
            w.open_workflow()
            self.assertFalse(w.close())
        self.assertEqual(w.actions[0].keys, "keep")
        self.assertTrue(w._is_dirty())
        self.assertTrue(self.path.exists())

    def test_save_choice_canceled_does_not_discard_edits(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="keep")])
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Save), patch(
                   "macro_qt.QFileDialog.getSaveFileName",
                   return_value=("", "")):
            w.new_workflow()
        self.assertEqual(w.actions[0].keys, "keep")
        self.assertTrue(w._is_dirty())

    def test_discard_then_open_resets_history_and_clears_snapshot(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="before")])
        w._write_recovery()
        target = self.root / "loaded.json"
        target.write_text(json.dumps(serialize_document(
            [Action(kind="key", keys="loaded")], 6, 1.5)), encoding="utf-8")
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(target), "")), patch(
                   "macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            w.open_workflow()
        self.assertEqual(w.actions[0].keys, "loaded")
        self.assertEqual((w.repeats.value(), w.delay.value()), (6, 1.5))
        self.assertFalse(w._is_dirty())
        self.assertFalse(w.history.can_undo)
        self.assertFalse(self.path.exists())

    def test_failed_user_save_preserves_target_and_dirty_recovery(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="changed")])
        w._write_recovery()
        target = self.root / "saved.json"
        target.write_text("original file", encoding="utf-8")
        with patch("macro_qt.QFileDialog.getSaveFileName",
                   return_value=(str(target), "")), patch(
                   "macro_qt.atomic_json_write",
                   side_effect=PermissionError("read-only")), patch(
                   "macro_qt.QMessageBox.warning") as warning:
            self.assertFalse(w.save_workflow())
        warning.assert_called_once()
        self.assertEqual(target.read_text(), "original file")
        self.assertTrue(self.path.exists())
        self.assertTrue(w._is_dirty())
        self.assertIsNone(w.current_file)

    def test_crash_restart_restore_is_unsaved_copy_and_source_untouched(self):
        first = self.window
        first._replace_actions([Action(kind="key", keys="crash data")])
        first.repeats.setValue(3)
        source = self.root / "original.json"
        source.write_text("original file remains untouched", encoding="utf-8")
        first.current_file = str(source)
        first._write_recovery()
        snapshot = self.path.read_bytes()
        # Simulate the OS ending the first session without editor Close.
        first.recovery_timer.stop()
        first.recovery_store = RecoveryStore(self.root / "unused.json")
        close_test_window(first)
        self.window = MacroWindow()
        self.window.recovery_store = RecoveryStore(self.path)
        RecoveryPrompt.decision = "Restore"
        with patch("macro_qt.QMessageBox", RecoveryPrompt):
            self.window.offer_recovery()
        self.assertEqual(self.window.actions[0].keys, "crash data")
        self.assertEqual(self.window.repeats.value(), 3)
        self.assertTrue(self.window._is_dirty())
        self.assertIsNone(self.window.current_file)
        self.assertEqual(source.read_text(), "original file remains untouched")
        self.assertEqual(self.path.read_bytes(), snapshot)
        # The original path remains available on another crash/restart,
        # although the recovered document itself is always untitled.
        self.window._write_recovery()
        self.assertEqual(self.window.recovery_store.read().source_file, str(source))
        saved_copy = self.root / "recovered-as.json"
        with patch("macro_qt.QFileDialog.getSaveFileName",
                   return_value=(str(saved_copy), "")):
            self.assertTrue(self.window.save_workflow())
        self.assertEqual(parse_document(json.loads(saved_copy.read_text()))[0],
                         self.window.actions)
        self.assertEqual(source.read_text(), "original file remains untouched")
        self.assertFalse(self.path.exists())

    def test_discard_recovery_leaves_empty_editor_and_deletes_snapshot(self):
        self.window.recovery_store.write(
            [Action(kind="key", keys="discard")], 1, 0, "previous.json")
        RecoveryPrompt.decision = "Discard recovery"
        with patch("macro_qt.QMessageBox", RecoveryPrompt):
            self.window.offer_recovery()
        self.assertEqual(self.window.actions, [])
        self.assertFalse(self.window._is_dirty())
        self.assertFalse(self.path.exists())

    def test_unreadable_recovery_can_be_preserved_without_overwrite(self):
        w = self.window
        self.path.write_text("{incomplete", encoding="utf-8")
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Cancel):
            w.offer_recovery()
        self.assertTrue(w._recovery_locked)
        w._replace_actions([Action(kind="key", keys="new work")])
        w._write_recovery()
        self.assertEqual(self.path.read_text(), "{incomplete")
        self.assertTrue(w._is_dirty())
        w._mark_clean()
        self.assertEqual(self.path.read_text(), "{incomplete")

    def test_unreadable_recovery_requires_explicit_discard(self):
        w = self.window
        self.path.write_text("{damaged", encoding="utf-8")
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            w.offer_recovery()
        self.assertFalse(w._recovery_locked)
        self.assertFalse(self.path.exists())
        w._replace_actions([Action(kind="key", keys="new work")])
        w._write_recovery()
        self.assertEqual(w.recovery_store.read().actions, w.actions)

    def test_recovery_permission_error_keeps_unsaved_state(self):
        w = self.window
        w._replace_actions([Action(kind="key", keys="not lost")])
        with patch.object(w.recovery_store, "write",
                          side_effect=PermissionError("denied")), patch(
                          "macro_qt.QMessageBox.warning") as warning:
            w._write_recovery()
        self.assertTrue(w._is_dirty())
        self.assertEqual(w.actions[0].keys, "not lost")
        warning.assert_called_once()
        self.assertTrue(w.windowTitle().startswith("* "))


if __name__ == "__main__":
    unittest.main()
