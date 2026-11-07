"""Stateful screen-region watch regression tests."""
import threading
import unittest

from PIL import Image

from macro_model import Action, parse_document, serialize_document, validate_action
from macro_flow import iter_flow_steps, validate_flow
from macro_runtime import MacroExecutor
from macro_vision import changed_pixel_percent, watch_region_change
from macro_workflow import default_node, to_actions, from_actions


def watcher(max_changes=2, confirmations=1):
    return Action(kind="watch_start", region_x=4, region_y=6,
                  region_w=10, region_h=10, poll_interval=0.1,
                  watch_change_percent=5, watch_pixel_tolerance=10,
                  watch_confirmations=confirmations,
                  watch_max_changes=max_changes)


class FakeGate:
    def __init__(self):
        self.waits = []
    def wait(self, seconds):
        self.waits.append(seconds)


class WatchTests(unittest.TestCase):
    def test_changed_pixels_and_tolerance(self):
        baseline = Image.new("RGB", (10, 10), "black")
        changed = baseline.copy()
        for x in range(3):
            for y in range(3):
                changed.putpixel((x, y), (255, 0, 0))
        self.assertEqual(changed_pixel_percent(baseline, changed, 10), 9)
        self.assertEqual(changed_pixel_percent(baseline, baseline, 10), 0)
        with self.assertRaises(ValueError):
            changed_pixel_percent(baseline, Image.new("RGB", (9, 10)), 10)

    def test_stable_change_confirmation_and_region(self):
        base = Image.new("RGB", (10, 10), "black")
        changed = Image.new("RGB", (10, 10), "white")
        frames = iter([base, changed, base, changed, changed])
        regions = []
        def screenshot(region=None):
            regions.append(region)
            return next(frames)
        gate = FakeGate()
        result = watch_region_change(watcher(confirmations=2), screenshot, gate)
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(regions, [(4, 6, 10, 10)] * 5)
        self.assertEqual(gate.waits, [0, .1, .1, .1, .1])

    def test_flow_rebaseline_after_body_and_bounded_watch(self):
        actions = [watcher(2), Action(kind="key", keys="body"),
                   Action(kind="watch_end"), Action(kind="key", keys="after")]
        checks = []
        result = [a.keys for _, a in iter_flow_steps(
            actions, lambda a: False, lambda: False,
            watch=lambda a, baseline=None: checks.append(a.kind))]
        self.assertEqual(result, ["body", "body", "after"])
        self.assertEqual(checks, ["watch_start", "watch_start"])

    def test_change_during_child_actions_uses_last_accepted_state(self):
        """A -> B triggers; a change back to A inside the body must trigger."""
        class Screen:
            def __init__(self):
                self.color = 0
                self.captures = 0

            def screenshot(self, region=None):
                self.captures += 1
                self.asserted_region = region
                if self.captures == 2:
                    self.color = 255  # First externally observed change.
                if self.captures > 3:
                    raise AssertionError("Lost the second change; kept polling")
                return Image.new("RGB", (10, 10), (self.color,) * 3)

        screen = Screen()
        action = watcher(max_changes=2)
        actions = [action, Action(kind="key", keys="body"), Action(kind="watch_end")]
        baselines = []
        triggered = []

        def capture_change(current_action, baseline=None):
            baselines.append(None if baseline is None else baseline.getpixel((0, 0)))
            return watch_region_change(current_action, screen.screenshot,
                                       FakeGate(), baseline=baseline)

        for _, step in iter_flow_steps(actions, lambda a: False, lambda: False,
                                       watch=capture_change):
            triggered.append(step.keys)
            screen.color = 0  # Second change occurs DURING the nested action.

        self.assertEqual(triggered, ["body", "body"])
        self.assertEqual(baselines, [None, (255, 255, 255)])
        self.assertEqual(screen.captures, 3)
        self.assertEqual(screen.asserted_region, (4, 6, 10, 10))

    def test_unchanged_frames_do_not_retrigger_last_accepted_state(self):
        # A -> B triggers once. Two more identical B frames must be ignored;
        # only B -> A triggers again.
        frames = iter([0, 255, 255, 255, 0])
        seen = []

        def screenshot(region=None):
            value = next(frames)
            seen.append(value)
            return Image.new("RGB", (10, 10), (value,) * 3)

        action = watcher()
        first = watch_region_change(action, screenshot, FakeGate())
        second = watch_region_change(action, screenshot, FakeGate(), baseline=first)
        self.assertEqual(first.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(second.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(seen, [0, 255, 255, 255, 0])

    def test_unlimited_watch_stops(self):
        actions = [watcher(0), Action(kind="wait", seconds=0),
                   Action(kind="watch_end")]
        calls = []
        def check(action, baseline=None):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError("Stopped")
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            list(iter_flow_steps(actions, lambda a: False, lambda: False,
                                 watch=check))
        self.assertEqual(len(calls), 3)

    def test_model_validation_and_roundtrip(self):
        actions = [watcher(2), Action(kind="click", x=3, y=5),
                   Action(kind="watch_end")]
        self.assertEqual(parse_document(serialize_document(actions, 1, 0))[0], actions)
        self.assertEqual(to_actions(from_actions(actions)), actions)
        self.assertEqual([a.kind for a in to_actions([default_node("watch_start")])],
                         ["watch_start", "wait", "watch_end"])
        for changes in (-1, 1.5):
            with self.subTest(changes=changes):
                a = watcher()
                a.watch_max_changes = changes
                with self.assertRaises(ValueError):
                    validate_action(vars(a))
        for bad in (0, -1):
            a = watcher()
            a.region_w = bad
            with self.assertRaises(ValueError):
                validate_action(vars(a))
        with self.assertRaises(ValueError):
            validate_flow([watcher(), Action(kind="watch_end")])

    def test_runtime_triggers_twice_then_finishes(self):
        class Fake:
            def __init__(self):
                self.calls = []
                self.frames = iter([0, 255, 0, 255])
            def screenshot(self, region=None):
                return Image.new("RGB", (10, 10), next(self.frames))
            def keyDown(self, key): pass
            def keyUp(self, key): pass
            def press(self, key): self.calls.append(key)
        fake = Fake()
        finished = []
        action = watcher(2)
        action.poll_interval = 0.1
        runner = MacroExecutor(
            [action, Action(kind="key", keys="a"), Action(kind="watch_end"),
             Action(kind="key", keys="b")], 1, 0, lambda *a: None,
            lambda *a: finished.append(a), automation=fake)
        runner.run()
        self.assertEqual(fake.calls, ["a", "a", "b"])
        self.assertTrue(finished[0][0], finished)


if __name__ == "__main__":
    unittest.main()
