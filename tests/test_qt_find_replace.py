"""Offscreen search navigation, highlighting, and atomic Qt editor bulk edits."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from macro_editing import ActionHistory
from macro_find_replace import plan_replacements
from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_find_replace import WorkflowFindReplaceDialog
from macro_recovery import RecoveryStore
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class WorkflowFindReplaceQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # A read-only find dialog never needs global keyboard hooks.
        with patch.object(MacroWindow, "_start_hotkeys"):
            self.window = MacroWindow()
        self.window.recovery_store = RecoveryStore(self.root / "recovery.json")
        self.window._replace_actions([
            Action(kind="if_start", condition_source="pixel", name="Check"),
            Action(kind="key", keys="ctrl+s", name="Save One"),
            Action(kind="wait", seconds=1),
            Action(kind="else"),
            Action(kind="key", keys="ctrl+s", name="Save Two"),
            Action(kind="if_end"),
        ])
        self.window._mark_clean()
        self.window.history = ActionHistory(60)
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.reject()
            dialog.deleteLater()
        close_test_window(self.window)

    def dialog(self):
        dialog = WorkflowFindReplaceDialog(
            self.window.actions, self.window.variables, self.root,
            self.window.tree.highlight_search_matches,
            self.window.tree.jump_to_action,
            self.window._apply_find_replace, self.window)
        self.dialogs.append(dialog)
        return dialog

    def test_ctrl_f_menu_action_available(self):
        self.assertEqual(self.window.find_replace_action.shortcut().toString(), "Ctrl+F")
        self.assertTrue(self.window.find_replace_action.isEnabled())

    def test_search_nested_action_highlights_and_reveals_collapsed_group(self):
        tree = self.window.tree
        tree.topLevelItem(0).setExpanded(False)
        d = self.dialog()
        d.search.setText("Save Two")
        d.scope.setCurrentIndex(d.scope.findData("name"))
        d.refresh_search()
        self.assertEqual(d.result_label.text(), "1 action(s) matched.")
        self.assertEqual(d.results.count(), 1)
        match_item = tree.index_map()[4]
        self.assertNotEqual(match_item.background(0).style(), 0)
        d._jump(d.results.item(0))
        self.assertTrue(tree.topLevelItem(0).isExpanded())
        self.assertTrue(match_item.isSelected())
        d.reject()
        self.assertEqual(len(tree._search_highlights), 0)
        self.assertEqual(tree.actions(), self.window.actions)

    def test_preview_does_not_edit_and_apply_is_one_undo(self):
        d = self.dialog()
        d.search.setText("Save")
        d.scope.setCurrentIndex(d.scope.findData("name"))
        d.refresh_search()
        d.field.setCurrentIndex(d.field.findData("name"))
        d.mode.setCurrentIndex(d.mode.findData("replace"))
        d.find_text.setText("Save")
        d.value.setText("Export")
        self.assertFalse(d.apply_button.isEnabled())
        d.preview()
        self.assertEqual(len(d.plan.changes), 2)
        self.assertTrue(d.apply_button.isEnabled())
        self.assertEqual(self.window.actions[1].name, "Save One")
        self.assertFalse(self.window.history.can_undo)
        d.apply()
        self.assertEqual([self.window.actions[i].name for i in (1, 4)],
                         ["Export One", "Export Two"])
        self.assertEqual(len(self.window.history.past), 1)
        self.window.undo()
        self.assertEqual([self.window.actions[i].name for i in (1, 4)],
                         ["Save One", "Save Two"])
        self.assertFalse(self.window.history.can_undo)
        self.window.redo()
        self.assertEqual(self.window.actions[1].name, "Export One")

    def test_replacement_preserves_tree_breakpoints_and_nonmatching_nodes(self):
        tree = self.window.tree
        child = tree.index_map()[1]
        child.setSelected(True)
        tree.toggle_breakpoints()
        self.assertEqual(tree.breakpoint_indices(), {1})
        d = self.dialog()
        d.search.setText("Save")
        d.scope.setCurrentIndex(d.scope.findData("name"))
        d.refresh_search()
        d.field.setCurrentIndex(d.field.findData("keys"))
        d.value.setText("ctrl+p")
        d.preview()
        d.apply()
        self.assertEqual(tree.breakpoint_indices(), {1})
        self.assertEqual(self.window.actions[2].seconds, 1)
        self.assertEqual(self.window.actions[1].keys, "ctrl+p")
        self.assertEqual(self.window.actions[4].keys, "ctrl+p")

    def test_invalid_preview_and_cancel_never_change_workflow(self):
        d = self.dialog()
        original = list(self.window.actions)
        d.search.setText("Save")
        d.scope.setCurrentIndex(d.scope.findData("name"))
        d.refresh_search()
        d.field.setCurrentIndex(d.field.findData("keys"))
        d.value.setText("")
        d.preview()
        self.assertFalse(d.apply_button.isEnabled())
        self.assertIn("Action 2", d.preview_label.text())
        d.reject()
        self.assertEqual(self.window.actions, original)
        self.assertFalse(self.window.history.can_undo)
        self.assertFalse(self.window._is_dirty())

    def test_structural_markers_cannot_be_modified_even_if_passed_directly(self):
        tree = self.window.tree
        original = list(self.window.actions)
        changed = list(original)
        from dataclasses import replace
        changed[1] = replace(changed[1], name="changed")
        changed[3] = replace(changed[3], name="bad")
        with self.assertRaisesRegex(ValueError, "Structural"):
            tree.apply_bulk_replacements(changed, [1, 3])
        self.assertEqual(tree.actions(), original)
        self.assertEqual(self.window.actions, original)

    def test_bulk_numeric_search_updates_only_compatible_items(self):
        tree = self.window.tree
        d = self.dialog()
        d.scope.setCurrentIndex(d.scope.findData("kind"))
        d.search.setText("wait")
        d.refresh_search()
        d.field.setCurrentIndex(d.field.findData("seconds"))
        d.value.setText("2.5")
        d.preview()
        self.assertEqual(len(d.plan.changes), 1)
        d.apply()
        self.assertEqual(tree.actions()[2].seconds, 2.5)
        self.assertEqual(self.window.actions[1].keys, "ctrl+s")


if __name__ == "__main__":
    unittest.main()
