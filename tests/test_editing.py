import unittest
from macro_model import Action
from macro_editing import ActionHistory,move_selected,duplicate_selected,delete_selected

def actions(*names): return [Action(kind="key",keys=n) for n in names]

class EditTests(unittest.TestCase):
    def test_undo_redo(self):
        a=actions("a"); h=ActionHistory(2); h.record(a)
        a[0].keys="b"; h.record(a); a.append(Action(kind="wait"))
        self.assertEqual([x.keys for x in h.undo(a)],["b"])
        orig=h.undo(a); self.assertEqual(orig[0].keys,"a")
        self.assertFalse(h.can_undo)
        restored=h.redo(orig); self.assertEqual(restored[0].keys,"b")
        h.record(restored); self.assertFalse(h.can_redo)
    def test_history_limit(self):
        h=ActionHistory(2)
        for i in range(5): h.record(actions(str(i)))
        self.assertEqual(len(h.past),2)
    def test_move_rows(self):
        a=actions("a","b","c","d","e")
        moved,sel=move_selected(a,[1,2],-1)
        self.assertEqual([x.keys for x in moved],["b","c","a","d","e"])
        self.assertEqual(sel,[0,1])
        moved,sel=move_selected(a,[1,3],1)
        self.assertEqual([x.keys for x in moved],["a","c","b","e","d"])
        self.assertEqual(sel,[2,4])
        unchanged,sel=move_selected(a,[0],-1)
        self.assertEqual(unchanged,a)
    def test_duplicate_delete(self):
        a=actions("a","b","c","d")
        result,sel=duplicate_selected(a,[0,2])
        self.assertEqual([x.keys for x in result],["a","b","c","a","c","d"])
        self.assertEqual(sel,[3,4]); result[3].keys="changed"
        self.assertEqual(a[0].keys,"a")
        deleted,sel=delete_selected(a,[1,3])
        self.assertEqual([x.keys for x in deleted],["a","c"])
        self.assertEqual(sel,[1])
        with self.assertRaises(ValueError):
            duplicate_selected([Action(kind="loop_start"),Action(kind="key")],[0,1])
