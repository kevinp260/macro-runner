import unittest
from PySide6.QtWidgets import QApplication
from macro_model import Action
from macro_qt_properties import fields_for_kind, convert, PropertiesPanel

app = QApplication.instance() or QApplication([])


class PropertiesTests(unittest.TestCase):
    def test_all_action_kinds_have_fields(self):
        self.assertIn("keys", fields_for_kind("key_down"))
        self.assertIn("pixel_color", fields_for_kind("if_start"))
        self.assertNotIn("condition_source", fields_for_kind("wait"))
        self.assertEqual(convert("region_x", ""), None)
        self.assertEqual(convert("pixel_x", "14"), 14)
        self.assertAlmostEqual(convert("confidence", "0.85"), .85)

    def test_scrollable_inspector_validates_and_emits(self):
        p = PropertiesPanel()
        p.show_action(Action(kind="wait", seconds=1))
        changed = []
        p.apply_action.connect(changed.append)
        p.controls["seconds"].setText("2.5")
        p.commit()
        self.assertEqual(changed[0].seconds, 2.5)

    def test_visual_control_reconfiguration(self):
        p = PropertiesPanel()
        p.show_action(Action(kind="wait_until", condition_source="pixel"))
        self.assertFalse(p.controls["image_path"].isEnabled())
        self.assertTrue(p.controls["pixel_color"].isEnabled())
        p.controls["condition_source"].setCurrentText("image")
        self.assertTrue(p.controls["image_path"].isEnabled())
        self.assertFalse(p.controls["pixel_color"].isEnabled())
