import os
import unittest
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
