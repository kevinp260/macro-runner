"""Offscreen integration of portable package menu commands."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from macro_model import Action, parse_document, serialize_document
from macro_packages import export_package
from macro_qt import MacroWindow
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class PortablePackageQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = MacroWindow()
        self.window.package_assets_dir = self.root / "imported"
        self.window.recovery_store.path = self.root / "recovery.json"

    def tearDown(self):
        close_test_window(self.window)

    def test_file_menu_exposes_package_actions(self):
        self.assertEqual(self.window.import_package_action.text(),
                         "Import portable package…")
        self.assertEqual(self.window.export_package_action.text(),
                         "Export portable package…")
        self.assertTrue(self.window.import_package_action.isEnabled())

    def test_confirmed_export_keeps_editor_unchanged(self):
        image = self.root / "reference.png"
        Image.new("RGB", (6, 6), "red").save(image)
        self.window._replace_actions([Action(kind="click_image", image_path=str(image))])
        actions_before = list(self.window.actions)
        file = self.root / "transfer.mrpkg"
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes), patch(
                "macro_qt.QFileDialog.getSaveFileName",
                return_value=(str(file), "Macro packages (*.mrpkg)")):
            self.window.export_workflow_package()
        self.assertTrue(file.is_file())
        self.assertEqual(self.window.actions, actions_before)
        self.assertEqual(self.window.current_file, None)

    def test_cancel_export_does_not_write_anything(self):
        self.window._replace_actions([Action(kind="wait")])
        with patch("macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No), patch(
                "macro_qt.QFileDialog.getSaveFileName") as picker:
            self.window.export_workflow_package()
        picker.assert_not_called()
        self.assertEqual(list(self.root.glob("*.mrpkg")), [])

    def test_import_opens_unsaved_document_with_rebased_image(self):
        image = self.root / "reference.png"
        Image.new("RGB", (6, 6), "red").save(image)
        package = self.root / "transfer.mrpkg"
        export_package(package, serialize_document(
            [Action(kind="click_image", image_path=str(image))], 3, 1.5))
        self.window._replace_actions([Action(kind="wait")])
        self.window._mark_clean()
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(package), "Macro packages (*.mrpkg)")), patch(
                "macro_qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes):
            self.window.import_workflow_package()
        self.assertEqual([action.kind for action in self.window.actions], ["click_image"])
        self.assertTrue(Path(self.window.actions[0].image_path).is_file())
        self.assertEqual(self.window.repeats.value(), 3)
        self.assertEqual(self.window.delay.value(), 1.5)
        self.assertTrue(self.window._is_dirty())
        self.assertIsNone(self.window.current_file)
        # Ordinary JSON remains usable, with no package schema migration.
        dest = self.root / "saved.json"
        with patch("macro_qt.QFileDialog.getSaveFileName",
                   return_value=(str(dest), "Macro files (*.json)")):
            self.assertTrue(self.window.save_workflow())
        self.assertEqual(parse_document(json.loads(dest.read_text()))[0],
                         self.window.actions)

    def test_rejected_package_does_not_replace_open_document(self):
        package = self.root / "bad.mrpkg"
        package.write_bytes(b"not a zip archive")
        self.window._replace_actions([Action(kind="wait", seconds=9)])
        self.window._mark_clean()
        before = list(self.window.actions)
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(package), "Macro packages (*.mrpkg)")), patch(
                "macro_qt.QMessageBox.warning") as warning:
            self.window.import_workflow_package()
        warning.assert_called_once()
        self.assertEqual(self.window.actions, before)
        self.assertFalse(self.window._is_dirty())
        self.assertFalse(self.window.package_assets_dir.exists())

    def test_cancel_import_does_not_write_assets_or_change_workflow(self):
        image = self.root / "reference.png"
        Image.new("RGB", (6, 6), "blue").save(image)
        package = self.root / "transfer.mrpkg"
        export_package(package, serialize_document([
            Action(kind="click_image", image_path=str(image))], 1, 0))
        self.window._replace_actions([Action(kind="wait")])
        self.window._mark_clean()
        before = list(self.window.actions)
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(package), "Macro packages (*.mrpkg)")), patch(
                "macro_qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No):
            self.window.import_workflow_package()
        self.assertEqual(self.window.actions, before)
        self.assertFalse(self.window.package_assets_dir.exists())


if __name__ == "__main__":
    unittest.main()
