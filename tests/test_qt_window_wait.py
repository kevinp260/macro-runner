"""Offscreen Qt inspector tests for the wait-for-window action."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_recovery import RecoveryStore
from macro_windows import WindowInfo
from qt_test_helpers import close_test_window


app = QApplication.instance() or QApplication([])


def window():
    return WindowInfo(80, "Test App", "TestClass", 900, 60, 80, 800, 600)


class WaitWindowQtTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.editor = MacroWindow()
        self.editor.recovery_store = RecoveryStore(
            Path(self.tmp.name) / "recovery.json")

    def tearDown(self):
        close_test_window(self.editor)

    def select(self, action=None):
        self.editor._replace_actions([action or Action(kind="wait_window")])
        self.editor.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        return self.editor.inspector

    def test_custom_wait_fields_and_round_trip(self):
        panel = self.select()
        self.assertEqual(panel.controls["window_wait_state"].currentText(),
                         "appears")
        self.assertTrue(panel.controls["window_wait_title"].isEnabled())
        panel.controls["window_wait_title"].setText("Future App")
        panel.controls["window_wait_class"].setText("MainWindow")
        panel.controls["window_wait_state"].setCurrentText("active")
        panel.controls["timeout"].setText("12.5")
        panel.controls["poll_interval"].setText("0.4")
        panel.commit()
        action = self.editor.actions[0]
        self.assertEqual((action.window_wait_title, action.window_wait_class),
                         ("Future App", "MainWindow"))
        self.assertEqual(action.window_wait_state, "active")
        self.assertEqual(action.timeout, 12.5)
        self.assertEqual(action.poll_interval, .4)
        self.assertEqual(parse_document(
            serialize_document([action], 1, 0))[0][0], action)

    def test_selected_window_identity_and_manual_changes_clear_stale_id(self):
        panel = self.select()
        class Dialog:
            selected = window()
            def __init__(self, manager, parent): pass
            def setWindowTitle(self, title): pass
            def exec(self): return QDialog.DialogCode.Accepted
        with patch("macro_qt_properties.WindowManager",
                   return_value=object()), patch(
                   "macro_qt_properties.WindowPickerDialog", Dialog):
            panel.pick_wait_window()
        self.assertEqual(panel.controls["window_wait_title"].text(), "Test App")
        self.assertEqual(panel.controls["window_wait_class"].text(), "TestClass")
        picked = panel._read_action()
        self.assertEqual(picked.window_wait_handle, 80)
        self.assertEqual(picked.window_wait_pid, 900)
        # Editing the title deliberately clears the old handle/PID, rather
        # than accidentally matching the wrong application's window.
        panel.controls["window_wait_title"].textEdited.emit("New App")
        panel.controls["window_wait_title"].setText("New App")
        changed = panel._read_action()
        self.assertEqual((changed.window_wait_handle, changed.window_wait_pid),
                         (0, 0))
        self.assertEqual(changed.window_wait_title, "New App")

    def test_workflow_source_disables_custom_editor_without_changing_target(self):
        action = Action(kind="wait_window", window_wait_title="Old title",
                        window_wait_handle=80, window_wait_pid=900)
        panel = self.select(action)
        panel.controls["window_wait_source"].setCurrentText("workflow")
        self.assertFalse(panel.controls["window_wait_title"].isEnabled())
        self.assertFalse(panel.wait_pick.isEnabled())
        panel.commit()
        self.assertEqual(self.editor.actions[0].window_wait_source, "workflow")
        self.assertEqual(self.editor.actions[0].window_wait_handle, 80)
        panel.controls["window_wait_source"].setCurrentText("custom")
        self.assertTrue(panel.controls["window_wait_title"].isEnabled())

    def test_invalid_picker_and_cancel_do_not_mutate(self):
        panel = self.select()
        class Dialog:
            selected = None
            def __init__(self, manager, parent): pass
            def setWindowTitle(self, title): pass
            def exec(self): return QDialog.DialogCode.Rejected
        with patch("macro_qt_properties.WindowManager",
                   return_value=object()), patch(
                   "macro_qt_properties.WindowPickerDialog", Dialog):
            panel.pick_wait_window()
        self.assertEqual(panel.controls["window_wait_title"].text(), "")
        self.assertEqual(panel._read_action().window_wait_handle, 0)

    def test_validation_in_inspector_does_not_save_invalid_timeout(self):
        panel = self.select()
        panel.controls["window_wait_title"].setText("App")
        panel.controls["timeout"].setText("-100")
        previous = self.editor.actions[:]
        with patch("macro_qt_properties.QMessageBox.warning") as warning:
            panel.commit()
        warning.assert_called_once()
        self.assertEqual(self.editor.actions, previous)

    def test_disabled_action_and_document_settings_still_roundtrip(self):
        action = Action(kind="wait_window", window_wait_title="App",
                        window_wait_state="closed", enabled=False)
        panel = self.select(action)
        self.assertFalse(panel.controls["enabled"].isChecked())
        self.assertEqual(panel._read_action(), action)
        self.assertEqual(parse_document(
            serialize_document(self.editor.actions, 3, .2))[0][0], action)


if __name__ == "__main__":
    unittest.main()
