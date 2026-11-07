from qt_test_helpers import close_test_window
"""Offscreen Qt pre-run confirmation and navigation tests."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from macro_model import Action
from macro_preflight import PreflightFinding
from macro_qt_preflight import PreflightDialog
from macro_qt import MacroWindow

app = QApplication.instance() or QApplication([])


class PreflightUITests(unittest.TestCase):
    def test_errors_have_navigation_but_cannot_run(self):
        dialog = PreflightDialog([
            PreflightFinding("error", 2, "Missing reference image"),
            PreflightFinding("warning", None, "Wayland input warning"),
        ])
        try:
            self.assertTrue(dialog.has_errors)
            self.assertIsNone(dialog.run_button)
            self.assertEqual(dialog.table.topLevelItemCount(), 2)
            self.assertEqual(dialog.table.currentItem().text(1), "#3")
            self.assertTrue(dialog.goto_button.isEnabled())
            dialog.go_to_action()
            self.assertEqual(dialog.navigation_index, 2)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        finally:
            dialog.close()

    def test_warning_requires_explicit_acceptance(self):
        dialog = PreflightDialog([
            PreflightFinding("warning", None, "Wayland input warning"),
            PreflightFinding("warning", 0, "Off primary display"),
        ])
        try:
            self.assertFalse(dialog.has_errors)
            self.assertIsNotNone(dialog.run_button)
            self.assertFalse(dialog.goto_button.isEnabled())
            self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
            dialog.table.setCurrentItem(dialog.table.topLevelItem(1))
            self.assertTrue(dialog.goto_button.isEnabled())
            dialog.run_button.click()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        finally:
            dialog.close()

    def test_main_window_navigates_to_nested_action(self):
        window = MacroWindow()
        try:
            actions = [
                Action(kind="loop_start"), Action(kind="click", x=5, y=10),
                Action(kind="loop_end"), Action(kind="wait")]
            window._replace_actions(actions)
            fake_dialog = SimpleNamespace(
                exec=lambda: QDialog.DialogCode.Rejected,
                has_errors=True, navigation_index=1)
            fake_pag = SimpleNamespace(size=lambda: (100, 100))
            with patch.dict(sys.modules, {"pyautogui": fake_pag}), patch(
                "macro_qt.inspect_workflow",
                return_value=[PreflightFinding("error", 1, "Invalid location")]), patch(
                "macro_qt.PreflightDialog", return_value=fake_dialog):
                self.assertFalse(window._validate_before_run(0))
            self.assertIs(window.tree.currentItem(), window.tree.index_map()[1])
            self.assertEqual(window.inspector.current.kind, "click")
        finally:
            close_test_window(window)

    def test_run_and_step_cannot_start_when_blocked_or_cancelled(self):
        window = MacroWindow()
        try:
            window._replace_actions([Action(kind="wait", seconds=0)])
            with patch.object(window, "_validate_before_run", return_value=False) as guard, patch(
                    "macro_qt.MacroExecutor") as executor:
                window.run_workflow()
                window.step_run()
                self.assertEqual(guard.call_count, 2)
                executor.assert_not_called()
                self.assertIsNone(window.executor)
                self.assertIsNone(window._run_session)
        finally:
            close_test_window(window)

    def test_main_window_confirmed_warning_does_not_create_extra_editor_changes(self):
        window = MacroWindow()
        try:
            window._replace_actions([Action(kind="click", x=150, y=25)])
            history_before = window.actions[:]
            fake_pag = SimpleNamespace(size=lambda: (100, 100))
            dialog = SimpleNamespace(
                exec=lambda: QDialog.DialogCode.Accepted,
                has_errors=False, navigation_index=None)
            with patch.dict(sys.modules, {"pyautogui": fake_pag}), patch(
                "macro_qt.PreflightDialog", return_value=dialog) as shown:
                self.assertTrue(window._validate_before_run(0))
                self.assertEqual(shown.call_args.args[0][0].severity, "warning")
            self.assertEqual(window.actions, history_before)
        finally:
            close_test_window(window)


if __name__ == "__main__":
    unittest.main()
