import os
import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from macro_model import Action
from macro_qt_workflow import WorkflowTree

app = QApplication.instance() or QApplication([])


class TreeEditorTests(unittest.TestCase):
    def test_block_insertion_drag_as_group_and_roundtrip(self):
        w = WorkflowTree()
        w.set_actions([Action(kind="wait", seconds=1)])
        w.insert_kind("loop_start")
        self.assertEqual([a.kind for a in w.actions()],
                         ["wait", "loop_start", "wait", "loop_end"])
        original = w.actions()
        self.assertEqual(len(w.index_map()), len(original))
        w.set_actions(original)
        self.assertEqual(w.actions(), original)

    def test_reject_broken_group_delete(self):
        w = WorkflowTree()
        actions = [Action(kind="loop_start"), Action(kind="wait"), Action(kind="loop_end")]
        w.set_actions(actions)
        errors = []
        w.invalid_change.connect(errors.append)
        child = w.topLevelItem(0).child(0)
        child.setSelected(True)
        w.delete_selection()
        self.assertEqual(w.actions(), actions)
        self.assertTrue(errors)

    def test_flat_indices_ignore_empty_else_drop_target(self):
        w = WorkflowTree()
        w.insert_kind("if_start")
        flattened = w.actions()
        self.assertEqual([a.kind for a in flattened],
                         ["if_start", "wait", "if_end"])
        self.assertEqual(len(w.index_map()), len(flattened))
        self.assertIs(w.index_map()[2], w.topLevelItem(0))

    def test_indices_with_actual_else_branch(self):
        w = WorkflowTree()
        w.set_actions([
            Action(kind="if_start", condition_source="pixel"),
            Action(kind="key", keys="a"),
            Action(kind="else"),
            Action(kind="key", keys="b"),
            Action(kind="if_end"),
        ])
        self.assertEqual(len(w.index_map()), len(w.actions()))
        self.assertEqual(w.index_map()[2].text(0)[:4], "ELSE")

    def test_leaf_checkboxes_show_status_and_commit_immediately(self):
        w = WorkflowTree()
        original = [Action(kind="click", x=5, y=8),
                    Action(kind="wait", seconds=2, enabled=False)]
        changed = []
        w.actions_changed.connect(changed.append)
        w.set_actions(original)
        self.assertEqual(changed, [])  # Loading is not a user edit.
        enabled = w.topLevelItem(0)
        disabled = w.topLevelItem(1)
        self.assertEqual(enabled.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(disabled.checkState(0), Qt.CheckState.Unchecked)
        self.assertTrue(disabled.font(0).strikeOut())
        self.assertIn("[disabled]", disabled.text(0))
        self.assertFalse(enabled.font(0).strikeOut())

        disabled.setCheckState(0, Qt.CheckState.Checked)
        self.assertEqual(len(changed), 1)
        self.assertTrue(w.actions()[1].enabled)
        self.assertFalse(disabled.font(0).strikeOut())
        self.assertNotIn("[disabled]", disabled.text(0))

        enabled.setCheckState(0, Qt.CheckState.Unchecked)
        self.assertEqual(len(changed), 2)
        self.assertFalse(w.actions()[0].enabled)
        self.assertTrue(enabled.font(0).strikeOut())
        self.assertEqual(w._snapshot, w.actions())

    def test_nested_actions_can_toggle_but_group_cannot(self):
        w = WorkflowTree()
        w.set_actions([Action(kind="loop_start", repeats=3),
                       Action(kind="wait", enabled=False),
                       Action(kind="loop_end")])
        group = w.topLevelItem(0)
        child = group.child(0)
        self.assertFalse(group.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertTrue(child.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertEqual(child.checkState(0), Qt.CheckState.Unchecked)
        child.setCheckState(0, Qt.CheckState.Checked)
        self.assertTrue(w.actions()[1].enabled)
        self.assertEqual([a.kind for a in w.actions()],
                         ["loop_start", "wait", "loop_end"])

    def test_inspector_edit_and_bulk_toggle_sync_checkboxes(self):
        w = WorkflowTree()
        w.set_actions([Action(kind="wait", seconds=1),
                       Action(kind="key", keys="a")])
        first = w.topLevelItem(0)
        first.setSelected(True)
        w.update_selected_action(Action(kind="wait", seconds=2, enabled=False))
        self.assertEqual(first.checkState(0), Qt.CheckState.Unchecked)
        self.assertTrue(first.font(0).strikeOut())
        w.topLevelItem(1).setSelected(True)
        w.toggle_enabled_selection()
        self.assertEqual([a.enabled for a in w.actions()], [True, False])
        self.assertEqual(first.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(w.topLevelItem(1).checkState(0), Qt.CheckState.Unchecked)

    def test_bulk_toggle_enabled_and_reject_group_toggle(self):
        w = WorkflowTree()
        w.set_actions([Action(kind="wait"), Action(kind="key", keys="a")])
        w.topLevelItem(0).setSelected(True)
        w.topLevelItem(1).setSelected(True)
        w.toggle_enabled_selection()
        self.assertEqual([a.enabled for a in w.actions()], [False, False])
        w.set_actions([Action(kind="loop_start"), Action(kind="wait"),
                       Action(kind="loop_end")])
        w.topLevelItem(0).setSelected(True)
        errors = []
        w.invalid_change.connect(errors.append)
        w.toggle_enabled_selection()
        self.assertTrue(errors)
        self.assertTrue(w.actions()[0].enabled)

    def test_change_properties_and_nested_if(self):
        w = WorkflowTree()
        w.set_actions([Action(kind="wait", seconds=2)])
        current = w.topLevelItem(0)
        current.setSelected(True)
        w.update_selected_action(Action(kind="wait", seconds=5))
        self.assertEqual(w.actions()[0].seconds, 5)
        w.clearSelection()
        w.insert_kind("if_start")
        self.assertEqual(w.actions()[-1].kind, "if_end")
