"""Window-state wait tests; no real desktop input required."""
from dataclasses import replace
import os
import threading
import unittest
from unittest.mock import patch

from macro_model import Action, parse_document, serialize_document, validate_action
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_window_wait import wait_for_window
from macro_windows import WindowInfo, WindowUnavailable, target_from_window
from macro_workflow import default_node
from macro_qt_workflow import description


def window():
    return WindowInfo(109, "Example Editor", "EditorClass", 500, 40, 60, 600, 400)


def wait_action(**changes):
    params = dict(kind="wait_window", window_wait_title=window().title,
                  window_wait_state="appears", timeout=.3, poll_interval=.1)
    params.update(changes)
    return Action(**params)


class FakeWindowManager:
    def __init__(self, snapshots=None, foreground=0):
        self.snapshots = list(snapshots if snapshots is not None else [[]])
        self.foreground = foreground
        self.probes = 0
        self.activations = []

    def all_windows(self):
        index = min(self.probes, len(self.snapshots) - 1)
        self.probes += 1
        return list(self.snapshots[index])

    def windows(self):
        return self.all_windows()

    def foreground_handle(self):
        return self.foreground

    def activate(self, handle):
        self.activations.append(handle)
        self.foreground = handle


class FastGate:
    def __init__(self, stopped_after=None):
        self.calls = []
        self.stopped_after = stopped_after

    def wait(self, value):
        self.calls.append(value)
        if self.stopped_after is not None and len(self.calls) >= self.stopped_after:
            raise RuntimeError("Stopped")


class FakeInput:
    def __init__(self):
        self.events = []

    def keyDown(self, key): self.events.append(("keyDown", key))
    def keyUp(self, key): self.events.append(("keyUp", key))
    def moveTo(self, x, y, duration=0): self.events.append(("move", x, y))
    def click(self, *a, **kw): self.events.append(("click", kw))


class WindowWaitModelTests(unittest.TestCase):
    def test_new_action_is_editable_and_legacy_json_stays_supported(self):
        action = default_node("wait_window").action
        self.assertEqual(action.window_wait_source, "custom")
        self.assertEqual(action.window_wait_state, "appears")
        self.assertEqual(validate_action(vars(action)), action)
        self.assertIn("Choose window", description(action))
        original = [wait_action(window_wait_class="EditorClass",
                                window_wait_handle=109, window_wait_pid=500),
                    Action(kind="wait", seconds=0)]
        self.assertEqual(parse_document(serialize_document(original, 2, .5))[0],
                         original)
        self.assertEqual(parse_document([{"kind":"wait", "seconds":.2}])[0][0].kind,
                         "wait")

    def test_invalid_fields_and_ranges(self):
        invalid = [
            {"window_wait_state":"visible"},
            {"window_wait_source":"background"},
            {"window_wait_title":42},
            {"window_wait_class":None},
            {"window_wait_pid":-1},
            {"window_wait_handle":True},
            {"timeout":-1},
            {"timeout":float("nan")},
            {"timeout":86401},
            {"poll_interval":.05},
            {"poll_interval":float("inf")},
        ]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_action(vars(wait_action(**fields)))
        with self.assertRaises(ValueError):
            validate_action(vars(wait_action(window_wait_handle=5,
                                              window_wait_pid=2,
                                              window_wait_class=42)))

    def test_preflight_blocks_empty_source_and_unsupported_backend(self):
        manager = FakeWindowManager()
        missing = inspect_workflow([Action(kind="wait_window")],
                                   window_manager=manager)
        self.assertEqual(missing[0].severity, "error")
        self.assertIn("Choose a window", missing[0].message)
        workflow = inspect_workflow(
            [wait_action(window_wait_source="workflow")],
            window_manager=manager)
        self.assertTrue(any("workflow target" in f.message for f in workflow))

    def test_preflight_does_not_require_future_window_to_exist(self):
        manager = FakeWindowManager()
        self.assertFalse(inspect_workflow([wait_action()],window_manager=manager))
        target = target_from_window(window())
        actions = [
            Action(kind="launch", launch_mode="url",
                   launch_target="https://example.org"),
            wait_action(window_wait_source="workflow"),
            Action(kind="click", x=10, y=20),
        ]
        findings = inspect_workflow(
            actions, window_target=target, window_manager=manager)
        self.assertFalse([f for f in findings if f.severity == "error"], findings)
        self.assertTrue([f for f in findings if f.severity == "warning"], findings)
        unsafe = inspect_workflow(
            [actions[-1], *actions[:2]], window_target=target,
            window_manager=manager)
        self.assertTrue([f for f in unsafe if f.severity == "error"], unsafe)

    def test_preflight_respects_disabled_wait_and_run_selected(self):
        manager = FakeWindowManager()
        actions = [Action(kind="wait_window", enabled=False),
                   Action(kind="wait", seconds=0)]
        self.assertEqual(inspect_workflow(actions,window_manager=manager), [])
        only_enabled = [wait_action()]
        self.assertEqual(inspect_workflow(only_enabled, window_manager=manager), [])

    def test_wayland_unsupported_even_without_workflow_binding(self):
        with patch("macro_windows.sys.platform", "linux"), patch.dict(
                os.environ, {"XDG_SESSION_TYPE":"wayland", "DISPLAY":":0"}):
            findings = inspect_workflow([wait_action()])
        self.assertTrue([f for f in findings if f.severity == "error"], findings)
        self.assertIn("Wayland", findings[0].message)


class WindowWaitPollingTests(unittest.TestCase):
    def test_delayed_appearance_and_polling_are_bounded(self):
        backend = FakeWindowManager([[], [], [window()]])
        gate = FastGate()
        wait_for_window(wait_action(), gate, manager=backend)
        self.assertEqual(backend.probes, 3)
        self.assertEqual(gate.calls.count(.1), 2)
        self.assertNotIn("activate", backend.activations)

    def test_foreground_wait_never_activates_app(self):
        backend = FakeWindowManager([[window()]], foreground=777)
        gate = FastGate()
        with self.assertRaises(TimeoutError):
            wait_for_window(wait_action(window_wait_state="active"), gate, manager=backend)
        self.assertEqual(backend.activations, [])
        backend.foreground = window().handle
        wait_for_window(wait_action(window_wait_state="active"), FastGate(),
                        manager=backend)

    def test_hidden_requires_known_minimized_or_unmapped_window(self):
        minimized = replace(window(), minimized=True, hidden=True)
        backend = FakeWindowManager([[window()], [minimized]])
        wait_for_window(wait_action(window_wait_state="hidden"), FastGate(),
                        manager=backend)
        backend = FakeWindowManager([[]])
        with self.assertRaises(TimeoutError):
            wait_for_window(wait_action(window_wait_state="hidden"), FastGate(),
                            manager=backend)
        # A hidden window is not closed, even if no longer on screen.
        backend = FakeWindowManager([[minimized]])
        with self.assertRaises(TimeoutError):
            wait_for_window(wait_action(window_wait_state="closed"), FastGate(),
                            manager=backend)

    def test_closed_wait_succeeds_after_removed_or_immediately(self):
        backend = FakeWindowManager([[window()], [], []])
        wait_for_window(wait_action(window_wait_state="closed"), FastGate(),
                        manager=backend)
        self.assertEqual(backend.probes, 2)
        backend = FakeWindowManager([[]])
        wait_for_window(wait_action(window_wait_state="closed"), FastGate(),
                        manager=backend)
        self.assertEqual(backend.probes, 1)

    def test_no_window_does_not_satisfy_appears_or_hidden(self):
        for state in ("appears", "hidden", "active"):
            with self.subTest(state=state):
                with self.assertRaises(TimeoutError):
                    wait_for_window(wait_action(window_wait_state=state,
                                                timeout=.2), FastGate(),
                                    manager=FakeWindowManager([[]]))

    def test_exact_title_class_duplicate_is_fatal(self):
        other = replace(window(), handle=200, pid=900)
        backend = FakeWindowManager([[window(), other]])
        with self.assertRaisesRegex(WindowUnavailable, "Multiple windows"):
            wait_for_window(wait_action(), FastGate(), manager=backend)
        with self.assertRaisesRegex(WindowUnavailable, "Multiple windows"):
            wait_for_window(wait_action(window_wait_state="closed"),
                            FastGate(), manager=backend)

    def test_picker_identity_survives_rename_and_pid_restart(self):
        saved = wait_action(window_wait_class="EditorClass",
                            window_wait_handle=109, window_wait_pid=500)
        renamed = replace(window(), title="Example Editor - document")
        wait_for_window(saved, FastGate(),
                        manager=FakeWindowManager([[renamed]]))
        reopened = replace(window(), handle=240, pid=901)
        wait_for_window(saved, FastGate(),
                        manager=FakeWindowManager([[reopened]]))
        impostor = replace(window(), title="Other window", pid=999)
        with self.assertRaises(TimeoutError):
            wait_for_window(saved, FastGate(),
                            manager=FakeWindowManager([[impostor]]))

    def test_workflow_binding_matches_target_from_issue_45(self):
        target = target_from_window(window())
        backend = FakeWindowManager([[], [window()]])
        wait_for_window(wait_action(window_wait_source="workflow",
                                    window_wait_title=""),
                        FastGate(), workflow_target=target, manager=backend)

    def test_zero_timeout_only_probes_once(self):
        backend = FakeWindowManager([[]])
        with self.assertRaises(TimeoutError):
            wait_for_window(wait_action(timeout=0), FastGate(), manager=backend)
        self.assertEqual(backend.probes, 1)

    def test_stop_is_immediate_without_input_or_busy_loop(self):
        backend, gate = FakeWindowManager([[]]), FastGate(stopped_after=2)
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            wait_for_window(wait_action(timeout=120), gate, manager=backend)
        self.assertEqual(backend.probes, 1)
        self.assertEqual(len(gate.calls), 2)

    def test_runtime_skips_input_backend_for_wait_only(self):
        finished = []
        runner = MacroExecutor(
            [wait_action()], 1, 0, lambda *args:None,
            lambda *args:finished.append(args),
            window_manager=FakeWindowManager([[], [window()]]))
        with patch.object(runner, "_pag", side_effect=AssertionError(
                "Window wait must not load global desktop input")):
            runner.run()
        self.assertTrue(finished[0][0], finished)

    def test_runtime_skip_timeout_and_continue(self):
        backend = FakeWindowManager([[]])
        result, diagnostics = [], []
        runner = MacroExecutor(
            [wait_action(timeout=0, failure_policy="skip"),
             Action(kind="wait", seconds=0)],
            1, 0, lambda *args:None, lambda *args:result.append(args),
            window_manager=backend, on_diagnostic=diagnostics.append)
        runner.run()
        self.assertTrue(result[0][0], result)
        self.assertTrue(any(e.get("event") == "action_skipped" for e in diagnostics))

    def test_stop_during_worker_poll_does_not_perform_next_action(self):
        backend = FakeWindowManager([[]])
        end, outcome, launched = threading.Event(), [], []
        runner = MacroExecutor(
            [wait_action(timeout=60), Action(kind="launch", launch_mode="url",
                                             launch_target="https://example.org")],
            1, 0, lambda *args:None,
            lambda *args:(outcome.append(args), end.set()),
            window_manager=backend)
        with patch("macro_runtime.launch_target", side_effect=launched.append):
            runner.start()
            # Do not wait a full poll interval; Stop should interrupt.
            runner.stop()
            self.assertTrue(end.wait(2))
        self.assertFalse(outcome[0][0])
        self.assertEqual(launched, [])


if __name__ == "__main__":
    unittest.main()
