"""Run-history persistence, privacy, retention, and executor diagnostics."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from macro_diagnostics import (
    MAX_EVENTS, RunHistoryStore, RunSession, action_paths, safe_error_code,
)
from macro_model import Action
from macro_runtime import MacroExecutor


def sample_actions():
    return [
        Action(kind="if_start", condition_source="pixel"),
        Action(kind="wait", seconds=0),
        Action(kind="else"),
        Action(kind="watch_start", region_x=0, region_y=0,
               region_w=10, region_h=10, watch_max_changes=1,
               poll_interval=.1, watch_confirmations=1),
        Action(kind="key", keys="PRIVATE_PASSWORD_12345", name="PRIVATE_LOGIN"),
        Action(kind="watch_end"),
        Action(kind="if_end"),
    ]


class DiagnosticsTests(unittest.TestCase):
    def test_action_paths_include_else_branch_and_nested_context(self):
        paths = action_paths(sample_actions())
        self.assertEqual(paths[1], ["if_start", "wait"])
        self.assertEqual(paths[3], ["if_start", "else", "watch_start"])
        self.assertEqual(paths[4], ["if_start", "else", "watch_start", "key"])
        self.assertEqual(paths[6], ["if_start", "else", "if_end"])

    def test_events_are_bounded_redacted_and_report_counts(self):
        session = RunSession(sample_actions(), mode="selected", repeat_count=2)
        for _ in range(MAX_EVENTS + 9):
            session.add({"event": "action_done", "index": 4,
                         "keys": "PRIVATE_PASSWORD_12345", "name": "PRIVATE_LOGIN",
                         "path": ["PRIVATE_LOGIN"], "raw_error": "SECRET"})
        session.add({"event": "action_error", "index": 4,
                     "error": "TimeoutError", "message": "SECRET"})
        record = session.finish("error")
        self.assertEqual(len(record["events"]), MAX_EVENTS)
        self.assertEqual(record["dropped_events"], 10)
        self.assertEqual(record["completed_actions"], MAX_EVENTS + 9)
        self.assertEqual(record["error_code"], "TimeoutError")
        self.assertIn("else", record["events"][-1]["path"])
        blob = json.dumps(record)
        self.assertNotIn("PRIVATE_PASSWORD", blob)
        self.assertNotIn("PRIVATE_LOGIN", blob)
        self.assertNotIn("SECRET", blob)
        self.assertEqual(safe_error_code(PermissionError("secret")), "PermissionError")

    def test_store_atomic_bounded_and_export_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunHistoryStore(Path(tmp) / "history.json", max_runs=3)
            for i in range(5):
                run = RunSession([Action(kind="key", keys="secrets")])
                run.add({"event": "action_start", "index": 0, "keys": "secrets"})
                run.add({"event": "action_done", "index": 0})
                record = run.finish("completed")
                record["accidental_secret"] = "PRIVATE_PASSWORD"
                store.add(record)
            self.assertEqual(len(store.runs), 3)
            self.assertEqual([r["status"] for r in store.runs],
                             ["completed"] * 3)
            persisted = store.path.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_PASSWORD", persisted)
            self.assertNotIn("secrets", persisted)
            restored = RunHistoryStore(store.path, max_runs=3)
            self.assertEqual(len(restored.runs), 3)
            export_path = Path(tmp) / "export.json"
            self.assertEqual(restored.export_safe(export_path), 3)
            self.assertNotIn("PRIVATE_PASSWORD", export_path.read_text())
            self.assertEqual(json.loads(export_path.read_text())["schema"], 1)

    def test_opt_in_capture_is_scaled_rotated_and_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RunHistoryStore(Path(tmp) / "run-history.json",
                                    max_screenshots=2)
            image = Image.new("RGB", (1600, 1000), "purple")
            for _ in range(3):
                run = RunSession([Action(kind="click", x=1, y=2)])
                run.add({"event": "action_error", "index": 0, "error": "OSError"})
                store.add(run.finish("error"), capture=image)
            self.assertEqual(len(store._capture_files()), 2)
            self.assertNotIn("screenshot", store.runs[0])
            self.assertTrue(all("screenshot" in r for r in store.runs[1:]))
            with Image.open(store.capture_dir / store.runs[-1]["screenshot"]) as pic:
                self.assertLessEqual(pic.width, 1280)
                self.assertLessEqual(pic.height, 800)
                self.assertEqual(pic.format, "JPEG")
            store.set_max_screenshots(1)
            self.assertEqual(len(store._capture_files()), 1)
            success = RunSession([Action(kind="wait", seconds=0)])
            store.add(success.finish("completed"), capture=image)
            self.assertNotIn("screenshot", store.runs[-1])
            store.clear()
            self.assertEqual(store.runs, [])
            self.assertEqual(store._capture_files(), [])

    def test_failed_screenshot_save_still_persists_run(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            store = RunHistoryStore(Path(tmp) / "history.json")
            run = RunSession([Action(kind="wait", seconds=0)])
            run.add({"event": "action_error", "index": 0,
                     "error": "PermissionError"})
            with patch.object(store, "_save_capture",
                              side_effect=PermissionError("private location")):
                store.add(run.finish("error"),
                          capture=Image.new("RGB", (20, 20), "white"))
            self.assertEqual(len(store.runs), 1)
            self.assertNotIn("screenshot", store.runs[0])
            self.assertIn("screenshot_unavailable",
                          [e["event"] for e in store.runs[0]["events"]])
            self.assertNotIn("private location", store.path.read_text())

    def test_corrupt_history_and_unsafe_capture_reference_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text("not json", encoding="utf-8")
            store = RunHistoryStore(path)
            self.assertEqual(store.runs, [])
            path.write_text(json.dumps({"schema": 1, "runs": [{
                "status": "error", "id": "abc", "started_at": "",
                "ended_at": "", "screenshot": "../../private.txt",
                "events": [{"event": "action_done", "keys": "PRIVATE_VALUE",
                            "at_s": 0}]
            }]}), encoding="utf-8")
            store = RunHistoryStore(path)
            self.assertNotIn("screenshot", store.runs[0])
            self.assertNotIn("PRIVATE_VALUE", json.dumps(store.runs))


class ExecutorEventTests(unittest.TestCase):
    class Automation:
        def __init__(self, fail=False):
            self.fail = fail
            self.calls = []
        def keyDown(self, key): pass
        def keyUp(self, key): pass
        def press(self, key):
            self.calls.append(("press", key))
            if self.fail:
                raise TimeoutError("PRIVATE_PASSWORD")
        def screenshot(self, region=None):
            return Image.new("RGB", (25, 20), "black")

    def test_emits_no_typed_input_on_success_or_error(self):
        a = Action(kind="key", keys="PRIVATE_PASSWORD_12345", name="PRIVATE_LOGIN")
        for fail in (False, True):
            with self.subTest(fail=fail):
                events, captures, finished = [], [], []
                executor = MacroExecutor([a], 1, 0, lambda *x: None,
                    lambda *x: finished.append(x), automation=self.Automation(fail),
                    on_diagnostic=events.append,
                    on_failure_capture=captures.append)
                executor.run()
                self.assertEqual(finished[0][0], not fail)
                self.assertIn("action_start", [e["event"] for e in events])
                self.assertIn("action_error" if fail else "action_done",
                              [e["event"] for e in events])
                self.assertEqual(len(captures), 1 if fail else 0)
                self.assertNotIn("PRIVATE_PASSWORD", str(events))
                self.assertNotIn("PRIVATE_LOGIN", str(events))

    def test_stop_does_not_screenshot_and_sink_failure_is_non_fatal(self):
        finished, captures = [], []
        executor = MacroExecutor(
            [Action(kind="wait", seconds=0)], 1, 0,
            lambda *x: None, lambda *x: finished.append(x),
            automation=self.Automation(),
            on_diagnostic=lambda e: (_ for _ in ()).throw(OSError("logging failed")),
            on_failure_capture=captures.append)
        executor.run()
        self.assertTrue(finished[0][0])
        executor2 = MacroExecutor(
            [Action(kind="wait", seconds=1)], 1, 0,
            lambda *x: None, lambda *x: finished.append(x),
            automation=self.Automation(),
            on_failure_capture=captures.append)
        executor2.stop()
        executor2.run()
        self.assertFalse(finished[-1][0])
        self.assertEqual(captures, [])

    def test_visual_conditions_and_watcher_emit_results(self):
        events = []
        class VisualAutomation(self.Automation):
            def __init__(self):
                super().__init__()
                self.screens = iter([0, 255])
            def screenshot(self, region=None):
                color = next(self.screens) if region else 0
                return Image.new("RGB", (10, 10), (color,) * 3)
        watch = Action(kind="watch_start", region_x=0, region_y=0,
                       region_w=10, region_h=10, watch_max_changes=1,
                       poll_interval=.1, watch_confirmations=1)
        executor = MacroExecutor(
            [watch, Action(kind="wait", seconds=0), Action(kind="watch_end")],
            1, 0, lambda *x: None, lambda *x: None,
            automation=VisualAutomation(), on_diagnostic=events.append)
        executor.run()
        self.assertIn("watch_trigger", [e["event"] for e in events])
        self.assertIn("action_done", [e["event"] for e in events])


if __name__ == "__main__":
    unittest.main()
