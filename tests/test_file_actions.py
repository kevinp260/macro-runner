"""Local filesystem workflow actions: safe conflicts, polling and cancellation."""
from dataclasses import asdict
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from macro_files import (FileActionError, local_path, run_file_action,
                         validate_file_action)
from macro_model import Action, parse_document, serialize_document, validate_action
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_playback import PlaybackGate
from macro_qt_workflow import description
from macro_workflow import default_node


class Gate:
    def __init__(self, stop_at=None, on_wait=None):
        self.calls = []
        self.stop_at = stop_at
        self.on_wait = on_wait

    def wait(self, value):
        self.calls.append(value)
        if self.on_wait:
            self.on_wait(value)
        if self.stop_at is not None and len(self.calls) >= self.stop_at:
            raise RuntimeError("Stopped")


class FileActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source 日本語.txt"
        self.source.write_text("old\nHello á 😊", encoding="utf-8")
        self.target = self.root / "target with spaces.txt"

    def action(self, kind, **kwargs):
        values = {"kind": kind, "file_path": str(self.source),
                  "file_destination": str(self.target)}
        values.update(kwargs)
        return Action(**values)

    def test_file_exists_and_wait_until_exists(self):
        run_file_action(self.action("file_check"), Gate())
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            run_file_action(self.action("file_check"), Gate())
        with self.assertRaises(TimeoutError):
            run_file_action(self.action("file_wait", timeout=0), Gate())
        with self.assertRaises(TimeoutError):
            run_file_action(self.action("file_wait", timeout=.2, poll_interval=.1),
                            Gate())
        self.assertFalse(self.target.exists())
        gate = Gate(on_wait=lambda delay: self.source.write_text(
            "arrived", encoding="utf-8") if delay > 0 else None)
        run_file_action(self.action("file_wait", timeout=.4, poll_interval=.1),
                        gate)
        self.assertEqual(self.source.read_text(), "arrived")
        self.assertIn(.1, gate.calls)

    def test_copy_preserves_source_and_requires_explicit_overwrite(self):
        original = self.source.read_bytes()
        run_file_action(self.action("file_copy"), Gate())
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)
        self.source.write_text("new version", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            run_file_action(self.action("file_copy"), Gate())
        self.assertEqual(self.target.read_bytes(), original)
        run_file_action(self.action("file_copy", file_overwrite=True), Gate())
        self.assertEqual(self.target.read_text(), "new version")
        self.assertEqual(self.source.read_text(), "new version")

    def test_move_removes_source_only_after_successful_destination_write(self):
        original = self.source.read_bytes()
        run_file_action(self.action("file_move"), Gate())
        self.assertFalse(self.source.exists())
        self.assertEqual(self.target.read_bytes(), original)

    def test_move_conflict_keeps_source_and_destination(self):
        self.target.write_text("unrelated existing file", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            run_file_action(self.action("file_move"), Gate())
        self.assertTrue(self.source.is_file())
        self.assertEqual(self.target.read_text(), "unrelated existing file")
        run_file_action(self.action("file_move", file_overwrite=True), Gate())
        self.assertFalse(self.source.exists())
        self.assertEqual(self.target.read_text(), "old\nHello á 😊")

    def test_overwrite_copy_failure_preserves_existing_destination(self):
        self.target.write_text("keep this", encoding="utf-8")
        with patch("macro_files._copy_chunks", side_effect=OSError("read failure")):
            with self.assertRaises(OSError):
                run_file_action(self.action("file_copy", file_overwrite=True),
                                Gate())
        self.assertEqual(self.target.read_text(), "keep this")
        self.assertTrue(self.source.exists())
        self.assertEqual(list(self.root.glob(".macrorunner-copy-*")), [])

    def test_overwrite_move_stop_preserves_both_original_files(self):
        self.target.write_text("keep existing", encoding="utf-8")
        gate = Gate(stop_at=4)
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            run_file_action(self.action("file_move", file_overwrite=True), gate)
        self.assertTrue(self.source.is_file())
        self.assertEqual(self.target.read_text(), "keep existing")
        self.assertEqual(list(self.root.glob(".macrorunner-copy-*")), [])

    def test_copy_stop_discards_partial_new_destination(self):
        with self.source.open("wb") as stream:
            stream.write(b"a" * (2 * 1024 * 1024))
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            run_file_action(self.action("file_copy"), Gate(stop_at=4))
        self.assertFalse(self.target.exists())
        self.assertTrue(self.source.is_file())

    def test_create_folder_recursive_idempotent_and_file_collision(self):
        path = self.root / "f o l d e r" / "child 😄"
        action = Action(kind="folder_create", file_path=str(path))
        run_file_action(action, Gate())
        self.assertTrue(path.is_dir())
        run_file_action(action, Gate())
        with self.assertRaises(FileExistsError):
            run_file_action(Action(kind="folder_create", file_path=str(self.source)),
                            Gate())

    def test_no_relative_paths_parent_traversal_or_same_file(self):
        for value in ("relative.txt", "../unsafe.txt", "a/../unsafe.txt",
                      str(self.root / ".." / "outside"), "",
                      " " + str(self.source), str(self.source) + "\n"):
            with self.subTest(value=value), self.assertRaises(FileActionError):
                local_path(value, "File", required=True)
        with patch("macro_files.Path.expanduser",
                   side_effect=RuntimeError("unknown account")):
            with self.assertRaisesRegex(FileActionError, "home directory"):
                local_path("~unavailable/file.txt", "File")
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="file_copy", file_path=str(self.source),
                                   file_destination=str(self.source)), Gate())
        linked = self.root / "hardlinked"
        os.link(self.source, linked)
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="file_move", file_path=str(self.source),
                                   file_destination=str(linked),
                                   file_overwrite=True), Gate())
        self.assertTrue(self.source.exists())

    def test_reject_symlinks_and_directories_for_mutation(self):
        symlink = self.root / "linked file"
        try:
            symlink.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink permissions")
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="file_copy", file_path=str(symlink),
                                   file_destination=str(self.target)), Gate())
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="file_copy", file_path=str(self.source),
                                   file_destination=str(symlink),
                                   file_overwrite=True), Gate())
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="folder_create", file_path=str(symlink)),
                            Gate())
        with self.assertRaises(FileActionError):
            run_file_action(Action(kind="file_move", file_path=str(self.root),
                                   file_destination=str(self.target)), Gate())
        self.assertTrue(self.source.exists())

    def test_missing_dest_parent_and_permission_failure(self):
        invalid_target = self.root / "missing" / "file.txt"
        with self.assertRaises(FileNotFoundError):
            run_file_action(
                Action(kind="file_copy", file_path=str(self.source),
                       file_destination=str(invalid_target)), Gate())
        self.assertTrue(self.source.exists())
        with patch("macro_files.Path.open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                run_file_action(self.action("file_copy"), Gate())
        self.assertFalse(self.target.exists())

    def test_model_validation_defaults_save_and_legacy_compat(self):
        for kind in ("file_check", "file_wait", "file_copy",
                     "file_move", "folder_create"):
            with self.subTest(kind=kind):
                node = default_node(kind)
                self.assertEqual(node.action.kind, kind)
                self.assertFalse(node.action.file_overwrite)
                self.assertEqual(validate_action(asdict(node.action)), node.action)
        original = [self.action("file_copy", file_overwrite=True),
                    self.action("file_wait", timeout=.3),
                    Action(kind="folder_create", file_path=str(self.root / "new"))]
        self.assertEqual(parse_document(
            serialize_document(original, 2, .1))[0], original)
        self.assertEqual(parse_document([{"kind":"wait", "seconds":1}])[0][0].kind,
                         "wait")
        self.assertNotIn("old\nHello", description(original[0]))
        for invalid in (1, "yes", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_action({"kind":"file_copy", "file_overwrite":invalid})

    def test_preflight_rejects_missing_path_but_allows_future_file(self):
        blank = [Action(kind="file_copy"), Action(kind="wait", seconds=0)]
        findings = inspect_workflow(blank)
        self.assertTrue(any(f.severity == "error" for f in findings))
        waiting = [Action(kind="file_wait",file_path=str(self.target),
                          timeout=.2)]
        self.assertEqual(inspect_workflow(waiting), [])
        missing = [self.action("file_check")]
        self.source.unlink()
        self.assertTrue(any(f.severity == "warning"
                            for f in inspect_workflow(missing)))
        disabled = [Action(kind="file_copy", enabled=False),
                    Action(kind="wait", seconds=0)]
        self.assertEqual(inspect_workflow(disabled), [])

    def test_runtime_file_only_workflow_avoids_desktop_backend(self):
        results = []
        runner = MacroExecutor([
            self.action("file_check"),
            Action(kind="folder_create", file_path=str(self.root / "generated")),
            self.action("file_copy"),
        ], 1, 0, lambda *args:None, lambda *args:results.append(args))
        with patch.object(runner, "_pag", side_effect=AssertionError("no desktop")):
            runner.run()
        self.assertTrue(results[0][0], results)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_runtime_skip_file_failure_runs_next_action(self):
        results, diagnostics = [], []
        runner = MacroExecutor([
            self.action("file_copy", file_destination=str(self.source),
                        failure_policy="skip"),
            Action(kind="folder_create", file_path=str(self.root / "later")),
        ], 1, 0, lambda *args:None, lambda *args:results.append(args),
        on_diagnostic=diagnostics.append)
        runner.run()
        self.assertTrue(results[0][0], results)
        self.assertTrue((self.root / "later").is_dir())
        self.assertTrue(any(e["event"] == "action_skipped" for e in diagnostics))
        self.assertNotIn("Hello", str(diagnostics))

    def test_pause_stop_interrupts_wait_and_prevents_followup_file_mutation(self):
        done, outcomes = threading.Event(), []
        runner = MacroExecutor([
            Action(kind="file_wait", file_path=str(self.target),
                   timeout=15, poll_interval=.1),
            Action(kind="folder_create", file_path=str(self.root / "unsafe")),
        ], 1, 0, lambda *args:None,
           lambda *args:(outcomes.append(args), done.set()))
        runner.start()
        runner.stop()
        self.assertTrue(done.wait(3))
        self.assertFalse(outcomes[0][0])
        self.assertFalse((self.root / "unsafe").exists())

    def test_step_one_file_action_at_a_time(self):
        completed = threading.Event()
        outcomes = []
        runner = MacroExecutor([
            Action(kind="folder_create", file_path=str(self.root / "one")),
            Action(kind="folder_create", file_path=str(self.root / "two")),
        ], 1, 0, lambda *args:None,
           lambda *args:(outcomes.append(args), completed.set()),
           step_mode=True)
        runner.start()
        self.assertFalse(completed.wait(.05))
        runner.step()
        self.assertTrue((self.root / "one").exists() or
                        not completed.wait(.1))
        self.assertFalse((self.root / "two").exists())
        runner.step()
        self.assertTrue(completed.wait(3))
        self.assertTrue(outcomes[0][0], outcomes)
        self.assertTrue((self.root / "two").is_dir())


if __name__ == "__main__":
    unittest.main()
