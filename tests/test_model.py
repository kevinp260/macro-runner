import unittest
from dataclasses import asdict
from macro_model import Action, parse_sequence, validate_action


class ActionTests(unittest.TestCase):
    def test_legacy_sequence(self):
        actions = parse_sequence([
            {"kind": "click", "x": 10, "y": 20, "repeats": 2},
            {"kind": "wait", "seconds": 0.5},
            {"kind": "key", "keys": "ctrl+s"},
        ])
        self.assertEqual([a.kind for a in actions], ["click", "wait", "key"])
        self.assertEqual(actions[0].repeats, 2)

    def test_roundtrip(self):
        action = Action(kind="move", x=100, y=200, move_duration=0.3, name="Test")
        self.assertEqual(validate_action(asdict(action)), action)

    def test_bad_input(self):
        examples = [None, {}, {"kind": "execute"}, {"kind": "wait", "seconds": -1},
                    {"kind": "wait", "seconds": float("nan")},
                    {"kind": "click", "x": None, "y": 2},
                    {"kind": "key", "key_mode": "type", "keys": ""}]
        for data in examples:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_action(data)

    def test_invalid_document(self):
        for data in ({}, [None], [{"kind": "wait", "repeats": 0}]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_sequence(data)


if __name__ == "__main__":
    unittest.main()
