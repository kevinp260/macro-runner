"""Regression tests for finite, cancellation-aware per-action failure policies."""
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from macro_model import Action, parse_document, serialize_document, validate_action
from macro_runtime import MacroExecutor
from macro_vision import ConditionTimeout
from macro_diagnostics import RunSession
from macro_qt_history import describe_run
from macro_workflow import from_actions, to_actions


class FakeDesktop:
    def __init__(self, pixels=None, fail_press=None, fail_click=None):
        self.pixels = iter(pixels if pixels is not None else [(0, 0, 0)])
        self.fail_press = fail_press
        self.fail_click = fail_click
        self.screenshots = 0
        self.clicks = []
        self.presses = []

    def screenshot(self, region=None):
        self.screenshots += 1
        color = next(self.pixels, (0, 0, 0))
        return Image.new("RGB", (1, 1), color)

    def press(self, key):
        self.presses.append(key)
        if self.fail_press is not None:
            raise self.fail_press

    def click(self, *args, **kwargs):
        self.clicks.append((args, kwargs))
        if self.fail_click is not None:
            raise self.fail_click

    def moveTo(self, *args, **kwargs):
        pass

    def keyDown(self, *args):
        pass

    def keyUp(self, *args):
        pass


def wait_until(**params):
    return Action(kind="wait_until", condition_source="pixel",
                  pixel_color="#00FF00", pixel_x=0, pixel_y=0,
                  poll_interval=.1, timeout=0.0, **params)


def execute(actions, desktop=None, **kwargs):
    outcomes, events = [], []
    target = desktop or FakeDesktop()
    runner = MacroExecutor(actions, 1, 0, lambda *a: None,
                           lambda *a: outcomes.append(a), automation=target,
                           on_diagnostic=events.append, **kwargs)
    runner.run()
    return runner, target, outcomes, events


class FailurePolicyModelTests(unittest.TestCase):
    def test_default_is_stop_and_json_v2_roundtrip(self):
        old = {"version": 2, "settings": {"repeat_count": 1, "start_delay": 0},
               "actions": [{"kind": "key", "keys": "enter"}]}
        loaded, settings = parse_document(old)
        self.assertEqual(loaded[0].failure_policy, "stop")
        self.assertEqual(loaded[0].retry_count, 2)
        self.assertEqual(loaded[0].retry_delay, 1.0)
        self.assertEqual(settings["repeat_count"], 1)
        configured = wait_until(failure_policy="retry", retry_count=3,
                                retry_delay=.15)
        actions = [Action(kind="loop_start", repeats=2), configured,
                   Action(kind="loop_end")]
        serialized = serialize_document(actions, 1, 0)
        self.assertEqual(serialized["version"], 2)
        self.assertEqual(parse_document(serialized)[0], actions)
        self.assertEqual(to_actions(from_actions(actions)), actions)

    def test_invalid_policies_and_unbounded_retries_are_rejected(self):
        for a in (
            Action(kind="wait", failure_policy="unknown"),
            Action(kind="wait", failure_policy="retry"),
            Action(kind="click", x=1, y=2, failure_policy="retry"),
            Action(kind="key", keys="a", failure_policy="retry"),
            Action(kind="wait_until", condition_source="pixel",
                   failure_policy="retry", retry_count=0),
            Action(kind="wait_until", condition_source="pixel",
                   failure_policy="retry", retry_count=11),
            Action(kind="wait", retry_count=True),
            Action(kind="wait", retry_delay=-.1),
            Action(kind="wait", retry_delay=61),
            Action(kind="wait", retry_delay=float("inf")),
            Action(kind="if_start", condition_source="pixel", failure_policy="skip"),
            Action(kind="watch_end", failure_policy="skip"),
        ):
            with self.subTest(a=a):
                with self.assertRaises(ValueError):
                    validate_action(vars(a))

    def test_skip_on_leaf_is_valid_and_control_cannot_skip(self):
        self.assertEqual(validate_action(vars(Action(
            kind="key", keys="foo", failure_policy="skip"))).failure_policy, "skip")


class FailurePolicyExecutionTests(unittest.TestCase):
    def test_retry_succeeds_after_timeout_then_normal_action(self):
        a = wait_until(failure_policy="retry", retry_count=2, retry_delay=0)
        desktop = FakeDesktop(pixels=[(0, 0, 0), (0, 255, 0)])
        _, desktop, outcomes, events = execute(
            [a, Action(kind="key", keys="after")], desktop)
        self.assertTrue(outcomes[0][0], outcomes)
        self.assertEqual(desktop.screenshots, 2)
        self.assertEqual(desktop.presses, ["after"])
        retries = [e for e in events if e["event"] == "action_retry"]
        self.assertEqual(len(retries), 1)
        self.assertEqual((retries[0]["attempt"], retries[0]["max_attempts"]), (2, 3))
        self.assertEqual(retries[0]["index"], 0)
        self.assertEqual([e["event"] for e in events].count("action_done"), 2)

    def test_retries_exhausted_and_stop_default(self):
        action = wait_until(failure_policy="retry", retry_count=2, retry_delay=0)
        _, desktop, outcomes, events = execute([action], FakeDesktop())
        self.assertFalse(outcomes[0][0])
        self.assertIn("timed out", outcomes[0][1])
        self.assertEqual(desktop.screenshots, 3)
        self.assertEqual([e["event"] for e in events].count("action_retry"), 2)
        self.assertEqual([e["event"] for e in events].count("action_error"), 1)
        _, old, outcomes, events = execute([wait_until()], FakeDesktop())
        self.assertFalse(outcomes[0][0])
        self.assertEqual(old.screenshots, 1)
        self.assertFalse(any(e["event"] == "action_retry" for e in events))

    def test_skip_failure_inside_nested_repeat_and_continues(self):
        actions = [
            Action(kind="loop_start", repeats=2),
            wait_until(failure_policy="skip"),
            Action(kind="key", keys="inner"),
            Action(kind="loop_end"),
            Action(kind="key", keys="last"),
        ]
        _, desktop, outcomes, events = execute(actions)
        self.assertTrue(outcomes[0][0], outcomes)
        self.assertEqual(desktop.presses, ["inner", "inner", "last"])
        skipped = [e for e in events if e["event"] == "action_skipped"]
        self.assertEqual(len(skipped), 2)
        self.assertTrue(all(e["index"] == 1 for e in skipped))
        session = RunSession(actions)
        for e in events:
            session.add(e)
        record = session.finish("completed")
        self.assertEqual(record["skipped_actions"], 2)
        self.assertEqual(record["completed_actions"], 3)
        self.assertIn("skipped after failure: 2", describe_run(record))
        self.assertIn("action skipped", describe_run(record))
        self.assertNotIn("condition timed out", describe_run(record))

    def test_skip_a_partial_input_error_does_not_replay_it(self):
        desktop = FakeDesktop(fail_press=OSError("sensitive data"))
        actions = [Action(kind="key", keys="first", failure_policy="skip"),
                   Action(kind="wait", seconds=0)]
        _, target, outcomes, events = execute(actions, desktop)
        self.assertTrue(outcomes[0][0])
        self.assertEqual(target.presses, ["first"])
        self.assertEqual([e["event"] for e in events].count("action_skipped"), 1)

    def test_click_image_retries_only_poll_not_the_click_itself(self):
        image_action = Action(kind="click_image", image_path="fake.png", timeout=0,
                              failure_policy="retry", retry_count=2, retry_delay=0)
        desktop = FakeDesktop()
        tries = []
        def probe(*args, **kwargs):
            tries.append(1)
            if len(tries) == 1:
                raise ConditionTimeout("No match yet")
            return (20, 30, .9)
        with patch("macro_runtime.poll_until", side_effect=probe):
            _, target, outcomes, events = execute([image_action], desktop)
        self.assertTrue(outcomes[0][0])
        self.assertEqual(len(tries), 2)
        self.assertEqual(len(target.clicks), 1)
        self.assertEqual([e["event"] for e in events].count("action_retry"), 1)

        target = FakeDesktop(fail_click=TimeoutError("input failed after click"))
        tries.clear()
        with patch("macro_runtime.poll_until", side_effect=lambda *a: (
                tries.append(1), (20, 30, .9))[1]):
            _, _, outcomes, events = execute([image_action], target)
        self.assertFalse(outcomes[0][0])
        self.assertEqual(len(tries), 1)  # The click must NEVER be duplicated.
        self.assertEqual(len(target.clicks), 1)
        self.assertFalse(any(e["event"] == "action_retry" for e in events))

    def test_backend_timeout_is_not_treated_as_retryable_condition_timeout(self):
        a = wait_until(failure_policy="retry", retry_count=3, retry_delay=0)
        class BrokenDesktop(FakeDesktop):
            def screenshot(self, region=None):
                self.screenshots += 1
                raise TimeoutError("backend unavailable")
        _, target, outcomes, events = execute([a], BrokenDesktop())
        self.assertFalse(outcomes[0][0])
        self.assertEqual(target.screenshots, 1)
        self.assertFalse(any(e["event"] == "action_retry" for e in events))

    def test_failsafe_cannot_be_suppressed_by_skip(self):
        class FailSafeException(Exception):
            pass
        desktop = FakeDesktop(fail_press=FailSafeException("corner"))
        actions = [Action(kind="key", keys="first", failure_policy="skip"),
                   Action(kind="wait", seconds=0)]
        _, _, outcomes, events = execute(actions, desktop)
        self.assertFalse(outcomes[0][0])
        self.assertFalse(any(e["event"] == "action_skipped" for e in events))

    def test_stop_interrupts_retry_delay_without_second_probe(self):
        started = threading.Event()
        outcomes, events = [], []
        desktop = FakeDesktop()
        def log(evt):
            events.append(evt)
            if evt["event"] == "action_retry":
                started.set()
        a = wait_until(failure_policy="retry", retry_count=10, retry_delay=10)
        runner = MacroExecutor([a], 1, 0, lambda *a: None,
                               lambda *a: outcomes.append(a),
                               automation=desktop, on_diagnostic=log)
        runner.start()
        self.assertTrue(started.wait(2))
        runner.stop()
        runner.thread.join(2)
        self.assertFalse(runner.thread.is_alive())
        self.assertFalse(outcomes[0][0])
        self.assertEqual(outcomes[0][1], "Stopped.")
        self.assertEqual(desktop.screenshots, 1)
        self.assertFalse(any(e["event"] == "action_skipped" for e in events))

    def test_pause_and_step_allow_one_complete_retrying_action(self):
        ready = threading.Event()
        done = threading.Event()
        desktop = FakeDesktop(pixels=[(0, 0, 0), (0, 255, 0)])
        a = wait_until(failure_policy="retry", retry_count=1, retry_delay=.01)
        runner = MacroExecutor([a, Action(kind="key", keys="after")],
                               1, 0, lambda *a: None, lambda *a: done.set(),
                               automation=desktop, step_mode=True)
        runner.start()
        self.assertFalse(done.wait(.05))
        runner.step()
        for _ in range(100):
            if desktop.screenshots == 2:
                ready.set()
                break
            done.wait(.01)
        self.assertTrue(ready.is_set())
        self.assertEqual(desktop.presses, [])
        runner.step()
        self.assertTrue(done.wait(2))
        self.assertEqual(desktop.presses, ["after"])


if __name__ == "__main__":
    unittest.main()
