"""Headless Qt editor and toolbar tests for transient breakpoints."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from macro_model import Action, serialize_document
from macro_qt import MacroWindow
from macro_qt_workflow import WorkflowTree

app = QApplication.instance() or QApplication([])


class BreakpointTreeTests(unittest.TestCase):
    def test_nested_marker_and_plain_json_unchanged(self):
        tree = WorkflowTree()
        actions = [Action(kind="loop_start", repeats=2),
                   Action(kind="key", keys="x"),
                   Action(kind="loop_end"), Action(kind="wait")]
        tree.set_actions(actions)
        before = serialize_document(tree.actions(), 1, 0)
        nested = tree.topLevelItem(0).child(0)
        nested.setSelected(True)
        changes = []
        tree.actions_changed.connect(changes.append)
        tree.toggle_breakpoints()
        self.assertIn("●", nested.text(0))
        self.assertEqual(tree.breakpoint_indices(), {1})
        self.assertEqual(changes, [])
        self.assertEqual(serialize_document(tree.actions(), 1, 0), before)
        tree.toggle_breakpoints()
        self.assertNotIn("●", nested.text(0))
        self.assertEqual(tree.breakpoint_indices(), set())
        tree.close()

    def test_control_marker_rejected(self):
        tree = WorkflowTree()
        tree.set_actions([Action(kind="loop_start"), Action(kind="wait"),
                          Action(kind="loop_end")])
        errors = []
        tree.invalid_change.connect(errors.append)
        tree.topLevelItem(0).setSelected(True)
        tree.toggle_breakpoints()
        self.assertTrue(errors)
        self.assertEqual(tree.breakpoint_indices(), set())
        tree.close()

    def test_disabled_mark_can_be_enabled_later(self):
        tree = WorkflowTree()
        tree.set_actions([Action(kind="wait", enabled=False)])
        item = tree.topLevelItem(0)
        item.setSelected(True)
        tree.toggle_breakpoints()
        self.assertIn("●", item.text(0))
        self.assertEqual(tree.breakpoint_indices(), set())
        item.setCheckState(0, Qt.CheckState.Checked)
        self.assertEqual(tree.breakpoint_indices(), {0})
        self.assertIn("●", item.text(0))
        tree.close()

    def test_action_edit_and_reorder_keep_marker_but_rebuild_resets(self):
        tree = WorkflowTree()
        tree.set_actions([Action(kind="wait", seconds=1),
                          Action(kind="wait", seconds=2)])
        first = tree.topLevelItem(0)
        first.setSelected(True)
        tree.toggle_breakpoints()
        tree.update_selected_action(Action(kind="wait", seconds=3))
        self.assertIn("●", first.text(0))
        moved = tree.takeTopLevelItem(0)
        tree.insertTopLevelItem(1, moved)
        tree._commit(tree._snapshot)
        self.assertEqual(tree.breakpoint_indices(), {1})
        tree.set_actions(tree.actions())
        self.assertEqual(tree.breakpoint_indices(), set())
        tree.close()


class BreakpointWindowTests(unittest.TestCase):
    def test_run_snapshot_uses_active_breakpoints_and_gap(self):
        window = MacroWindow()
        old_gap = window.settings.value("debug_gap")
        try:
            window._replace_actions([Action(kind="wait", seconds=0),
                                     Action(kind="wait", seconds=0)])
            item = window.tree.topLevelItem(1)
            item.setSelected(True)
            window.toggle_breakpoint()
            window.debug_gap.setValue(.6)
            runner = SimpleNamespace(total=2, start=lambda: None)
            with patch.object(window, "_validate_before_run", return_value=True), patch(
                    "macro_qt.MacroExecutor", return_value=runner) as factory:
                window.run_workflow()
            self.assertEqual(factory.call_args.kwargs["breakpoints"], {1})
            self.assertEqual(factory.call_args.kwargs["debug_gap"], .6)
            self.assertIs(window.executor, runner)
        finally:
            window.executor = None
            window._run_session = None
            if old_gap is None:
                window.settings.remove("debug_gap")
            else:
                window.settings.setValue("debug_gap", old_gap)
            window.close()

    def test_breakpoint_diagnostic_highlights_and_allows_resume(self):
        window = MacroWindow()
        try:
            window._replace_actions([Action(kind="wait", seconds=0)])
            gate = SimpleNamespace(paused=True)
            resumed = []
            window.executor = SimpleNamespace(gate=gate, resume=lambda: resumed.append(True))
            window._diagnostic_event({"event": "breakpoint", "index": 0, "cycle": 1})
            self.assertEqual(window.tree.currentItem(), window.tree.topLevelItem(0))
            self.assertIn("Breakpoint before action #1", window.status.text())
            self.assertEqual(window.toolbar_actions["pause"].text(), "Resume")
            window.pause_run()
            self.assertEqual(resumed, [True])
        finally:
            window.executor = None
            window.close()

    def test_minimized_editor_is_accessible_on_break_and_reminimized_on_continue(self):
        window = MacroWindow()
        try:
            window.show()
            app.processEvents()
            window._replace_actions([Action(kind="wait", seconds=0)])
            window._restore_after_run = True
            window.executor = SimpleNamespace(
                gate=SimpleNamespace(paused=True), resume=lambda: None)
            window.showMinimized()
            app.processEvents()
            window._diagnostic_event({"event": "breakpoint", "index": 0})
            app.processEvents()
            self.assertTrue(window._debug_window_visible)
            self.assertFalse(window.isMinimized())
            window.pause_run()
            app.processEvents()
            self.assertTrue(window.isMinimized())
            window._restore_run_window()
            self.assertFalse(window.isMinimized())
        finally:
            window.executor = None
            window.close()


if __name__ == "__main__":
    unittest.main()
