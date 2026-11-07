"""Offscreen Qt tests for launch action editor and test-launch wiring."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox, QPlainTextEdit

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_qt_workflow import description
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class LaunchQtTests(unittest.TestCase):
    def setUp(self):
        self.window = MacroWindow()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def tearDown(self):
        close_test_window(self.window)

    def select_launch(self):
        w = self.window
        w._replace_actions([Action(kind="launch")])
        w.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        return w.inspector

    def test_blank_action_is_editable_and_path_browse_preserves_spaces(self):
        inspector = self.select_launch()
        self.assertEqual(inspector.controls["launch_mode"].currentText(), "application")
        self.assertEqual(inspector.controls["launch_target"].text(), "")
        path = str(Path(self.temp.name) / "Apps ñ" / "Tool A.exe")
        with patch("macro_qt_properties.QFileDialog.getOpenFileName",
                   return_value=(path, "All files (*)")):
            inspector.browse_launch(inspector.controls["launch_target"])
        self.assertEqual(inspector.controls["launch_target"].text(), path)
        self.assertTrue(inspector.launch_browse.isVisible() or
                        not inspector.isVisible())

    def test_arguments_are_multiline_literals_and_persist(self):
        w = self.window
        inspector = self.select_launch()
        filename = Path(self.temp.name) / "App α.exe"
        inspector.controls["launch_target"].setText(str(filename))
        args = inspector.controls["launch_args"]
        self.assertIsInstance(args, QPlainTextEdit)
        args.setPlainText("--name\nName with spaces 你好\nC:\\Program Files\\A")
        inspector.commit()
        self.assertEqual(w.actions[0].launch_args, args.toPlainText())
        self.assertNotIn("Name with spaces", description(w.actions[0]))
        saved = serialize_document(w.actions,1,0)
        self.assertEqual(parse_document(saved)[0],w.actions)

    def test_switch_file_and_url_disables_arguments(self):
        inspector = self.select_launch()
        mode = inspector.controls["launch_mode"]
        inspector.controls["launch_args"].setPlainText("--flag\narg with space")
        mode.setCurrentText("file")
        self.assertFalse(inspector.controls["launch_args"].isEnabled())
        self.assertEqual(inspector._read_action().launch_args, "")
        mode.setCurrentText("url")
        self.assertFalse(inspector.launch_browse.isVisible())
        inspector.controls["launch_target"].setText("https://example.org/λ")
        action = inspector._read_action()
        self.assertEqual(action.launch_mode, "url")
        self.assertEqual(action.launch_target, "https://example.org/λ")
        mode.setCurrentText("application")
        self.assertTrue(inspector.controls["launch_args"].isEnabled())

    def test_test_launch_uses_unsaved_values_but_does_not_commit(self):
        w = self.window
        inspector = self.select_launch()
        inspector.controls["launch_mode"].setCurrentText("url")
        inspector.controls["launch_target"].setText("https://example.com")
        with patch("macro_qt.launch_target") as launched, patch(
                "macro_qt.QMessageBox.information") as info:
            inspector._test_launch()
        launched.assert_called_once()
        self.assertEqual(launched.call_args.args[0].launch_target,
                         "https://example.com")
        info.assert_called_once()
        self.assertEqual(w.actions[0].launch_target, "")
        self.assertTrue(w._is_dirty())

    def test_invalid_test_launch_warns_without_dispatch(self):
        inspector = self.select_launch()
        inspector.controls["launch_mode"].setCurrentText("url")
        inspector.controls["launch_target"].setText("file:///etc/passwd")
        with patch("macro_qt.launch_target") as launched, patch(
                "macro_qt_properties.QMessageBox.warning") as warning:
            inspector._test_launch()
        launched.assert_not_called()
        warning.assert_called_once()

    def test_test_launch_during_run_is_blocked(self):
        inspector = self.select_launch()
        inspector.controls["launch_mode"].setCurrentText("url")
        inspector.controls["launch_target"].setText("https://example.com")
        self.window.record_pending = True
        with patch("macro_qt.launch_target") as launch, patch(
                "macro_qt.QMessageBox.warning") as warning:
            inspector._test_launch()
        launch.assert_not_called()
        warning.assert_called_once()
        self.window.record_pending = False


if __name__ == "__main__":
    unittest.main()
