import unittest

from macro_model import Action, parse_document, serialize_document, validate_action
from macro_flow import iter_flow_steps, validate_flow, validate_start_selection


def pixel(kind, **params):
    return Action(kind=kind, condition_source="pixel",
                  pixel_color="#FF0000", **params)


class SmartFlowTests(unittest.TestCase):
    def test_if_else_and_repeat_until(self):
        actions = [
            pixel("if_start"), Action(kind="key", keys="then"),
            Action(kind="else"), Action(kind="key", keys="else"),
            Action(kind="if_end"),
            pixel("until_start", repeats=4),
            Action(kind="key", keys="retry"), Action(kind="until_end"),
            Action(kind="key", keys="end"),
        ]
        checks = iter([False, False, False, True])
        actual = [a.keys for _, a in iter_flow_steps(
            actions, lambda _: next(checks), lambda: False)]
        self.assertEqual(actual, ["else", "retry", "retry", "retry", "end"])

    def test_nested_condition_with_fixed_loop(self):
        actions = [Action(kind="loop_start", repeats=2), pixel("if_start"),
                   Action(kind="key", keys="yes", repeats=2),
                   Action(kind="else"), Action(kind="key", keys="no"),
                   Action(kind="if_end"), Action(kind="loop_end")]
        self.assertEqual(
            [a.keys for _, a in iter_flow_steps(actions, lambda _: True, lambda: False)],
            ["yes", "yes", "yes", "yes"]
        )

    def test_until_limit(self):
        actions = [pixel("until_start", repeats=2),
                   Action(kind="key", keys="tick"), Action(kind="until_end")]
        with self.assertRaises(TimeoutError):
            list(iter_flow_steps(actions, lambda _: False, lambda: False))

    def test_stop_before_markers(self):
        actions = [pixel("if_start"), Action(kind="key"),
                   Action(kind="if_end")]
        with self.assertRaises(RuntimeError):
            list(iter_flow_steps(actions, lambda _: True, lambda: True))

    def test_invalid_blocks(self):
        p = pixel("if_start")
        cases = [
            [Action(kind="else")], [Action(kind="if_end")],
            [Action(kind="until_end")], [p, Action(kind="if_end")],
            [p, Action(kind="key"), Action(kind="else"), Action(kind="if_end")],
            [pixel("until_start"), Action(kind="until_end")],
            [p, Action(kind="key"), Action(kind="else"), Action(kind="key"),
             Action(kind="else"), Action(kind="key"), Action(kind="if_end")],
        ]
        for actions in cases:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                validate_flow(actions)

    def test_selection_inside_block_rejected(self):
        actions = [pixel("if_start"), Action(kind="key"), Action(kind="if_end"),
                   Action(kind="key", keys="last")]
        with self.assertRaises(ValueError):
            validate_start_selection(actions, 1)
        self.assertEqual(
            [a.keys for _, a in iter_flow_steps(actions, lambda _: True,
                                                 lambda: False, 3)],
            ["last"]
        )

    def test_document_compatibility(self):
        actions = [pixel("if_start"), Action(kind="key"),
                   Action(kind="if_end")]
        restored, settings = parse_document(serialize_document(actions, 3, 2.0))
        self.assertEqual(restored, actions)
        self.assertEqual(settings["repeat_count"], 3)

    def test_model_validation(self):
        bad = [
            {"kind": "click_image", "image_path": ""},
            {"kind": "click_image", "image_path": "x.png", "confidence": 2},
            {"kind": "click_image", "image_path": "x.png", "match_mode": "not_matches"},
            {"kind": "wait_until", "condition_source": "pixel", "pixel_color": "red"},
            {"kind": "wait_until", "condition_source": "pixel", "pixel_tolerance": 256},
            {"kind": "if_start", "image_path": "x.png", "region_x": 3},
            {"kind": "wait_until", "image_path": "x.png", "poll_interval": 0},
            {"kind": "if_end", "enabled": False},
            {"kind": "until_end", "repeats": 2},
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_action(item)
