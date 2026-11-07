"""Atomic local recovery tests; no desktop input required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macro_model import Action, parse_document, serialize_document
from macro_recovery import (MAX_RECOVERY_BYTES, RecoveryStore,
                            atomic_json_write)


class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "local" / "workflow-recovery.json"
        self.store = RecoveryStore(self.path)

    def test_full_snapshot_reopens_with_settings_and_source(self):
        actions = [Action(kind="key", keys="test text"),
                   Action(kind="wait", seconds=2)]
        self.store.write(actions, 4, 2.5, self.root / "original.json")
        recovered = self.store.read()
        self.assertEqual(recovered.actions, actions)
        self.assertEqual(recovered.repeat_count, 4)
        self.assertEqual(recovered.start_delay, 2.5)
        self.assertEqual(recovered.source_file, str(self.root / "original.json"))
        self.assertIn("T", recovered.saved_at)
        self.assertIn("test text", self.path.read_text(encoding="utf-8"))
        # A recovery is not the original user file.
        self.assertFalse((self.root / "original.json").exists())

    def test_single_snapshot_is_replaced_without_leftover_temp_files(self):
        self.store.write([Action(kind="key", keys="old")], 1, 0)
        self.store.write([Action(kind="key", keys="new")], 2, 1)
        self.assertEqual(self.store.read().actions[0].keys, "new")
        self.assertEqual(self.store.read().repeat_count, 2)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.store.clear()
        self.assertIsNone(self.store.read())

    def test_failed_atomic_replace_retains_previous_complete_snapshot(self):
        self.store.write([Action(kind="key", keys="original")], 1, 0)
        previous = self.path.read_bytes()
        with patch("macro_recovery.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.store.write([Action(kind="key", keys="later")], 3, 0)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_user_save_does_not_truncate_original(self):
        user_file = self.root / "saved.json"
        user_file.write_text("original", encoding="utf-8")
        with patch("macro_recovery.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                atomic_json_write(user_file, {"actions": []})
        self.assertEqual(user_file.read_text(encoding="utf-8"), "original")
        self.assertEqual(list(self.root.iterdir()), [user_file])

    def test_corruption_schema_and_limit_are_rejected_without_deletion(self):
        self.path.parent.mkdir(parents=True)
        for payload in ('{broken', '{"schema":99}', '{"schema":1,"document":{}}'):
            with self.subTest(payload=payload):
                self.path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.store.read()
                self.assertEqual(self.path.read_text(encoding="utf-8"), payload)
        self.path.write_bytes(b"X" * (MAX_RECOVERY_BYTES + 1))
        with self.assertRaises(ValueError):
            self.store.read()
        self.assertTrue(self.path.exists())

    def test_wrapped_legacy_list_is_compatible(self):
        # Older user documents may be raw action arrays. Recovery can read
        # a wrapped array without changing the user's on-disk document.
        data = {"schema":1, "saved_at":"2026-11-07T19:00:00+00:00",
                "source_file":None, "document":[{"kind":"key","keys":"legacy"}]}
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        result = self.store.read()
        self.assertEqual(result.actions[0].keys, "legacy")
        self.assertEqual((result.repeat_count, result.start_delay), (1, 3.0))

    def test_original_macro_document_format_is_unchanged(self):
        actions = [Action(kind="wait", seconds=1)]
        legacy = [{"kind":"key","keys":"enter"}]
        self.assertEqual(parse_document(legacy)[0][0].keys, "enter")
        document = serialize_document(actions, 2, 1)
        self.store.write(actions, 2, 1)
        self.assertEqual(json.loads(self.path.read_text())["document"], document)
        self.assertNotIn("recovery", document)


if __name__ == "__main__":
    unittest.main()
