"""Offscreen Qt OCR inspector and read-only preview coverage."""
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication, QCheckBox

from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_ocr import OCRPreviewDialog
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class OCRQtTests(unittest.TestCase):
    def setUp(self):
        # OCR inspector tests do not need global native X11 keyboard listeners.
        with patch.object(MacroWindow, "_start_hotkeys"):
            self.window = MacroWindow()

    def tearDown(self):
        close_test_window(self.window)

    def test_actions_have_editable_phrase_language_and_region(self):
        self.window.inspector.show_action(Action(kind="find_text", text_target="Sign In"))
        panel = self.window.inspector
        self.assertIn("text_target", panel.controls)
        self.assertIsInstance(panel.controls["text_click"], QCheckBox)
        self.assertEqual(panel.controls["text_language"].text(), "eng")
        self.assertFalse(panel.controls["text_click"].isChecked())
        panel.controls["text_click"].setChecked(True)
        panel.controls["region_x"].setText("10")
        panel.controls["region_y"].setText("20")
        panel.controls["region_w"].setText("80")
        panel.controls["region_h"].setText("50")
        action = panel._read_action()
        self.assertTrue(action.text_click)
        self.assertEqual((action.region_x, action.region_y,
                          action.region_w, action.region_h), (10, 20, 80, 50))

    def test_wait_text_can_retry_but_cannot_click(self):
        self.window.inspector.show_action(
            Action(kind="wait_text", text_target="Ready", failure_policy="retry"))
        p = self.window.inspector
        self.assertNotIn("text_click", p.controls)
        self.assertEqual(p.controls["failure_policy"].currentText(), "retry")
        self.assertEqual(p._read_action().kind, "wait_text")

    def test_preview_uses_unsaved_fields_and_not_application_execution(self):
        self.window.inspector.show_action(Action(kind="find_text", text_target="before"))
        self.window.inspector.controls["text_target"].setText("after")
        captured = []
        self.window.inspector.preview_text.connect(captured.append)
        with patch("macro_qt_properties.QMessageBox.warning") as warning:
            self.window.inspector._preview_text()
        warning.assert_not_called()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].text_target, "after")
        self.assertEqual(self.window.inspector.current.text_target, "before")

    def test_dialog_displays_match_without_starting_worker(self):
        dialog = OCRPreviewDialog(Action(kind="find_text", text_target="Ready"))
        try:
            self.assertIsNone(dialog.worker)
            dialog._frame({"image": Image.new("RGB", (120, 50)),
                           "match": None})
            self.assertIn("not found", dialog.status.text())
            self.assertIsNotNone(dialog.picture.pixmap())
        finally:
            dialog.close()

    def test_palette_registers_both_ocr_actions(self):
        from macro_qt_workflow import KINDS
        self.assertIn(("Find text (offline OCR)", "find_text"), KINDS)
        self.assertIn(("Wait for text (offline OCR)", "wait_text"), KINDS)


if __name__ == "__main__":
    unittest.main()
