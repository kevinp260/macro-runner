import unittest
from types import SimpleNamespace
from macro_keys import KeyboardRecorder,HeldKeys,normalize_event_key,valid_hold_key
from macro_model import Action,parse_document,serialize_document,validate_action

class KeyTests(unittest.TestCase):
    def test_hold_roundtrip(self):
        a=[Action(kind="key_down",keys="shift"),Action(kind="click",x=1,y=2),
           Action(kind="key_up",keys="shift")]
        loaded,_=parse_document(serialize_document(a,1,0))
        self.assertEqual(loaded,a)
        for data in ({"kind":"key_down","keys":"ctrl+c"},{"kind":"key_up","keys":""},
                     {"kind":"key_down","keys":"nonsense_key"}):
            with self.assertRaises(ValueError): validate_action(data)
    def test_normalize(self):
        for name,expected in [("ctrl_l","ctrl"),("shift_r","shift"),
                              ("esc","esc"),("page_down","pgdn")]:
            self.assertEqual(normalize_event_key(SimpleNamespace(name=name)),expected)
        self.assertEqual(normalize_event_key(SimpleNamespace(char="A")),"a")
        self.assertEqual(normalize_event_key(SimpleNamespace(char=chr(3))),"c")
        self.assertEqual(normalize_event_key(SimpleNamespace(char=" ")),"space")
        self.assertIsNone(normalize_event_key(SimpleNamespace(char="☃")))
        self.assertFalse(valid_hold_key("ctrl+v"))
    def test_recorder(self):
        r=KeyboardRecorder()
        self.assertEqual(r.press("ctrl").kind,"key_down")
        self.assertIsNone(r.press("ctrl"))
        self.assertEqual(r.press("c").keys,"c")
        self.assertIsNone(r.release("c"))
        self.assertEqual(r.release("ctrl").kind,"key_up")
        self.assertEqual(r.finish(),[])
        r.press("shift")
        self.assertEqual([(a.kind,a.keys) for a in r.finish()],[("key_up","shift")])
    def test_release_on_abort(self):
        log=[]
        h=HeldKeys(lambda n:log.append(("down",n)),lambda n:log.append(("up",n)))
        h.press("shift");h.press("shift");h.press("ctrl")
        self.assertEqual(h.release_all(),[])
        self.assertEqual(log,[("down","shift"),("down","ctrl"),("up","ctrl"),("up","shift")])
        with self.assertRaises(ValueError):h.release("ctrl")
