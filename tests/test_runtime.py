import threading
import unittest

from macro_model import Action
from macro_runtime import MacroExecutor


class FakeAutomation:
    def __init__(self):
        self.calls = []
    def keyDown(self, key): self.calls.append(("down", key))
    def keyUp(self, key): self.calls.append(("up", key))
    def press(self, key): self.calls.append(("press", key))
    def moveTo(self, x, y, duration=0): self.calls.append(("move", x, y))
    def click(self, *args, **kwargs): self.calls.append(("click", args, kwargs))
    def screenshot(self, region=None):
        from PIL import Image
        return Image.new("RGB", (1, 1), "#00FF00")


class RuntimeTests(unittest.TestCase):
    def test_keyboard_hold_cleanup_and_progress(self):
        fake = FakeAutomation()
        events = []
        completions = []
        executor = MacroExecutor([
            Action(kind="key_down", keys="shift"),
            Action(kind="key", keys="a"),
        ], 1, 0, lambda *args: events.append(args),
            lambda *args: completions.append(args), automation=fake)
        executor.run()
        self.assertTrue(completions[0][0])
        self.assertEqual(fake.calls, [
            ("down", "shift"), ("press", "a"), ("up", "shift")
        ])
        self.assertEqual([e[2] for e in events], [0, 1])

    def test_abort_still_releases_keys(self):
        fake = FakeAutomation()
        result = []
        executor = MacroExecutor([
            Action(kind="key_down", keys="ctrl"),
            Action(kind="key_up", keys="shift"),
        ], 1, 0, lambda *a: None, lambda *a: result.append(a), automation=fake)
        executor.run()
        self.assertFalse(result[0][0])
        self.assertIn(("up", "ctrl"), fake.calls)

    def test_visual_condition_and_fixed_repeat(self):
        fake = FakeAutomation()
        result = []
        actions = [Action(kind="if_start", condition_source="pixel", pixel_color="#00FF00"),
                   Action(kind="key", keys="x"), Action(kind="if_end")]
        runner = MacroExecutor(actions, 1, 0, lambda *a: None,
                               lambda *a: result.append(a), automation=fake)
        runner.run()
        self.assertTrue(result[0][0])
        self.assertIn(("press", "x"), fake.calls)

    def test_step_around_conditional_markers(self):
        fake = FakeAutomation()
        completed = threading.Event()
        outcomes = []
        actions = [
            Action(kind="if_start", condition_source="pixel", pixel_color="#00FF00"),
            Action(kind="key", keys="inside"),
            Action(kind="if_end"),
            Action(kind="key", keys="after"),
        ]
        runner = MacroExecutor(actions, 1, 0, lambda *args: None,
                               lambda *args: (outcomes.append(args), completed.set()),
                               step_mode=True, automation=fake)
        runner.start()
        self.assertFalse(completed.wait(.05))
        runner.step()
        for _ in range(50):
            if ("press", "inside") in fake.calls:
                break
            completed.wait(.01)
        self.assertIn(("press", "inside"), fake.calls)
        self.assertNotIn(("press", "after"), fake.calls)
        runner.step()
        self.assertTrue(completed.wait(2))
        self.assertTrue(outcomes[0][0])
        self.assertIn(("press", "after"), fake.calls)

    def test_step_repeat_until_condition(self):
        fake = FakeAutomation()
        completed = threading.Event()
        outcomes = []
        actions = [
            Action(kind="until_start", repeats=3, condition_source="pixel",
                   pixel_color="#00FF00"),
            Action(kind="key", keys="body"),
            Action(kind="until_end"),
        ]
        runner = MacroExecutor(actions, 1, 0, lambda *args: None,
                               lambda *args: (outcomes.append(args), completed.set()),
                               step_mode=True, automation=fake)
        runner.start()
        self.assertFalse(completed.wait(.05))
        runner.step()
        self.assertTrue(completed.wait(2))
        self.assertTrue(outcomes[0][0])
        self.assertEqual(fake.calls.count(("press", "body")), 1)

    def test_pause_step_and_stop(self):
        fake = FakeAutomation()
        complete = threading.Event()
        runner = MacroExecutor([Action(kind="key", keys="a"),
                                Action(kind="key", keys="b")],
                               1, 0, lambda *a: None,
                               lambda *a: complete.set(), step_mode=True, automation=fake)
        runner.start()
        self.assertFalse(complete.wait(.05))
        runner.step()
        # Wait until the first key has been replayed.
        for _ in range(30):
            if ("press", "a") in fake.calls: break
            complete.wait(.01)
        self.assertIn(("press", "a"), fake.calls)
        self.assertNotIn(("press", "b"), fake.calls)
        runner.stop()
        self.assertTrue(complete.wait(1))
