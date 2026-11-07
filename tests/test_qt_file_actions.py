"""Offscreen Qt tests for local file/folder action Properties controls."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QCheckBox

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_qt_properties import PropertiesPanel, fields_for_kind
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class FileActionQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "File with space 😀.txt"
        self.src.write_text("contents", encoding="utf-8")
        self.dst = self.root / "Other 日本語.txt"
        self.editor = MacroWindow()

    def tearDown(self):
        close_test_window(self.editor)

    def select(self, kind):
        self.editor._replace_actions([Action(kind=kind)])
        self.editor.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        return self.editor.inspector

    def test_fields_of_each_file_action_are_minimal(self):
        self.assertIn("file_path", fields_for_kind("file_check"))
        self.assertIn("timeout", fields_for_kind("file_wait"))
        self.assertIn("file_destination", fields_for_kind("file_copy"))
        self.assertIn("file_overwrite", fields_for_kind("file_move"))
        self.assertNotIn("file_destination", fields_for_kind("folder_create"))
        self.assertNotIn("file_overwrite", fields_for_kind("file_check"))

    def test_copy_source_and_destination_browsers_and_explicit_overwrite(self):
        panel = self.select("file_copy")
        with patch("macro_qt_properties.QFileDialog.getOpenFileName",
                   return_value=(str(self.src), "")) as read:
            panel.browse_file_action(panel.controls["file_path"], "file_path")
        read.assert_called_once()
        with patch("macro_qt_properties.QFileDialog.getSaveFileName",
                   return_value=(str(self.dst), "")) as save:
            panel.browse_file_action(
                panel.controls["file_destination"], "file_destination")
        save.assert_called_once()
        checkbox = panel.controls["file_overwrite"]
        self.assertIsInstance(checkbox, QCheckBox)
        self.assertFalse(checkbox.isChecked())
        panel.commit()
        action = self.editor.actions[0]
        self.assertEqual(action.file_path, str(self.src))
        self.assertEqual(action.file_destination, str(self.dst))
        self.assertFalse(action.file_overwrite)
        # Applying rebuilds the inspector; edit its current checkbox.
        panel.controls["file_overwrite"].setChecked(True)
        panel.commit()
        self.assertTrue(self.editor.actions[0].file_overwrite)
        self.assertEqual(
            parse_document(serialize_document(self.editor.actions, 1, 0))[0],
            self.editor.actions)

    def test_folder_picker_and_new_folder_name_can_be_typed(self):
        panel = self.select("folder_create")
        with patch("macro_qt_properties.QFileDialog.getExistingDirectory",
                   return_value=str(self.root)) as picker:
            panel.browse_file_action(panel.controls["file_path"], "file_path")
        picker.assert_called_once()
        self.assertEqual(panel.controls["file_path"].text(), str(self.root))
        folder = self.root / "created later" / "Child 😀"
        panel.controls["file_path"].setText(str(folder))
        panel.commit()
        self.assertEqual(self.editor.actions[0].file_path, str(folder))
        self.assertFalse(folder.exists())  # Editing cannot create folders.

    def test_wait_for_future_file_and_invalid_path_fails_to_apply(self):
        panel = self.select("file_wait")
        future = self.root / "not yet created.txt"
        panel.controls["file_path"].setText(str(future))
        panel.controls["timeout"].setText("1.5")
        panel.controls["poll_interval"].setText("0.2")
        panel.commit()
        self.assertEqual(self.editor.actions[0].file_path, str(future))
        self.assertEqual(self.editor.actions[0].timeout, 1.5)
        self.assertEqual(self.editor.actions[0].poll_interval, .2)
        panel.controls["file_path"].setText("../not-allowed.txt")
        with patch("macro_qt_properties.QMessageBox.warning") as warning:
            panel.commit()
        warning.assert_called_once()
        self.assertEqual(self.editor.actions[0].file_path, str(future))

    def test_disabled_action_remains_editable_and_does_not_touch_files(self):
        panel = self.select("file_move")
        panel.controls["file_path"].setText(str(self.src))
        panel.controls["file_destination"].setText(str(self.dst))
        panel.controls["enabled"].setChecked(False)
        panel.commit()
        self.assertFalse(self.editor.actions[0].enabled)
        self.assertTrue(self.src.is_file())
        self.assertFalse(self.dst.exists())

    def test_cancel_browser_leaves_current_value_unchanged(self):
        panel = self.select("file_copy")
        panel.controls["file_path"].setText(str(self.src))
        with patch("macro_qt_properties.QFileDialog.getOpenFileName",
                   return_value=("", "")):
            panel.browse_file_action(panel.controls["file_path"], "file_path")
        self.assertEqual(panel.controls["file_path"].text(), str(self.src))


if __name__ == "__main__":
    unittest.main()
