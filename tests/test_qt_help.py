"""Offscreen Qt tests for the local searchable Help dialog and menu."""
import unittest
from unittest.mock import patch

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from macro_help import BY_ID
from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_help import HelpDialog
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class HelpDialogTests(unittest.TestCase):
    def test_help_dialog_search_and_categories(self):
        dialog = HelpDialog()
        try:
            self.assertGreater(dialog.results.count(), 40)
            dialog.search.setText("DEBUG GAP")
            self.assertEqual(dialog.count.text(), "1 topic(s)")
            self.assertEqual(
                dialog.results.currentItem().data(
                    dialog.results.currentItem().data.__self__ if False else
                    __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ItemDataRole.UserRole),
                "debug-gap")
            self.assertIn("extra pause", dialog.article.toPlainText())

            dialog.search.clear()
            dialog.category.setCurrentText("Action reference")
            self.assertEqual(dialog.results.count(),
                             sum(t.category == "Action reference" for t in BY_ID.values()))
            dialog.search.setText("no_such_help_topic")
            self.assertEqual(dialog.results.count(), 0)
            self.assertIn("No matching help topics", dialog.article.toPlainText())
        finally:
            dialog.close()

    def test_direct_topic_navigation_resets_filters(self):
        dialog = HelpDialog()
        try:
            dialog.category.setCurrentText("Troubleshooting")
            dialog.search.setText("file")
            dialog.open_topic("breakpoint")
            self.assertEqual(dialog.search.text(), "")
            self.assertEqual(dialog.category.currentText(), "All topics")
            self.assertIn("temporary stop sign", dialog.article.toPlainText())
            self.assertTrue(dialog.isVisible())
            dialog.open_topic("debug-gap")
            self.assertIn("extra pause", dialog.article.toPlainText())
        finally:
            dialog.close()


class HelpMenuTests(unittest.TestCase):
    def setUp(self):
        # A Help dialog does not exercise global system keyboard hooks.
        with patch.object(MacroWindow, "_start_hotkeys"):
            self.window = MacroWindow()

    def tearDown(self):
        if self.window.help_dialog is not None:
            self.window.help_dialog.close()
        close_test_window(self.window)

    def test_f1_guide_and_about_remain_accessible(self):
        actions = self.window.findChildren(QAction)
        guides = [action for action in actions if action.text() == "User Guide…"]
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0].shortcut().toString(), "F1")
        self.assertTrue(any(action.text() == "About MacroRunner"
                            for action in actions))
        self.window.show_help()
        self.assertIsNotNone(self.window.help_dialog)
        self.assertTrue(self.window.help_dialog.isVisible())
        self.assertIn("What is MacroRunner?", self.window.help_dialog.article.toPlainText())
        self.assertFalse(self.window._busy())
        self.window.help_dialog.close()
        self.assertIsNone(self.window.help_dialog)

    def test_help_for_selected_action(self):
        self.window._replace_actions([Action(kind="wait", seconds=2)])
        item = self.window.tree.topLevelItem(0)
        item.setSelected(True)
        self.window.help_selected_action()
        self.assertIn("Wait", self.window.help_dialog.article.toPlainText())
        self.assertIn("fixed number of seconds",
                      self.window.help_dialog.article.toPlainText())
        self.assertEqual(self.window.actions[0].seconds, 2)

    def test_searching_help_never_changes_workflow_or_history(self):
        self.window._replace_actions([Action(kind="key", keys="hello")])
        before = list(self.window.actions)
        self.window.history.past.clear()
        self.window.show_help()
        guide = self.window.help_dialog
        guide.search.setText("debug gap")
        guide.category.setCurrentText("Running and debugging")
        guide.refresh()
        self.assertEqual(before, self.window.actions)
        self.assertFalse(self.window.history.can_undo)


if __name__ == "__main__":
    unittest.main()
