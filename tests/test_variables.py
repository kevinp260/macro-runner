"""Typed workflow variables: document compatibility, runtime outputs and safety."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from macro_diagnostics import safe_event
from macro_editing import ActionHistory
from macro_model import Action, parse_document, serialize_document, validate_action
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_variables import (VariableContext, VariableMissing, format_value,
                             parse_value, validate_references, validate_variables,
                             unset_warnings)
from macro_clipboard import ClipboardState


def definition(name, kind, default=None):
    return {"name": name, "type": kind, "default": default}


class FakeClipboard:
    def __init__(self, response=None):
        self.response = response or ClipboardState("text", "new secret text")
        self.writes = []

    def read(self, gate=None):
        return self.response

    def set_text(self, text, gate=None):
        self.writes.append(text)


class FakeDesktop:
    def __init__(self):
        self.moves = []
        self.clicks = []
        self.pressed = []

    def keyDown(self, key): pass
    def keyUp(self, key): pass
    def screenshot(self, region=None): return object()
    def size(self): return (500, 400)
    def moveTo(self, x, y, duration=0): self.moves.append((x, y))
    def click(self, *args, **kwargs): self.clicks.append((args, kwargs))
    def press(self, key): self.pressed.append(key)
    def write(self, key): self.pressed.append(key)


class VariableModelTests(unittest.TestCase):
    def test_variable_types_validation_and_explicit_missing(self):
        defaults = [
            definition("Label", "text", "Hello 你好"),
            definition("Count", "number", 3),
            definition("Enabled", "boolean", False),
            definition("Point", "coordinates", [10, -20]),
            definition("Later", "text"),
        ]
        self.assertEqual(validate_variables(defaults), defaults)
        vars = VariableContext(defaults, {"Count": 8, "Enabled": True})
        self.assertEqual(vars.get("Count"), 8)
        self.assertEqual(vars.get("Enabled"), True)
        self.assertEqual(vars.get("Point"), [10, -20])
        with self.assertRaises(VariableMissing):
            vars.get("Later")
        vars.set_result("Later", "read from clipboard")
        self.assertEqual(vars.get("Later"), "read from clipboard")
        vars.reset()
        with self.assertRaises(VariableMissing):
            vars.get("Later")
        self.assertEqual(vars.get("Count"), 8)

    def test_reject_invalid_names_and_cross_type_values(self):
        invalid = [
            definition("a b", "text", ""), definition("9name", "text", ""),
            definition("A", "number", True), definition("x", "boolean", 1),
            definition("x", "coordinates", [1.0, 2]),
            definition("x", "number", float("inf")),
        ]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                validate_variables([entry])
        with self.assertRaises(ValueError):
            validate_variables([definition("x", "text", ""),
                                definition("x", "text", "again")])
        with self.assertRaises(ValueError):
            VariableContext([definition("flag", "boolean", True)],
                            {"flag": "true"})
        with self.assertRaises(ValueError):
            VariableContext([], {"unknown": "value"})

    def test_bound_point_numbers_boolean_and_unknown_fields(self):
        defs = [
            definition("place", "coordinates", [17, 29]),
            definition("n", "number", 5.0),
            definition("allow", "boolean", True),
        ]
        vars = VariableContext(defs)
        click = Action(kind="click", x=0, y=0, bindings={"point": "place"})
        resolved = vars.resolve(click)
        self.assertEqual((resolved.x, resolved.y), (17, 29))
        self.assertEqual(resolved.bindings, {})
        self.assertEqual((click.x, click.y), (0, 0))
        overwrite = Action(kind="file_copy", file_path="/tmp/source",
                           file_destination="/tmp/dest",
                           bindings={"file_overwrite": "allow"})
        self.assertTrue(vars.resolve(overwrite).file_overwrite)
        scroll = Action(kind="scroll", bindings={"scroll_amount":"n"})
        self.assertEqual(vars.resolve(scroll).scroll_amount, 5)
        with self.assertRaisesRegex(ValueError, "whole-number"):
            VariableContext([definition("n", "number", 2.5)]).resolve(scroll)
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            VariableContext([definition("n", "number", -2)]).resolve(
                Action(kind="wait", bindings={"seconds":"n"}))
        with self.assertRaises(ValueError):
            validate_action({"kind":"wait", "bindings":{"nonexistent":"n"}})
        with self.assertRaises(ValueError):
            validate_action({"kind":"wait", "bindings":{"seconds":"bad name"}})

    def test_document_v2_legacy_and_optional_variables(self):
        actions = [
            Action(kind="click", x=0, y=0, bindings={"point": "center"}),
            Action(kind="clipboard_read", result_variable="message"),
        ]
        defs = [definition("center", "coordinates", [2, 3]),
                definition("message", "text")]
        doc = serialize_document(actions, 2, 0, variables=defs)
        self.assertEqual(doc["version"], 2)
        self.assertEqual(doc["settings"]["variables"], defs)
        rebuilt, settings = parse_document(doc)
        self.assertEqual(rebuilt, actions)
        self.assertEqual(settings["variables"], defs)
        legacy = serialize_document([Action(kind="wait")], 1, 0)
        self.assertNotIn("variables", legacy["settings"])
        self.assertNotIn("variables", parse_document(legacy)[1])
        self.assertEqual(parse_document([{"kind":"wait","seconds":1}])[0][0].kind,
                         "wait")
        with self.assertRaisesRegex(ValueError, "undefined variable"):
            serialize_document(actions, 2, 0, variables=[])
        with self.assertRaisesRegex(ValueError, "must be coordinates"):
            serialize_document(actions, 2, 0, variables=[
                definition("center","text","wrong"),
                definition("message","text")])

    def test_output_type_mismatch_and_unknown_binding_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "must be text"):
            validate_references(
                [Action(kind="clipboard_read", result_variable="count")],
                [definition("count", "number", 0)])
        with self.assertRaisesRegex(ValueError, "undefined"):
            validate_references(
                [Action(kind="key", bindings={"keys": "unknown"})], [])
        with self.assertRaisesRegex(ValueError, "choose a text result"):
            validate_references([Action(kind="clipboard_read")], [],
                                require_outputs=True)
        with self.assertRaisesRegex(ValueError, "expects coordinates"):
            validate_references(
                [Action(kind="click", x=0, y=0, bindings={"point": "name"})],
                [definition("name","text","")])

    def test_preflight_warns_unset_before_producer_and_selected_start(self):
        defs = [definition("text", "text", None)]
        actions = [
            Action(kind="clipboard_read", result_variable="text"),
            Action(kind="clipboard_set", clipboard_text="",
                   bindings={"clipboard_text": "text"}),
        ]
        self.assertEqual(unset_warnings(actions, defs), [])
        self.assertEqual(len(unset_warnings(actions, defs, start_index=1)), 1)
        warnings = inspect_workflow(actions, start_index=1, variables=defs)
        self.assertTrue(any(x.severity == "warning" and
                            "no default" in x.message for x in warnings))
        wrong = inspect_workflow(
            [Action(kind="click", x=0, y=0, bindings={"point": "text"})],
            variables=defs)
        self.assertTrue(any(x.severity == "error" for x in wrong))

    def test_editor_value_parser_and_history(self):
        self.assertEqual(parse_value("42", "number"), 42.0)
        self.assertEqual(parse_value("13,-9", "coordinates"), [13, -9])
        self.assertTrue(parse_value("true", "boolean"))
        self.assertEqual(format_value([9,4], "coordinates"), "9,4")
        with self.assertRaises(ValueError):
            parse_value("__import__('os')", "number")
        history = ActionHistory()
        current = [Action(kind="wait", seconds=1)]
        old_vars = [definition("one", "text", "secret")]
        history.record(current, old_vars)
        new_vars = [definition("two", "boolean", True)]
        previous = history.undo(current, new_vars)
        self.assertEqual(previous[1], old_vars)
        self.assertEqual(history.redo(previous[0], previous[1])[1], new_vars)

    def test_preflight_dynamic_file_path_is_not_checked_too_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = str(Path(tmp) / "not-yet-exists.txt")
            actions = [
                Action(kind="file_wait", file_path="",
                       bindings={"file_path":"pathname"}, timeout=0),
            ]
            defs = [definition("pathname","text",filename)]
            findings = inspect_workflow(actions, variables=defs)
            self.assertEqual([f for f in findings if f.severity == "error"], [])


class VariableRuntimeTests(unittest.TestCase):
    def run_actions(self, actions, defs, *, overrides=None, clipboard=None,
                    automation=None, repeats=1, start_index=0):
        outcomes, diagnostics = [], []
        runner = MacroExecutor(
            actions, repeats, 0, lambda *x:None, lambda *x:outcomes.append(x),
            clipboard=clipboard, automation=automation,
            variables=defs, variable_overrides=overrides,
            start_index=start_index, on_diagnostic=diagnostics.append)
        runner.run()
        return runner, outcomes, diagnostics

    def test_clipboard_output_substitution_and_repeat_reset(self):
        defs = [definition("message", "text", "initial")]
        board = FakeClipboard(ClipboardState("text", "new secret text"))
        actions = [
            Action(kind="clipboard_set", clipboard_text="",
                   bindings={"clipboard_text":"message"}),
            Action(kind="clipboard_read", result_variable="message"),
            Action(kind="clipboard_set", clipboard_text="",
                   bindings={"clipboard_text":"message"}),
        ]
        runner, outcome, diagnostics = self.run_actions(
            actions, defs, clipboard=board, repeats=2)
        self.assertTrue(outcome[0][0], outcome)
        self.assertEqual(board.writes,
                         ["initial", "new secret text", "initial", "new secret text"])
        self.assertNotIn("new secret text", str(diagnostics))
        self.assertNotIn("new secret text", str(runner._action_indices))

    def test_run_overrides_take_priority_and_are_not_mutated(self):
        defs = [definition("message","text","default")]
        board = FakeClipboard()
        overrides = {"message":"temporary"}
        _, results, _ = self.run_actions([
            Action(kind="clipboard_set", clipboard_text="",
                   bindings={"clipboard_text":"message"}),
        ], defs, overrides=overrides, clipboard=board, repeats=3)
        self.assertTrue(results[0][0], results)
        self.assertEqual(board.writes, ["temporary"] * 3)
        self.assertEqual(overrides, {"message":"temporary"})

    def test_image_match_sets_coordinates_for_later_click(self):
        defs = [definition("hit", "coordinates", None)]
        desktop = FakeDesktop()
        actions = [
            Action(kind="click_image", image_path="ref.png", timeout=0,
                   result_variable="hit"),
            Action(kind="click", x=0, y=0, bindings={"point":"hit"}),
        ]
        with patch("macro_runtime.locate_image", return_value=(88, 77, .98)):
            runner, results, _ = self.run_actions(
                actions, defs, automation=desktop)
        self.assertTrue(results[0][0], results)
        self.assertEqual(desktop.moves, [(88, 77)])
        self.assertEqual(runner.variables.get("hit"), [88,77])
        self.assertEqual(len(desktop.clicks), 2)

    def test_run_selected_without_producer_fails_before_mouse_input(self):
        defs = [definition("hit", "coordinates", None)]
        desktop = FakeDesktop()
        actions = [
            Action(kind="click_image", image_path="ref.png", result_variable="hit"),
            Action(kind="click", x=0, y=0, bindings={"point":"hit"}),
        ]
        _, outcomes, diagnostics = self.run_actions(
            actions, defs, start_index=1, automation=desktop)
        self.assertFalse(outcomes[0][0])
        self.assertIn("unset", outcomes[0][1])
        self.assertFalse(desktop.moves)
        self.assertNotIn("hit", str(diagnostics))

    def test_nontext_clipboard_fails_without_variable_write(self):
        defs = [definition("message", "text", "previous")]
        board = FakeClipboard(ClipboardState("other", None))
        runner, outcome, _ = self.run_actions(
            [Action(kind="clipboard_read", result_variable="message")],
            defs, clipboard=board)
        self.assertFalse(outcome[0][0])
        self.assertEqual(runner.variables.get("message"), "previous")

    def test_disabled_output_is_not_produced(self):
        defs = [definition("message","text",None)]
        actions = [
            Action(kind="clipboard_read", result_variable="message",
                   enabled=False),
            Action(kind="clipboard_set", clipboard_text="",
                   bindings={"clipboard_text":"message"}),
        ]
        board = FakeClipboard()
        _, outcome, _ = self.run_actions(actions, defs, clipboard=board)
        self.assertFalse(outcome[0][0])
        self.assertEqual(board.writes, [])

    def test_files_can_use_typed_text_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = str(Path(tmp) / "folder with spaces")
            defs = [definition("folder", "text", folder)]
            action = Action(kind="folder_create",
                            bindings={"file_path":"folder"})
            _, result, _ = self.run_actions([action], defs)
            self.assertTrue(result[0][0], result)
            self.assertTrue(Path(folder).is_dir())


if __name__ == "__main__":
    unittest.main()
