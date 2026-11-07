"""Breakpoint and debug-delay runtime checks without native desktop input."""
import threading
import time
import unittest

from macro_model import Action, parse_document, serialize_document
from macro_runtime import MacroExecutor
from macro_diagnostics import RunSession


class FakeDesktop:
    def __init__(self):
        self.presses = []
        self.first_press = threading.Event()

    def keyDown(self, key):
        pass

    def keyUp(self, key):
        pass

    def press(self, key):
        self.presses.append(key)
        self.first_press.set()

    def screenshot(self, region=None):
        from PIL import Image
        return Image.new("RGB", (1, 1), (0, 255, 0))


def eventually(predicate, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


def make_runner(actions, **kwargs):
    desktop = FakeDesktop()
    events, outcomes = [], []
    finished = threading.Event()

    def on_finished(*args):
        outcomes.append(args)
        finished.set()

    def on_diagnostic(event):
        events.append(event)

    runner = MacroExecutor(
        actions, 1, 0, lambda *a: None, on_finished,
        automation=desktop, on_diagnostic=on_diagnostic, **kwargs)
    return runner, desktop, events, outcomes, finished


class BreakpointRuntimeTests(unittest.TestCase):
    def test_breakpoint_pauses_before_input_and_resume_once(self):
        runner, desktop, events, outcome, finished = make_runner(
            [Action(kind="key", keys="first"), Action(kind="key", keys="second")],
            breakpoints={0})
        runner.start()
        try:
            self.assertTrue(eventually(lambda: any(
                e["event"] == "breakpoint" for e in events)))
            self.assertEqual(desktop.presses, [])
            self.assertTrue(runner.gate.paused)
            runner.resume()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcome[0][0], outcome)
            self.assertEqual(desktop.presses, ["first", "second"])
            self.assertEqual([e["index"] for e in events
                              if e["event"] == "breakpoint"], [0])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_nested_repeat_breakpoint_hits_every_cycle(self):
        actions = [Action(kind="loop_start", repeats=2),
                   Action(kind="key", keys="inner"), Action(kind="loop_end"),
                   Action(kind="key", keys="after")]
        runner, desktop, events, outcome, finished = make_runner(
            actions, breakpoints={1})
        runner.start()
        try:
            self.assertTrue(eventually(lambda: sum(
                e["event"] == "breakpoint" for e in events) == 1))
            self.assertEqual(desktop.presses, [])
            runner.step()
            self.assertTrue(eventually(lambda: sum(
                e["event"] == "breakpoint" for e in events) == 2))
            self.assertEqual(desktop.presses, ["inner"])
            runner.resume()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcome[0][0])
            self.assertEqual(desktop.presses, ["inner", "inner", "after"])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_nested_if_breakpoint_and_disabled_action_ignored(self):
        actions = [Action(kind="if_start", condition_source="pixel",
                          pixel_color="#00FF00"),
                   Action(kind="key", keys="inside"),
                   Action(kind="if_end"),
                   Action(kind="key", keys="disabled", enabled=False),
                   Action(kind="key", keys="after")]
        runner, desktop, events, outcome, finished = make_runner(
            actions, breakpoints={0, 1, 3})
        self.assertEqual(runner.breakpoints, {1})
        runner.start()
        try:
            self.assertTrue(eventually(lambda: any(
                e["event"] == "breakpoint" for e in events)))
            self.assertEqual(desktop.presses, [])
            runner.resume()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcome[0][0])
            self.assertEqual(desktop.presses, ["inside", "after"])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_run_from_selected_skips_earlier_breakpoint(self):
        actions = [Action(kind="key", keys="before"),
                   Action(kind="key", keys="after")]
        runner, desktop, events, outcomes, finished = make_runner(
            actions, breakpoints={0, 1}, start_index=1)
        runner.start()
        try:
            self.assertTrue(eventually(lambda: any(
                e["event"] == "breakpoint" for e in events)))
            self.assertEqual([e["index"] for e in events
                              if e["event"] == "breakpoint"], [1])
            runner.resume()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcomes[0][0])
            self.assertEqual(desktop.presses, ["after"])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_stop_at_breakpoint_prevents_actions_and_finishes(self):
        runner, desktop, events, outcomes, finished = make_runner(
            [Action(kind="key", keys="never")], breakpoints={0})
        runner.start()
        try:
            self.assertTrue(eventually(lambda: runner.gate.paused))
            runner.stop()
            self.assertTrue(finished.wait(2))
            self.assertEqual(desktop.presses, [])
            self.assertFalse(outcomes[0][0])
            self.assertEqual(outcomes[0][1], "Stopped.")
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_step_mode_and_breakpoint_do_not_swallow_step(self):
        runner, desktop, events, outcomes, finished = make_runner(
            [Action(kind="key", keys="one"), Action(kind="key", keys="two")],
            breakpoints={0, 1}, step_mode=True)
        runner.start()
        try:
            self.assertTrue(eventually(lambda: sum(
                e["event"] == "breakpoint" for e in events) == 1))
            runner.step()
            self.assertTrue(eventually(lambda: sum(
                e["event"] == "breakpoint" for e in events) == 2))
            self.assertEqual(desktop.presses, ["one"])
            runner.step()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcomes[0][0])
            self.assertEqual(desktop.presses, ["one", "two"])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_slow_gap_is_cancellable_and_does_not_change_action_json(self):
        actions = [Action(kind="key", keys="first"),
                   Action(kind="key", keys="second")]
        before = serialize_document(actions, 1, 0)
        runner, desktop, events, outcomes, finished = make_runner(
            actions, debug_gap=1.0)
        runner.start()
        try:
            self.assertTrue(desktop.first_press.wait(2))
            runner.stop()
            self.assertTrue(finished.wait(2))
            self.assertFalse(outcomes[0][0])
            self.assertEqual(desktop.presses, ["first"])
            self.assertEqual(serialize_document(actions, 1, 0), before)
            loaded, _ = parse_document(before)
            self.assertEqual(loaded, actions)
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_slow_gap_pauses_and_resumes(self):
        runner, desktop, _, outcomes, finished = make_runner(
            [Action(kind="key", keys="first"), Action(kind="key", keys="second")],
            debug_gap=.3)
        runner.start()
        try:
            self.assertTrue(desktop.first_press.wait(2))
            runner.pause()
            time.sleep(.35)
            self.assertEqual(desktop.presses, ["first"])
            runner.resume()
            self.assertTrue(finished.wait(2))
            self.assertTrue(outcomes[0][0])
            self.assertEqual(desktop.presses, ["first", "second"])
        finally:
            runner.stop()
            runner.thread.join(2)

    def test_invalid_debug_parameters_rejected(self):
        for gap in (-1, 5.1, float("inf"), float("nan"), True):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                make_runner([Action(kind="key")], debug_gap=gap)
        for indexes in ({-1}, {10}, {True}):
            with self.subTest(indexes=indexes), self.assertRaises(ValueError):
                make_runner([Action(kind="key")], breakpoints=indexes)

    def test_breakpoint_diagnostics_are_redacted(self):
        actions = [Action(kind="key", name="PRIVATE NAME", keys="PRIVATE TEXT")]
        session = RunSession(actions)
        session.add({"event": "breakpoint", "index": 0, "cycle": 1,
                     "keys": "PRIVATE TEXT", "name": "PRIVATE NAME"})
        record = session.finish("stopped")
        self.assertEqual(record["events"][0]["event"], "breakpoint")
        self.assertEqual(record["events"][0]["index"], 0)
        self.assertNotIn("PRIVATE", str(record))


if __name__ == "__main__":
    unittest.main()
