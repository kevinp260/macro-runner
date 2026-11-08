"""Offscreen snippet insertion, history, preview and structured tree integration."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication, QEvent

from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_snippets import SnippetLibraryDialog, snippet_preview
from macro_recovery import RecoveryStore
from macro_snippets import SnippetStore, make_snippet
from qt_test_helpers import close_test_window


app = QApplication.instance() or QApplication([])


def defs(name, kind, default):
    return {"name": name, "type": kind, "default": default}


class SnippetQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.window = MacroWindow()
        self.window.snippet_store = SnippetStore(self.root / "snippets")
        self.window.recovery_store = RecoveryStore(self.root / "recovery.json")

    def tearDown(self):
        close_test_window(self.window)
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_group_selection_saves_complete_nested_structure(self):
        sequence = [
            Action(kind="if_start", condition_source="pixel"),
            Action(kind="loop_start", repeats=2), Action(kind="wait"),
            Action(kind="loop_end"), Action(kind="else"),
            Action(kind="key"), Action(kind="if_end"),
        ]
        self.window._replace_actions(sequence)
        group = self.window.tree.topLevelItem(0)
        group.setSelected(True)
        group.child(0).setSelected(True)  # Child must not be duplicated in snippet.
        ident = self.window._save_snippet_selection("Condition")
        snippet = self.window.snippet_store.read(ident)
        self.assertEqual([action["kind"] for action in snippet["actions"]],
                         [a.kind for a in sequence])
        self.assertIn("Else:", snippet_preview(snippet))

    def test_insert_copy_updates_variables_and_one_undo_snapshot(self):
        snippet = make_snippet("Reusable wait", [
            Action(kind="wait", bindings={"seconds": "duration"})], [
            defs("duration", "number", 1.5)])
        self.window._replace_actions([Action(kind="key", keys="enter")])
        self.window._mark_clean()
        self.window.tree.setCurrentItem(self.window.tree.topLevelItem(0))
        self.window._insert_snippet_copy(snippet)
        self.assertEqual([action.kind for action in self.window.actions],
                         ["key", "wait"])
        self.assertEqual(self.window.variables, [defs("duration", "number", 1.5)])
        self.assertTrue(self.window._is_dirty())
        self.window.undo()
        self.assertEqual([action.kind for action in self.window.actions], ["key"])
        self.assertEqual(self.window.variables, [])
        self.window.redo()
        self.assertEqual([action.kind for action in self.window.actions], ["key", "wait"])
        self.assertEqual(self.window.variables, [defs("duration", "number", 1.5)])
        # The inserted leaf remains a normal selectable/duplicable tree action.
        self.window.tree.setCurrentItem(self.window.tree.topLevelItem(1))
        self.window.tree.duplicate_selection()
        self.assertEqual(len(self.window.actions), 3)

    def test_insert_into_else_branch_and_nested_block(self):
        original = [
            Action(kind="if_start", condition_source="pixel"),
            Action(kind="wait"), Action(kind="else"), Action(kind="wait"),
            Action(kind="if_end"),
        ]
        self.window._replace_actions(original)
        group = self.window.tree.topLevelItem(0)
        branch = group.child(1)
        self.assertEqual(branch.data(0, int(Qt.ItemDataRole.UserRole)), "else_branch")
        self.window.tree.setCurrentItem(branch)
        self.window._insert_snippet_copy(make_snippet(
            "Key", [Action(kind="key", keys="a")], []))
        self.assertEqual([a.kind for a in self.window.actions], [
            "if_start", "wait", "else", "wait", "key", "if_end"])
        self.window.tree.setCurrentItem(self.window.tree.topLevelItem(0))
        self.window._insert_snippet_copy(make_snippet(
            "Mouse", [Action(kind="click", x=4, y=8)], []))
        self.assertEqual([a.kind for a in self.window.actions], [
            "if_start", "wait", "click", "else", "wait", "key", "if_end"])

    def test_invalid_insertion_never_changes_editor_or_history(self):
        self.window._replace_actions([Action(kind="wait")])
        self.window._mark_clean()
        self.window.history = type(self.window.history)(60)
        original = deepcopy(self.window.actions)
        missing = make_snippet("Image", [
            Action(kind="click_image", image_path=str(self.root / "missing.png"))], [])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.window._insert_snippet_copy(missing)
        self.assertEqual(self.window.actions, original)
        self.assertFalse(self.window.history.can_undo)
        self.assertFalse(self.window._is_dirty())

    def test_browser_search_and_preview_do_not_expose_clipboard_text(self):
        saved = make_snippet("Paste example", [
            Action(kind="clipboard_set", clipboard_text="private clipboard value"),
            Action(kind="key", key_mode="type", keys="private typed value")], [])
        self.window.snippet_store.save(saved)
        dialog = SnippetLibraryDialog(
            self.window.snippet_store, self.window._save_snippet_selection,
            self.window._insert_snippet_copy, self.window)
        try:
            self.assertEqual(dialog.items.count(), 1)
            self.assertIn("independent copy", dialog.preview.toPlainText())
            self.assertNotIn("private clipboard value", dialog.preview.toPlainText())
            self.assertNotIn("private typed value", dialog.preview.toPlainText())
            dialog.search.setText("no match")
            self.assertEqual(dialog.items.count(), 0)
            dialog.search.setText("paste")
            self.assertEqual(dialog.items.count(), 1)
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
