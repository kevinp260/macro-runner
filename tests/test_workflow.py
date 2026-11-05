import unittest
from copy import deepcopy
from macro_model import Action, serialize_document, parse_document
from macro_workflow import from_actions, to_actions, default_node, WorkflowNode


class WorkflowStructureTests(unittest.TestCase):
    def test_roundtrip_nested_conditional_and_loops(self):
        actions = [
            Action(kind="loop_start", repeats=3, name="Outer"),
            Action(kind="if_start", condition_source="pixel", pixel_color="#112233"),
            Action(kind="key", keys="a"),
            Action(kind="else", name="Otherwise"),
            Action(kind="until_start", condition_source="pixel", repeats=2),
            Action(kind="wait", seconds=0.3),
            Action(kind="until_end"),
            Action(kind="if_end"), Action(kind="loop_end"),
            Action(kind="key_down", keys="shift"), Action(kind="key_up", keys="shift")
        ]
        nodes = from_actions(actions)
        self.assertEqual(to_actions(nodes), actions)
        saved = serialize_document(to_actions(nodes), 2, 0.3)
        self.assertEqual(parse_document(saved)[0], actions)

    def test_move_group_as_a_unit(self):
        nodes = [default_node("loop_start"), default_node("key")]
        expected = to_actions(nodes)
        nodes.reverse()
        self.assertEqual(to_actions(nodes), expected[-1:] + expected[:-1])
        self.assertEqual(len(nodes[1].children), 1)

    def test_if_else_branches_and_undoable_snapshot(self):
        nodes = [default_node("if_start")]
        nodes[0].otherwise.append(default_node("key"))
        actions = to_actions(nodes)
        self.assertEqual([x.kind for x in actions],
                         ["if_start", "wait", "else", "key", "if_end"])
        clone = deepcopy(nodes)
        clone[0].children[0] = default_node("scroll")
        self.assertEqual(nodes[0].children[0].action.kind, "wait")
        self.assertEqual(to_actions(clone)[1].kind, "scroll")

    def test_invalid_empty_group_or_nested_fixed_repeat(self):
        group = default_node("if_start")
        group.children = []
        with self.assertRaises(ValueError):
            to_actions([group])
        inner = default_node("loop_start")
        outer = default_node("loop_start")
        outer.children = [inner]
        with self.assertRaises(ValueError):
            to_actions([outer])

    def test_default_actions_compile(self):
        for kind in ("click", "wait", "key", "move", "scroll", "drag",
                     "key_down", "key_up", "wait_until", "if_start",
                     "loop_start", "until_start"):
            with self.subTest(kind=kind):
                self.assertGreaterEqual(len(to_actions([default_node(kind)])), 1)
