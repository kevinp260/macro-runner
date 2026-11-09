"""Region drawing and watch inspector tests (headless Qt)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from macro_model import Action
from macro_qt_properties import PropertiesPanel
from macro_qt_region import (RegionOverlay, RegionPicker, normalized_region,
                             save_reference_capture)
from macro_qt_workflow import WorkflowTree
from macro_qt import MacroWindow
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class RegionUITests(unittest.TestCase):
    def test_drag_coordinates_normalize_in_both_directions(self):
        self.assertEqual(normalized_region(QPoint(120, 180), QPoint(20, 30)),
                         (20, 30, 100, 150))
        self.assertEqual(normalized_region(QPoint(20, 30), QPoint(120, 180)),
                         (20, 30, 100, 150))

    def test_drag_records_native_pointer_pixels_not_qt_logical_position(self):
        # Simulate Qt logical coordinates on a scaled desktop: a 20x20 Qt
        # drag corresponds to a 60x40 rectangle in physical screenshot pixels.
        class Mouse:
            def __init__(self, x, y):
                self.point = QPointF(x, y)
            def button(self):
                return Qt.MouseButton.LeftButton
            def position(self):
                return self.point

        screen = QApplication.primaryScreen()
        overlay = RegionOverlay(screen)
        selected = []
        overlay.selected.connect(lambda *rect: selected.append(rect))
        try:
            with patch.object(overlay, "_pointer_pixel",
                              side_effect=[QPoint(400, 210), QPoint(460, 250)]):
                overlay.mousePressEvent(Mouse(10, 12))
                overlay.mouseReleaseEvent(Mouse(30, 32))
            self.assertEqual(selected, [(400, 210, 60, 40)])
        finally:
            overlay.close()

    def test_inspector_draw_button_populates_fields_and_saves(self):
        panel = PropertiesPanel()
        panel.show_action(Action(kind="watch_start", region_x=0, region_y=0,
                                 region_w=200, region_h=100))
        buttons = [b for b in panel.findChildren(QPushButton)
                   if b.text() == "Draw screen region…"]
        self.assertEqual(len(buttons), 1)
        signals = []
        panel.pick_region.connect(lambda: signals.append(True))
        buttons[0].click()
        self.assertEqual(signals, [True])
        panel.update_picked_region(30, 40, 80, 90)
        saved = []
        panel.apply_action.connect(saved.append)
        panel.commit()
        self.assertEqual(
            (saved[0].region_x, saved[0].region_y,
             saved[0].region_w, saved[0].region_h),
            (30, 40, 80, 90))

    def test_region_picker_is_available_for_image_conditions_and_ocr(self):
        panel = PropertiesPanel()
        signals = []
        panel.pick_region.connect(lambda: signals.append(True))
        try:
            for kind in ("click_image", "wait_until", "if_start",
                         "until_start", "find_text", "wait_text", "watch_start"):
                with self.subTest(kind=kind):
                    panel.show_action(Action(kind=kind))
                    button = panel.region_draw
                    self.assertIsNotNone(button)
                    self.assertEqual(button.text(), "Draw screen region…")
                    self.assertGreaterEqual(panel.form.getWidgetPosition(button)[0], 0)
                    self.assertTrue(button.isEnabled())
                    previous = len(signals)
                    button.click()
                    self.assertEqual(len(signals), previous + 1)
                    panel.update_picked_region(30, 40, 80, 90)
                    self.assertEqual(
                        [panel.controls[name].text()
                         for name in ("region_x", "region_y",
                                      "region_w", "region_h")],
                        ["30", "40", "80", "90"])
            panel.show_action(Action(kind="loop_start"))
            self.assertIsNone(panel.region_draw)
        finally:
            panel.close()

    def test_pixel_conditions_disable_region_picker(self):
        panel = PropertiesPanel()
        try:
            for kind in ("wait_until", "if_start", "until_start"):
                with self.subTest(kind=kind):
                    panel.show_action(Action(kind=kind,
                                             condition_source="pixel"))
                    self.assertIsNotNone(panel.region_draw)
                    self.assertFalse(panel.region_draw.isEnabled())
                    panel.controls["condition_source"].setCurrentText("image")
                    self.assertTrue(panel.region_draw.isEnabled())
                    panel.controls["condition_source"].setCurrentText("pixel")
                    self.assertFalse(panel.region_draw.isEnabled())
        finally:
            panel.close()

    def test_capture_and_browse_buttons_on_image_matching_actions(self):
        panel = PropertiesPanel()
        captured = []
        panel.capture_reference_image.connect(lambda: captured.append(True))
        try:
            for kind in ("click_image", "wait_until", "if_start", "until_start"):
                with self.subTest(kind=kind):
                    panel.show_action(Action(kind=kind, image_path="old.png"))
                    self.assertEqual(panel.capture_button.text(), "Capture…")
                    self.assertTrue(panel.capture_button.isEnabled())
                    panel.capture_button.click()
                    self.assertEqual(len(captured), 1 + (
                        ("click_image", "wait_until", "if_start", "until_start").index(kind)))
                    self.assertEqual(panel.controls["image_path"].text(), "old.png")
                    panel.update_captured_image("/tmp/new-ref.png")
                    self.assertEqual(panel.controls["image_path"].text(),
                                     "/tmp/new-ref.png")
                    self.assertEqual(panel.controls["region_x"].text(), "")
            for kind in ("wait_until", "if_start", "until_start"):
                panel.show_action(Action(kind=kind, condition_source="pixel"))
                self.assertFalse(panel.capture_button.isEnabled())
                panel.controls["condition_source"].setCurrentText("image")
                self.assertTrue(panel.capture_button.isEnabled())
            panel.show_action(Action(kind="watch_start"))
            self.assertIsNone(panel.capture_button)
        finally:
            panel.close()

    def test_click_image_can_be_added_before_choosing_reference(self):
        tree = WorkflowTree()
        try:
            tree.insert_kind("click_image")
            actions = tree.actions()
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].kind, "click_image")
            self.assertEqual(actions[0].image_path, "")
        finally:
            tree.close()

    def test_captured_png_is_unique_and_failed_save_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (24, 12), "red")
            first = Path(save_reference_capture(image, directory))
            second = Path(save_reference_capture(image, directory))
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file())
            with Image.open(first) as saved:
                self.assertEqual(saved.size, (24, 12))
            self.assertEqual(first.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

            class BrokenImage:
                def save(self, target, format):
                    Path(target).write_bytes(b"incomplete")
                    raise OSError("save failed")

            with self.assertRaisesRegex(OSError, "save failed"):
                save_reference_capture(BrokenImage(), directory)
            self.assertEqual(sorted(Path(directory).iterdir()), sorted([first, second]))

    def test_desktop_capture_assigns_reference_without_changing_search_region(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MacroWindow, "_start_hotkeys"):
                window = MacroWindow()
            window.capture_assets_dir = Path(directory)
            try:
                window.inspector.show_action(
                    Action(kind="click_image", image_path="existing.png",
                           region_x=5, region_y=6, region_w=100, region_h=80))
                pending = []
                screenshot = Image.new("RGB", (20, 15), "blue")
                with patch("macro_qt.QTimer.singleShot",
                           side_effect=lambda _, callback: pending.append(callback)), \
                        patch("pyautogui.screenshot", return_value=screenshot) as grab:
                    window.inspector.capture_button.click()
                    self.assertTrue(window._screen_selection_active)
                    pending.pop(0)()  # Show the picker after hiding editor.
                    self.assertIsNotNone(window.region_picker)
                    window.region_picker._finish(20, 30, 20, 15)
                    self.assertIsNone(window.region_picker)
                    pending.pop(0)()  # Screenshot only after overlay closes.
                    grab.assert_called_once_with(region=(20, 30, 20, 15))
                path = Path(window.inspector.controls["image_path"].text())
                self.assertTrue(path.is_file())
                self.assertEqual(path.parent, Path(directory))
                self.assertEqual(window.inspector.controls["region_x"].text(), "5")
                self.assertEqual(window.inspector.controls["region_y"].text(), "6")
                self.assertFalse(window._screen_selection_active)
            finally:
                close_test_window(window)

    def test_cancelled_or_failed_capture_preserves_existing_reference(self):
        with patch.object(MacroWindow, "_start_hotkeys"):
            window = MacroWindow()
        try:
            window.inspector.show_action(
                Action(kind="wait_until", image_path="keep.png"))
            pending = []
            with patch("macro_qt.QTimer.singleShot",
                       side_effect=lambda _, callback: pending.append(callback)):
                window.inspector.capture_button.click()
                pending.pop(0)()
                window.region_picker.cancel()
                self.assertFalse(window._screen_selection_active)
                self.assertEqual(window.inspector.controls["image_path"].text(), "keep.png")

                window.inspector.capture_button.click()
                pending.pop(0)()
                window.region_picker._finish(10, 20, 20, 15)
                with patch("pyautogui.screenshot", side_effect=PermissionError("denied")), \
                        patch("macro_qt.QMessageBox.warning") as warn:
                    pending.pop(0)()
                self.assertTrue(warn.called)
                self.assertFalse(window._screen_selection_active)
                self.assertEqual(window.inspector.controls["image_path"].text(), "keep.png")
        finally:
            close_test_window(window)

    def test_picker_completion_and_cancellation(self):
        selected = []
        cancelled = []
        picker = RegionPicker(lambda *rect: selected.append(rect),
                              lambda: cancelled.append(True))
        self.assertTrue(picker.overlays)
        picker._finish(10, 20, 30, 40)
        self.assertEqual(selected, [(10, 20, 30, 40)])
        self.assertFalse(picker.overlays)
        picker2 = RegionPicker(lambda *rect: selected.append(rect),
                               lambda: cancelled.append(True))
        picker2.cancel()
        self.assertEqual(cancelled, [True])
        self.assertEqual(len(selected), 1)
        picker3 = RegionPicker(lambda *rect: selected.append(rect),
                               lambda: cancelled.append(True))
        picker3.cancel(notify=False)
        self.assertEqual(cancelled, [True])
        self.assertFalse(picker3.overlays)


if __name__ == "__main__":
    unittest.main()
