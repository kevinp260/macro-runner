"""Headless Qt coverage for new failure policy controls and visibility."""
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from macro_model import Action
from macro_qt_properties import PropertiesPanel, fields_for_kind
from macro_qt_workflow import description

app = QApplication.instance() or QApplication([])


class FailurePolicyUITests(unittest.TestCase):
    def test_controls_only_on_executable_actions(self):
        self.assertIn("failure_policy", fields_for_kind("wait"))
        self.assertNotIn("retry_count", fields_for_kind("wait"))
        self.assertIn("retry_count", fields_for_kind("wait_until"))
        self.assertIn("retry_delay", fields_for_kind("click_image"))
        self.assertNotIn("failure_policy", fields_for_kind("if_start"))
        self.assertNotIn("failure_policy", fields_for_kind("watch_start"))

    def test_wait_until_retries_are_visible_only_when_selected(self):
        p = PropertiesPanel()
        try:
            action = Action(kind="wait_until", condition_source="pixel")
            p.show_action(action)
            policy = p.controls["failure_policy"]
            self.assertEqual(policy.currentText(), "stop")
            self.assertEqual(policy.count(), 3)
            self.assertTrue(p.controls["retry_count"].isHidden())
            self.assertTrue(p.controls["retry_delay"].isHidden())
            policy.setCurrentText("retry")
            self.assertFalse(p.controls["retry_count"].isHidden())
            self.assertFalse(p.controls["retry_delay"].isHidden())
            p.controls["retry_count"].setText("3")
            p.controls["retry_delay"].setText("0.25")
            submitted = []
            p.apply_action.connect(submitted.append)
            p.commit()
            self.assertEqual(submitted[0].failure_policy, "retry")
            self.assertEqual(submitted[0].retry_count, 3)
            self.assertEqual(submitted[0].retry_delay, .25)
            policy.setCurrentText("skip")
            self.assertTrue(p.controls["retry_count"].isHidden())
            self.assertTrue(p.controls["retry_delay"].isHidden())
            p.commit()
            self.assertEqual(submitted[1].failure_policy, "skip")
            self.assertEqual(action.failure_policy, "stop")  # No automatic edit.
        finally:
            p.close()

    def test_side_effecting_actions_offer_stop_or_skip_not_retry(self):
        p = PropertiesPanel()
        try:
            p.show_action(Action(kind="click", x=1, y=2))
            policy = p.controls["failure_policy"]
            self.assertEqual([policy.itemText(i) for i in range(policy.count())],
                             ["stop", "skip"])
            policy.setCurrentText("skip")
            saved = []
            p.apply_action.connect(saved.append)
            p.commit()
            self.assertEqual(saved[0].failure_policy, "skip")
            self.assertIn("skip on error", description(saved[0]))
            self.assertIn("retry 3×", description(
                Action(kind="wait_until", failure_policy="retry",
                       retry_count=3, condition_source="pixel")))
        finally:
            p.close()

    def test_invalid_retry_form_does_not_apply(self):
        p = PropertiesPanel()
        try:
            p.show_action(Action(kind="wait_until", condition_source="pixel"))
            p.controls["failure_policy"].setCurrentText("retry")
            p.controls["retry_count"].setText("0")
            applied, warnings = [], []
            p.apply_action.connect(applied.append)
            with patch.object(QMessageBox, "warning",
                              side_effect=lambda *a: warnings.append(a)):
                p.commit()
            self.assertEqual(applied, [])
            self.assertEqual(len(warnings), 1)
            self.assertIn("at least one", warnings[0][2])
        finally:
            p.close()


if __name__ == "__main__":
    unittest.main()
