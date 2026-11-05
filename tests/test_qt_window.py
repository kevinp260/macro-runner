import unittest
from PySide6.QtWidgets import QApplication
from macro_qt import MacroWindow
from macro_model import Action

app = QApplication.instance() or QApplication([])


class WindowTests(unittest.TestCase):
    def test_window_undo_and_full_workflow(self):
        w = MacroWindow()
        try:
            w._replace_actions([Action(kind="wait", seconds=1)])
            w.tree.insert_kind("loop_start")
            self.assertEqual([a.kind for a in w.actions],
                             ["wait", "loop_start", "wait", "loop_end"])
            w.undo()
            self.assertEqual([a.kind for a in w.actions], ["wait"])
            w.redo()
            self.assertEqual(w.actions[-1].kind, "loop_end")
        finally:
            w.close()

    def test_scrollable_palette_and_inspector(self):
        w = MacroWindow()
        try:
            w.search.setText("click")
            visible = [w.palette.item(i).text() for i in range(w.palette.count())
                       if not w.palette.item(i).isHidden()]
            self.assertEqual(len(visible), 2)
            w._replace_actions([Action(kind="wait", seconds=1)])
            w.tree.topLevelItem(0).setSelected(True)
            self.assertEqual(w.inspector.current.kind, "wait")
        finally:
            w.close()
