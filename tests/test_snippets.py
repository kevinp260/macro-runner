"""Reusable snippets: local persistence, structure, dependencies and OS paths."""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from macro_model import Action, serialize_document, parse_document
from macro_snippets import (
    FORMAT, SCHEMA, SnippetStore, make_snippet, normalize_snippet,
    prepare_insertion,
)


def definition(name, kind, default):
    return {"name": name, "type": kind, "default": default}


def demo_actions():
    return [
        Action(kind="if_start", condition_source="pixel",
               pixel_color="#00FF00"),
        Action(kind="wait", seconds=1, bindings={"seconds": "duration"}),
        Action(kind="else"),
        Action(kind="loop_start", repeats=2),
        Action(kind="key", keys="enter"),
        Action(kind="loop_end"),
        Action(kind="if_end"),
    ]


class SnippetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SnippetStore(self.root / "library")

    def test_nested_if_else_and_loop_roundtrip(self):
        snippet = make_snippet("Conditional keys", demo_actions(),
                               [definition("duration", "number", 0.5)])
        self.assertEqual(snippet["mode"], "copy")
        self.assertEqual(snippet["format"], FORMAT)
        self.assertEqual(snippet["version"], SCHEMA)
        self.assertEqual(len(snippet["actions"]), 7)
        ident = self.store.save(snippet)
        self.assertEqual(self.store.read(ident), snippet)
        copied, merged = prepare_insertion(snippet, [])
        self.assertEqual([a.kind for a in copied], [a.kind for a in demo_actions()])
        self.assertEqual(merged, [definition("duration", "number", 0.5)])
        copied[0].name = "changed"
        self.assertEqual(self.store.read(ident), snippet)  # No live linking.

    def test_text_variable_defaults_are_not_copied(self):
        actions = [Action(kind="clipboard_set", clipboard_text="",
                          bindings={"clipboard_text": "secret"})]
        snippet = make_snippet("Text dependency", actions,
                               [definition("secret", "text", "private token")])
        self.assertEqual(snippet["variables"], [definition("secret", "text", None)])
        self.assertNotIn("private token", json.dumps(snippet))
        copied, merged = prepare_insertion(snippet, [
            definition("secret", "text", "destination value")])
        self.assertEqual(merged[0]["default"], "destination value")
        self.assertEqual(copied[0].bindings, {"clipboard_text": "secret"})

    def test_missing_reference_or_conflicting_type_is_rejected(self):
        snippet = make_snippet("Wait", [Action(
            kind="wait", bindings={"seconds": "duration"})],
            [definition("duration", "number", 2)])
        with self.assertRaisesRegex(ValueError, "expects number"):
            prepare_insertion(snippet, [definition("duration", "text", "2")])
        document = deepcopy(snippet)
        document["variables"] = []
        with self.assertRaisesRegex(ValueError, "declarations"):
            normalize_snippet(document)

    def test_existing_workflow_defaults_are_not_overwritten(self):
        snippet = make_snippet("Wait", [Action(
            kind="wait", bindings={"seconds": "duration"})],
            [definition("duration", "number", 2)])
        prior = [definition("duration", "number", 10)]
        actions, definitions = prepare_insertion(snippet, prior)
        self.assertEqual(definitions, prior)
        self.assertEqual(actions[0].bindings, {"seconds": "duration"})
        definitions[0]["default"] = 3
        self.assertEqual(prior[0]["default"], 10)

    def test_library_rename_replace_delete_are_independent(self):
        first = self.store.save(make_snippet("A", [Action(kind="wait")], []))
        second = self.store.save(make_snippet("B", [Action(kind="wait")], []))
        self.store.rename(first, "Edited")
        self.assertEqual(self.store.read(first)["name"], "Edited")
        self.assertEqual(self.store.read(second)["name"], "B")
        self.store.replace(first, make_snippet("Replaced",
                                                [Action(kind="key")], []))
        self.assertEqual(self.store.read(first)["actions"][0]["kind"], "key")
        self.store.delete(first)
        self.assertEqual(len(self.store.list()), 1)
        with self.assertRaises(ValueError):
            self.store.read(first)

    def test_import_export_and_relative_image_reference(self):
        image = self.root / "reference.png"
        Image.new("RGB", (3, 3), color="red").save(image)
        source = self.root / "external.json"
        original = make_snippet("Image", [
            Action(kind="click_image", image_path="reference.png")], [])
        source.write_text(json.dumps(original), encoding="utf-8")
        ident = self.store.import_file(source)
        imported = self.store.read(ident)
        self.assertEqual(imported["actions"][0]["image_path"], str(image))
        self.assertEqual(len(prepare_insertion(imported, [])[0]), 1)
        out = self.root / "out.json"
        self.store.export_file(ident, out)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), imported)
        image.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            prepare_insertion(imported, [])

    def test_image_validation_checks_readable_content(self):
        image = self.root / "broken.png"
        image.write_text("not an image", encoding="utf-8")
        snippet = make_snippet("Broken image",
                               [Action(kind="click_image", image_path=str(image))], [])
        with self.assertRaisesRegex(ValueError, "unreadable"):
            prepare_insertion(snippet, [])

    def test_image_variable_default_is_validated(self):
        snippet = make_snippet("Bound image", [
            Action(kind="click_image", image_path="",
                   bindings={"image_path": "template"})], [
            definition("template", "text", "original path")])
        self.assertEqual(snippet["variables"][0]["default"], None)
        prepare_insertion(snippet, [])  # A future output or override can supply it.
        with self.assertRaisesRegex(ValueError, "missing"):
            prepare_insertion(snippet, [
                definition("template", "text", str(self.root / "missing.png"))])

    def test_import_windows_style_relative_image_paths(self):
        image_dir = self.root / "images"
        image_dir.mkdir()
        image = image_dir / "reference.png"
        Image.new("RGB", (3, 3), color="blue").save(image)
        source = self.root / "win-relative.json"
        snippet = make_snippet("Relative image", [
            Action(kind="click_image", image_path=r"images\reference.png")], [])
        source.write_text(json.dumps(snippet), encoding="utf-8")
        imported = self.store.read(self.store.import_file(source))
        if os.name != "nt":
            self.assertEqual(imported["actions"][0]["image_path"], str(image))
            prepare_insertion(imported, [])

    def test_foreign_windows_path_is_not_resolved_as_posix_relative(self):
        path = r"C:\Users\someone\reference.png"
        snippet = make_snippet("Windows image", [
            Action(kind="click_image", image_path=path)], [],
            base_dir=self.root)
        self.assertEqual(snippet["actions"][0]["image_path"], path)
        if os.name != "nt":
            with self.assertRaisesRegex(ValueError, "another operating system"):
                prepare_insertion(snippet, [])

    def test_reject_malformed_and_nested_loop_snippets(self):
        original = make_snippet("Valid", [Action(kind="wait")], [])
        for change in (
            {"mode": "link"},
            {"version": 999},
            {"actions": [asdict(Action(kind="if_start", condition_source="pixel"))]},
            {"actions": []},
        ):
            invalid = dict(original, **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_snippet(invalid)
        nested_loops = [
            Action(kind="loop_start"), Action(kind="loop_start"),
            Action(kind="wait"), Action(kind="loop_end"), Action(kind="loop_end")]
        with self.assertRaises(ValueError):
            make_snippet("bad", nested_loops, [])

    def test_invalid_json_and_unsafe_ids_never_change_library(self):
        (self.store.directory).mkdir()
        (self.store.directory / ("a" * 32 + ".json")).write_text(
            '{"not":"a snippet"}', encoding="utf-8")
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(ValueError):
            self.store.read("../../other")
        bad = self.root / "bad.json"
        bad.write_text('{"actions": [}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.import_file(bad)
        self.assertEqual(self.store.list(), [])

    def test_regular_macro_format_is_unchanged_by_snippets(self):
        workflow = [Action(kind="wait")]
        before = serialize_document(workflow, 3, 0)
        self.store.save(make_snippet("wait", workflow, []))
        after = serialize_document(workflow, 3, 0)
        self.assertEqual(before, after)
        actions, settings = parse_document(before)
        self.assertEqual(actions, workflow)
        self.assertEqual(settings["repeat_count"], 3)


if __name__ == "__main__":
    unittest.main()
