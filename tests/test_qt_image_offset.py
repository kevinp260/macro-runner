"""Offscreen Qt image-click offset inspector and read-only preview tests."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_properties import PropertiesPanel
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class ImageOffsetQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "reference.png"
        self.path.write_bytes(b"only a placeholder for mocked matching")
        self.window = MacroWindow()

    def tearDown(self):
        close_test_window(self.window)

    def select(self, action=None):
        action = action or Action(kind="click_image", image_path=str(self.path))
        self.window._replace_actions([action])
        self.window.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        return self.window.inspector

    def test_offsets_apply_and_round_trip_with_undo(self):
        panel = self.select()
        self.assertEqual(panel.controls["image_offset_x"].text(), "0")
        self.assertEqual(panel.controls["image_offset_y"].text(), "0")
        panel.controls["image_offset_x"].setText("-18")
        panel.controls["image_offset_y"].setText("35")
        panel.commit()
        self.assertEqual(self.window.actions[0].image_offset_x, -18)
        self.assertEqual(self.window.actions[0].image_offset_y, 35)
        self.window.undo()
        self.assertEqual(self.window.actions[0].image_offset_x, 0)
        self.window.redo()
        self.assertEqual(self.window.actions[0].image_offset_x, -18)

    def test_invalid_offset_rejected_before_apply(self):
        panel = self.select()
        panel.controls["image_offset_x"].setText("4.5")
        with patch("macro_qt_properties.QMessageBox.warning") as warning:
            panel.commit()
        warning.assert_called_once()
        self.assertEqual(self.window.actions[0].image_offset_x, 0)

    def test_preview_uses_unsaved_offset_and_does_not_click(self):
        panel = self.select()
        panel.controls["image_offset_x"].setText("12")
        panel.controls["image_offset_y"].setText("-7")
        mouse = SimpleNamespace(size=lambda: (400, 300),
                                screenshot=lambda region=None: object(),
                                click=lambda *a, **k: self.fail("Preview clicked"))
        with patch("macro_qt.get_automation", return_value=mouse), patch(
                "macro_qt.locate_image", return_value=(100, 80, .982)) as matching, patch(
                "macro_qt.QMessageBox.information") as info:
            panel._preview_image_click()
        matching.assert_called_once()
        info.assert_called_once()
        message = info.call_args.args[2]
        self.assertIn("(112, 73)", message)
        self.assertIn("(+12, -7)", message)
        self.assertIn("98.2%", message)
        self.assertEqual(self.window.actions[0].image_offset_x, 0)

    def test_preview_failure_and_offscreen_show_warning_without_click(self):
        panel = self.select()
        mouse = SimpleNamespace(size=lambda: (200, 150),
                                screenshot=lambda region=None: object())
        with patch("macro_qt.get_automation", return_value=mouse), patch(
                "macro_qt.locate_image", return_value=None), patch(
                "macro_qt.QMessageBox.warning") as warning:
            panel._preview_image_click()
        self.assertIn("No image match", warning.call_args.args[1])

        panel.controls["image_offset_x"].setText("300")
        with patch("macro_qt.get_automation", return_value=mouse), patch(
                "macro_qt.locate_image", return_value=(100, 80, .99)), patch(
                "macro_qt.QMessageBox.warning") as warning:
            panel._preview_image_click()
        self.assertIn("primary screen", warning.call_args.args[2])

    def test_preview_refused_during_macro_execution(self):
        panel = self.select()
        self.window.record_pending = True
        with patch("macro_qt.locate_image") as locate, patch(
                "macro_qt.QMessageBox.warning") as warning:
            panel._preview_image_click()
        locate.assert_not_called()
        self.assertIn("Stop the current", warning.call_args.args[2])
        self.window.record_pending = False


if __name__ == "__main__":
    unittest.main()
