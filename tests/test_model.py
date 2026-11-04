import unittest
from dataclasses import asdict
from macro_model import Action, parse_sequence, parse_document, serialize_document, validate_action


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

    def test_disabled_action(self):
        action = validate_action({"kind": "wait", "seconds": 1, "enabled": False})
        self.assertFalse(action.enabled)
        self.assertEqual(parse_sequence([{"kind": "wait"}])[0].enabled, True)
        with self.assertRaises(ValueError):
            validate_action({"kind": "wait", "enabled": "false"})

    def test_macro_document_roundtrip(self):
        actions = [Action(kind="click", x=42, y=99, enabled=False, name="Skip me"),
                   Action(kind="wait", seconds=0.25, repeats=3)]
        document = serialize_document(actions, 8, 2.5)
        self.assertEqual(document["version"], 2)
        parsed, settings = parse_document(document)
        self.assertEqual(parsed, actions)
        self.assertEqual(settings, {"repeat_count": 8, "start_delay": 2.5})

    def test_legacy_file_keeps_current_settings(self):
        actions, settings = parse_document([{"kind": "wait", "seconds": 1.0}])
        self.assertIsNone(settings)
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0].enabled)

    def test_bad_document_settings(self):
        valid = serialize_document([Action(kind="wait")], 1, 0.0)
        for bad in (
            {"version": 3, "settings": valid["settings"], "actions": valid["actions"]},
            {"version": 2, "settings": {"repeat_count": 0, "start_delay": 0}, "actions": []},
            {"version": 2, "settings": {"repeat_count": 2, "start_delay": -0.1}, "actions": []},
            {"version": 2, "settings": {"repeat_count": 2, "start_delay": float("inf")}, "actions": []},
            {"version": 2, "settings": {"repeat_count": 2, "start_delay": 0}, "actions": "wrong"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_document(bad)

    def test_new_action_types(self):
        actions = [
            Action(kind="scroll", scroll_amount=-4, repeats=2),
            Action(kind="drag", x=10, y=20, to_x=80, to_y=90,
                   move_duration=0.5, button="left"),
        ]
        restored, _ = parse_document(serialize_document(actions, 3, 1.0))
        self.assertEqual(restored, actions)
        for bad in ({"kind": "scroll", "scroll_amount": 0},
                    {"kind": "scroll", "scroll_amount": 1.5},
                    {"kind": "drag", "x": 1, "y": 1, "to_x": None, "to_y": 5},
                    {"kind": "drag", "x": 1, "y": 1, "to_x": 2, "to_y": 5, "move_duration": -1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_action(bad)

    def test_invalid_document(self):
        for data in ({}, [None], [{"kind": "wait", "repeats": 0}]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_sequence(data)


if __name__ == "__main__":
    unittest.main()
