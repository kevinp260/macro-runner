"""Region drawing and watch inspector tests (headless Qt)."""
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QPushButton

from macro_model import Action
from macro_qt_properties import PropertiesPanel
from macro_qt_region import RegionPicker, normalized_region

app = QApplication.instance() or QApplication([])


class RegionUITests(unittest.TestCase):
    def test_drag_coordinates_normalize_in_both_directions(self):
        self.assertEqual(normalized_region(QPoint(120, 180), QPoint(20, 30)),
                         (20, 30, 100, 150))
        self.assertEqual(normalized_region(QPoint(20, 30), QPoint(120, 180)),
                         (20, 30, 100, 150))

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


if __name__ == "__main__":
    unittest.main()
