"""Portable workflow ZIP tests: cross-directory paths and hostile archives."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

from PIL import Image

from macro_model import Action, parse_document, serialize_document
from macro_packages import (export_package, import_package, inspect_package,
                            plan_package)


def document(actions, variables=None):
    return serialize_document(actions, 1, 0, variables=variables)


def image_action(filename):
    return Action(kind="click_image", image_path=str(filename))


class PortablePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "source"
        self.sources.mkdir()
        self.assets_root = self.root / "destination" / "assets"
        self.package = self.root / "transfer.mrpkg"

    def make_image(self, name="reference.png", color="green"):
        path = self.sources / name
        Image.new("RGB", (8, 8), color).save(path)
        return path

    def repack(self, changes=None, additions=None):
        changes = changes or {}
        additions = additions or []
        with zipfile.ZipFile(self.package) as archive:
            entries = [(info.filename, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(self.package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, changes.get(name, data))
            for name, content in additions:
                archive.writestr(name, content)

    def test_plain_workflow_without_images(self):
        original = document([Action(kind="wait", seconds=2)])
        plan = export_package(self.package, original)
        self.assertEqual(plan.assets, ())
        self.assertEqual(inspect_package(self.package)["image_count"], 0)
        imported = import_package(self.package, self.assets_root)
        self.assertEqual(imported, original)
        self.assertFalse(self.assets_root.exists())

    def test_round_trip_rebases_images_into_managed_assets(self):
        picture = self.make_image()
        original = document([image_action(picture)])
        unchanged = deepcopy(original)
        plan = export_package(self.package, original, self.sources)
        self.assertEqual(original, unchanged)
        self.assertEqual(len(plan.assets), 1)
        with zipfile.ZipFile(self.package) as archive:
            portable = json.loads(archive.read("workflow.json"))
        self.assertTrue(portable["actions"][0]["image_path"].startswith("assets/"))
        self.assertNotIn(str(self.sources), json.dumps(portable))
        imported = import_package(self.package, self.assets_root)
        target = Path(imported["actions"][0]["image_path"])
        self.assertTrue(target.is_file())
        self.assertTrue(target.is_relative_to(self.assets_root))
        self.assertEqual(target.read_bytes(), picture.read_bytes())
        self.assertEqual(parse_document(imported)[0][0].image_path, str(target))
        # Saving as ordinary JSON still preserves the imported local path.
        json_file = self.root / "saved.json"
        json_file.write_text(json.dumps(imported), encoding="utf-8")
        reopened = parse_document(json.loads(json_file.read_text()))
        self.assertEqual(reopened[0][0].image_path, str(target))

    def test_relative_image_paths_resolve_from_source_workflow_directory(self):
        self.make_image()
        workflow = document([image_action("reference.png")])
        plan = plan_package(workflow, self.sources)
        self.assertEqual(len(plan.assets), 1)
        export_package(self.package, workflow, self.sources)
        imported = import_package(self.package, self.assets_root)
        self.assertTrue(Path(imported["actions"][0]["image_path"]).is_file())

    def test_duplicate_asset_basenames_remain_distinct(self):
        first = self.make_image("same.png", "red")
        folder = self.sources / "other"
        folder.mkdir()
        second = folder / "same.png"
        Image.new("RGB", (8, 8), "blue").save(second)
        original = document([image_action(first), image_action(second)])
        plan = export_package(self.package, original)
        self.assertEqual(len(plan.assets), 2)
        imported = import_package(self.package, self.assets_root)
        paths = [Path(a["image_path"]) for a in imported["actions"]]
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual(paths[0].read_bytes(), first.read_bytes())
        self.assertEqual(paths[1].read_bytes(), second.read_bytes())

    def test_identical_image_contents_are_deduplicated(self):
        first = self.make_image("first.png")
        second = self.sources / "second.png"
        second.write_bytes(first.read_bytes())
        plan = export_package(self.package, document([
            image_action(first), image_action(second)]))
        self.assertEqual(len(plan.assets), 1)
        imported = import_package(self.package, self.assets_root)
        self.assertEqual(imported["actions"][0]["image_path"],
                         imported["actions"][1]["image_path"])

    def test_image_conditions_in_nested_groups_are_packed(self):
        picture = self.make_image()
        original = document([
            Action(kind="if_start", image_path=str(picture)),
            Action(kind="wait"),
            Action(kind="if_end"),
        ])
        export_package(self.package, original)
        imported = import_package(self.package, self.assets_root)
        self.assertTrue(Path(imported["actions"][0]["image_path"]).exists())
        self.assertEqual([a.kind for a in parse_document(imported)[0]],
                         ["if_start", "wait", "if_end"])

    def test_bound_image_defaults_are_rebased(self):
        picture = self.make_image()
        definitions = [{"name": "reference", "type": "text",
                        "default": str(picture)}]
        original = document([Action(kind="click_image", image_path="old.png",
                                    bindings={"image_path": "reference"})], definitions)
        export_package(self.package, original)
        with zipfile.ZipFile(self.package) as archive:
            portable = json.loads(archive.read("workflow.json"))
        self.assertEqual(portable["actions"][0]["image_path"], "")
        imported = import_package(self.package, self.assets_root)
        target = Path(imported["settings"]["variables"][0]["default"])
        self.assertTrue(target.exists())
        self.assertEqual(imported["actions"][0]["image_path"], "")
        self.assertNotIn(str(picture), json.dumps(imported))

    def test_unset_dynamic_image_variable_does_not_invent_an_asset(self):
        original = document(
            [Action(kind="click_image", image_path="",
                    bindings={"image_path": "reference"})],
            [{"name": "reference", "type": "text", "default": None}])
        plan = export_package(self.package, original)
        self.assertEqual(plan.assets, ())
        self.assertTrue(any("override" in warning for warning in plan.warnings))
        self.assertEqual(import_package(self.package, self.assets_root),
                         original)

    def test_missing_image_refuses_to_create_package(self):
        workflow = document([image_action(self.sources / "missing.png")])
        with self.assertRaisesRegex(ValueError, "missing"):
            export_package(self.package, workflow)
        self.assertFalse(self.package.exists())

    def test_invalid_image_and_foreign_windows_path_rejected(self):
        (self.sources / "not-an-image.png").write_text("not an image")
        for value in (str(self.sources / "not-an-image.png"),
                      r"C:\Users\person\Desktop\image.png"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plan_package(document([image_action(value)]), self.sources)

    def test_export_rejects_change_to_image_source(self):
        picture = self.make_image()
        plan = plan_package(document([image_action(picture)]))
        picture.write_bytes(b"changed")
        from macro_packages import write_package
        with self.assertRaisesRegex(ValueError, "changed"):
            write_package(self.package, plan)
        self.assertFalse(self.package.exists())
        self.assertEqual(list(self.root.glob(".macro-package-*")), [])

    def test_traversal_and_extra_archive_members_rejected(self):
        picture = self.make_image()
        workflow = document([image_action(picture)])
        for extra in ("../outside.png", "/root/evil.png", r"..\windows.png",
                      "assets/other.txt", "other.json", "assets/folder/"):
            with self.subTest(extra=extra):
                export_package(self.package, workflow)
                self.repack(additions=[(extra, b"unexpected")])
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    import_package(self.package, self.assets_root)
                self.assertFalse(self.assets_root.exists())

    def test_duplicate_zip_entry_rejected(self):
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.repack(additions=[("workflow.json", b"{}")])
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            import_package(self.package, self.assets_root)

    def test_symlink_entry_rejected(self):
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with zipfile.ZipFile(self.package, "a") as archive:
            link = zipfile.ZipInfo("assets/" + "a" * 64 + ".png")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "outside")
        with self.assertRaises(ValueError):
            import_package(self.package, self.assets_root)

    def test_unlisted_image_and_external_reference_rejected(self):
        picture = self.make_image()
        for wrong in ("../../private.png", "/tmp/private.png", "assets/no.png"):
            with self.subTest(wrong=wrong):
                export_package(self.package, document([image_action(picture)]))
                with zipfile.ZipFile(self.package) as archive:
                    workflow = json.loads(archive.read("workflow.json"))
                workflow["actions"][0]["image_path"] = wrong
                self.repack(changes={"workflow.json": json.dumps(workflow).encode()})
                with self.assertRaisesRegex(ValueError, "not packaged"):
                    import_package(self.package, self.assets_root)
                self.assertFalse(self.assets_root.exists())

    def test_corrupted_image_checksum_rolls_back_all_imports(self):
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with zipfile.ZipFile(self.package) as archive:
            asset_name = next(n for n in archive.namelist() if n.startswith("assets/"))
            data = archive.read(asset_name)
        self.repack(changes={asset_name: b"x" * len(data)})
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            import_package(self.package, self.assets_root)
        self.assertEqual(list(self.assets_root.iterdir()), [])

    def test_prior_managed_assets_not_modified_on_failed_import(self):
        prior = self.assets_root / "already-here"
        prior.mkdir(parents=True)
        marker = prior / "keep.txt"
        marker.write_text("important")
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with zipfile.ZipFile(self.package) as archive:
            name = next(n for n in archive.namelist() if n.startswith("assets/"))
            data = archive.read(name)
        self.repack(changes={name: b"?" * len(data)})
        with self.assertRaises(ValueError):
            import_package(self.package, self.assets_root)
        self.assertEqual(marker.read_text(), "important")
        self.assertEqual(list(self.assets_root.iterdir()), [prior])

    def test_manifest_and_header_size_validation(self):
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with zipfile.ZipFile(self.package) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        manifest["assets"][0]["size"] += 1
        self.repack(changes={"manifest.json": json.dumps(manifest).encode()})
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            import_package(self.package, self.assets_root)
        self.assertFalse(self.assets_root.exists())

    def test_large_archive_entry_refused_before_extracting(self):
        picture = self.make_image()
        export_package(self.package, document([image_action(picture)]))
        with zipfile.ZipFile(self.package) as archive:
            name = next(n for n in archive.namelist() if n.startswith("assets/"))
        self.repack(changes={name: b"z" * (16 * 1024 * 1024 + 1)})
        with self.assertRaisesRegex(ValueError, "too large"):
            import_package(self.package, self.assets_root)
        self.assertFalse(self.assets_root.exists())

    def test_existing_package_is_not_truncated_on_export_error(self):
        picture = self.make_image()
        self.package.write_bytes(b"original file")
        plan = plan_package(document([image_action(picture)]))
        picture.write_bytes(b"changed")
        from macro_packages import write_package
        with self.assertRaises(ValueError):
            write_package(self.package, plan)
        self.assertEqual(self.package.read_bytes(), b"original file")


if __name__ == "__main__":
    unittest.main()
