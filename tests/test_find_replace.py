"""Pure model tests for nested workflow search and atomic bulk replacement."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from macro_find_replace import search_actions, plan_replacements
from macro_model import Action, serialize_document, parse_document


class WorkflowSearchTests(unittest.TestCase):
    def setUp(self):
        self.actions = [
            Action(kind="if_start", condition_source="pixel", name="Check dialog"),
            Action(kind="key", name="Save dialog", keys="ctrl+s"),
            Action(kind="click_image", name="Approve button", image_path=r"C:\tmp\approve.png"),
            Action(kind="else"),
            Action(kind="click", x=42, y=80, name="Fallback", enabled=False),
            Action(kind="if_end"),
            Action(kind="key", name="Save document", keys="ctrl+s"),
        ]

    def matches(self, query, field):
        return [m.index for m in search_actions(self.actions, query, field)]

    def test_searches_nested_groups_by_type_and_name(self):
        self.assertEqual(self.matches("key", "kind"), [1, 6])
        self.assertEqual(self.matches("save", "name"), [1, 6])
        self.assertEqual(self.matches("if end", "kind"), [5])
        self.assertEqual(self.matches("check dialog", "name"), [0])

    def test_searches_enabled_keyboard_coordinates_and_image_basename(self):
        self.assertEqual(self.matches("false", "enabled"), [4])
        self.assertEqual(self.matches("enabled", "enabled"), [0, 1, 2, 3, 5, 6])
        self.assertEqual(self.matches("ctrl+s", "keys"), [1, 6])
        self.assertEqual(self.matches("x=42", "coordinates"), [4])
        self.assertEqual(self.matches("42,80", "coordinates"), [4])
        self.assertEqual(self.matches("(42, 80)", "coordinates"), [4])
        self.assertEqual(self.matches("80", "coordinates"), [4])
        self.assertEqual(self.matches("approve.png", "image"), [2])
        self.assertEqual(self.matches("APPROVE.PNG", "all"), [2])

    def test_empty_and_unknown_queries_are_safe(self):
        self.assertEqual(search_actions(self.actions, "   "), [])
        with self.assertRaises(ValueError):
            search_actions(self.actions, "save", "unknown")

    def test_large_workflow_search_is_linear_and_complete(self):
        many = [Action(kind="wait", name=f"Step {i}") for i in range(4000)]
        found = search_actions(many, "step 3999", "name")
        self.assertEqual([m.index for m in found], [3999])


class WorkflowReplacementTests(unittest.TestCase):
    def setUp(self):
        self.actions = [
            Action(kind="if_start", condition_source="pixel", name="Group"),
            Action(kind="key", keys="ctrl+s", name="Save now"),
            Action(kind="wait", seconds=1.5, name="Wait one"),
            Action(kind="else"),
            Action(kind="key", keys="ctrl+s", name="Save again"),
            Action(kind="if_end"),
        ]

    def test_substring_replacement_preserves_original_and_group_structure(self):
        before = deepcopy(self.actions)
        matches = [m.index for m in search_actions(self.actions, "save", "name")]
        plan = plan_replacements(self.actions, matches, "name", "Export",
                                 mode="replace", find_text="Save")
        self.assertEqual([c.index for c in plan.changes], [1, 4])
        self.assertEqual([c.new for c in plan.changes],
                         ["Export now", "Export again"])
        self.assertEqual(self.actions, before)
        self.assertEqual([x.kind for x in plan.actions],
                         [x.kind for x in before])
        parsed, _ = parse_document(serialize_document(list(plan.actions), 1, 0))
        self.assertEqual(parsed, list(plan.actions))

    def test_set_numeric_values_in_nested_actions(self):
        plan = plan_replacements(self.actions, [2], "seconds", "2.75")
        self.assertEqual(plan.actions[2].seconds, 2.75)
        self.assertEqual(self.actions[2].seconds, 1.5)
        with self.assertRaisesRegex(ValueError, "Action 3"):
            plan_replacements(self.actions, [2], "seconds", "-1")

    def test_integer_replacement_and_invalid_values(self):
        actions = [Action(kind="click", x=10, y=12),
                   Action(kind="drag", x=20, y=15, to_x=40, to_y=50)]
        plan = plan_replacements(actions, [0, 1], "x", "123")
        self.assertEqual([x.x for x in plan.actions], [123, 123])
        with self.assertRaisesRegex(ValueError, "integer"):
            plan_replacements(actions, [0, 1], "x", "1.5")
        with self.assertRaisesRegex(ValueError, "Substring replace"):
            plan_replacements(actions, [0, 1], "x", "10", mode="replace", find_text="1")

    def test_mixed_selection_skips_structural_markers_and_wrong_kinds(self):
        plan = plan_replacements(self.actions, list(range(6)), "keys", "ctrl+p")
        self.assertEqual([change.index for change in plan.changes], [1, 4])
        self.assertEqual(plan.skipped, 4)
        self.assertEqual(self.actions[1].keys, "ctrl+s")
        self.assertEqual(plan.actions[0].name, "Group")

    def test_no_partial_result_if_any_replacement_invalid(self):
        actions = [Action(kind="key", keys="a"),
                   Action(kind="key_down", keys="shift")]
        before = deepcopy(actions)
        with self.assertRaisesRegex(ValueError, "Action 2"):
            plan_replacements(actions, [0, 1], "keys", "ctrl+s")
        self.assertEqual(actions, before)

    def test_unbound_fields_only_and_correct_variable_definitions(self):
        actions = [
            Action(kind="click", x=7, y=12, bindings={"point": "position"}),
            Action(kind="click", x=7, y=12),
        ]
        definitions = [{"name": "position", "type": "coordinates",
                        "default": [7, 12]}]
        plan = plan_replacements(actions, [0, 1], "x", "33",
                                 variables=definitions)
        self.assertEqual(plan.skipped, 1)
        self.assertEqual(plan.actions[0].x, 7)
        self.assertEqual(plan.actions[1].x, 33)

    def test_unrelated_or_unsupported_fields_cannot_be_changed(self):
        with self.assertRaisesRegex(ValueError, "Only listed"):
            plan_replacements(self.actions, [1], "kind", "click")
        with self.assertRaisesRegex(ValueError, "No eligible"):
            plan_replacements(self.actions, [0, 3, 5], "name", "Changed")
        with self.assertRaisesRegex(ValueError, "indices"):
            plan_replacements(self.actions, [1000], "name", "Changed")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            plan_replacements(self.actions, [1], "name", "new",
                              mode="replace", find_text="")

    def test_invalid_reference_image_fails_atomically(self):
        with self.assertRaisesRegex(ValueError, "Reference image does not exist"):
            plan_replacements(
                [Action(kind="click_image", image_path="first.png"),
                 Action(kind="click_image", image_path="second.png")],
                [0, 1], "image_path", "/no/such/image.png")
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "valid.png"
            Image.new("RGB", (5, 5), "blue").save(image)
            plan = plan_replacements(
                [Action(kind="click_image", image_path="first.png"),
                 Action(kind="click_image", image_path="second.png")],
                [0, 1], "image_path", str(image))
            self.assertEqual([x.image_path for x in plan.actions],
                             [str(image), str(image)])

    def test_relative_image_replacement_is_saved_as_absolute(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "relative.png"
            Image.new("RGB", (5, 5), "red").save(image)
            plan = plan_replacements(
                [Action(kind="click_image", image_path="old.png")],
                [0], "image_path", "relative.png", base_dir=temp)
            self.assertEqual(plan.actions[0].image_path, str(image.resolve()))

    def test_does_not_change_values_that_are_already_identical(self):
        with self.assertRaisesRegex(ValueError, "No eligible"):
            plan_replacements(self.actions, [1, 4], "keys", "ctrl+s")


if __name__ == "__main__":
    unittest.main()
