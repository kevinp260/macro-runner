"""Region drawing and watch inspector tests (headless Qt)."""
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from macro_model import Action
from macro_qt_properties import PropertiesPanel
from macro_qt_region import RegionOverlay, RegionPicker, normalized_region

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
                    buttons = [w for w in panel.findChildren(QPushButton)
                               if w.text() == "Draw screen region…"]
                    self.assertEqual(len(buttons), 1)
                    self.assertTrue(buttons[0].isEnabled())
                    previous = len(signals)
                    buttons[0].click()
                    self.assertEqual(len(signals), previous + 1)
                    panel.update_picked_region(30, 40, 80, 90)
                    self.assertEqual(
                        [panel.controls[name].text()
                         for name in ("region_x", "region_y",
                                      "region_w", "region_h")],
                        ["30", "40", "80", "90"])
            panel.show_action(Action(kind="loop_start"))
            self.assertIsNone(panel.region_draw)
            self.assertFalse(any(
                w.text() == "Draw screen region…"
                for w in panel.findChildren(QPushButton)))
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
