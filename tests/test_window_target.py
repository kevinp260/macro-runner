"""Platform-neutral target resolution, preflight, and runtime safety tests."""
import os
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from PIL import Image

from macro_model import Action, parse_document, serialize_document
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_windows import (WindowBinding, WindowInfo, WindowManager,
                           WindowUnavailable, identify_target,
                           target_from_window, validate_target)


class FakeBackend:
    def __init__(self, windows=None, active=None, accepts_activation=True):
        self.items = list(windows or [])
        self.active = active
        self.accepts_activation = accepts_activation
        self.activations = []

    def windows(self):
        return list(self.items)

    def foreground_handle(self):
        return self.active or 0

    def activate(self, handle):
        self.activations.append(handle)
        if self.accepts_activation:
            self.active = handle


class FakeMouse:
    def __init__(self):
        self.calls = []
        self.on_click = None

    def moveTo(self, x, y, duration=0):
        self.calls.append(("move", x, y, duration))

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))
        if self.on_click:
            self.on_click()

    def dragTo(self, x, y, duration=0, button="left"):
        self.calls.append(("drag", x, y, duration, button))

    def scroll(self, value):
        self.calls.append(("scroll", value))

    def press(self, key):
        self.calls.append(("press", key))

    def keyDown(self, key):
        self.calls.append(("down", key))

    def keyUp(self, key):
        self.calls.append(("up", key))

    def write(self, char):
        self.calls.append(("write", char))

    def screenshot(self, region=None):
        self.calls.append(("capture", region))
        return Image.new("RGB", (1, 1), "#00FF00")


def example():
    return WindowInfo(100, "Target Editor", "TargetClass", 250,
                      150, 240, 640, 480)


class TargetIdentityTests(unittest.TestCase):
    def test_spec_strict_and_optional_document_round_trip(self):
        info = example()
        saved = target_from_window(info)
        self.assertEqual(saved["handle"], 100)
        self.assertTrue(saved["activate"])
        self.assertTrue(saved["relative"])
        actions = [Action(kind="click", x=10, y=20)]
        legacy = serialize_document(actions, 2, 0.5)
        self.assertNotIn("window_target", legacy["settings"])
        saved_doc = serialize_document(actions, 2, 0.5, saved)
        parsed, settings = parse_document(saved_doc)
        self.assertEqual(parsed, actions)
        self.assertEqual(settings["window_target"], saved)
        self.assertEqual(parse_document(legacy)[1],
                         {"repeat_count":2,"start_delay":0.5})

    def test_invalid_identity_rejected(self):
        good = target_from_window(example())
        for updates in ({"handle": 0}, {"handle": True}, {"title": ""},
                        {"class_name": 123}, {"pid": -1},
                        {"relative": "yes"}, {"activate": None},
                        {"unknown": 4}):
            with self.subTest(updates=updates):
                with self.assertRaises(ValueError):
                    validate_target({**good, **updates})

    def test_same_instance_title_changed_and_new_pid_fallback(self):
        saved = target_from_window(example())
        changed_title = replace(example(), title="Target Editor (edited)")
        self.assertEqual(identify_target(saved, [changed_title]), changed_title)
        restarted = replace(example(), handle=200, pid=260)
        self.assertEqual(identify_target(saved, [restarted]), restarted)

    def test_wrong_reused_handle_never_selected_and_ambiguity_blocks(self):
        saved = target_from_window(example())
        impostor = replace(example(), pid=900, title="Unrelated window")
        correct = replace(example(), handle=300, pid=260)
        self.assertEqual(identify_target(saved, [impostor, correct]), correct)
        with self.assertRaises(WindowUnavailable):
            identify_target(saved, [replace(correct, handle=310), correct])
        with self.assertRaises(WindowUnavailable):
            identify_target(saved, [impostor])

    def test_client_coordinates_bounds_and_negative_screen_origin(self):
        info = replace(example(), x=-400, y=100)
        binding = WindowBinding(target_from_window(info),
                                WindowManager(FakeBackend([info], active=info.handle)))
        self.assertEqual(binding.point(12, 14, info), (-388, 114))
        self.assertEqual(binding.rect(0, 0, 200, 250, info),
                         (-400, 100, 200, 250))
        with self.assertRaises(WindowUnavailable):
            binding.point(-1, 0, info)
        with self.assertRaises(WindowUnavailable):
            binding.point(640, 0, info)
        with self.assertRaises(WindowUnavailable):
            binding.rect(500, 450, 200, 50, info)

    def test_action_transform_absolute_and_relative(self):
        info = example()
        manager = WindowManager(FakeBackend([info], active=info.handle))
        binding = WindowBinding(target_from_window(info), manager)
        click = binding.transform(Action(kind="click", x=3, y=7), info)
        self.assertEqual((click.x, click.y), (153, 247))
        drag = binding.transform(Action(kind="drag", x=1, y=2,
                                        to_x=15, to_y=20), info)
        self.assertEqual((drag.to_x, drag.to_y), (165, 260))
        pixel = binding.transform(Action(kind="wait_until",
                                         condition_source="pixel", pixel_x=5,
                                         pixel_y=6), info)
        self.assertEqual((pixel.pixel_x, pixel.pixel_y), (155, 246))
        match = binding.transform(Action(kind="click_image", image_path="a.png"),
                                  info)
        self.assertEqual((match.region_x, match.region_y,
                          match.region_w, match.region_h), (150, 240, 640, 480))
        watch = binding.transform(Action(kind="watch_start", region_x=10,
                                         region_y=20, region_w=100,
                                         region_h=200), info)
        self.assertEqual((watch.region_x, watch.region_y), (160, 260))
        absolute = WindowBinding(target_from_window(
            info, relative=False), manager)
        self.assertEqual(absolute.transform(Action(kind="click", x=5, y=6), info),
                         Action(kind="click", x=5, y=6))

    def test_foreground_required_and_failure_to_activate(self):
        info = example()
        inactive = FakeBackend([info], active=900)
        binding = WindowBinding(target_from_window(info, activate=False),
                                WindowManager(inactive))
        with self.assertRaisesRegex(WindowUnavailable, "not foreground"):
            binding.prepare()
        self.assertEqual(inactive.activations, [])
        refused = FakeBackend([info], active=900, accepts_activation=False)
        binding = WindowBinding(target_from_window(info),
                                WindowManager(refused))
        class FastGate:
            def wait(self, seconds): return None
        with self.assertRaisesRegex(WindowUnavailable, "Could not activate"):
            binding.prepare(FastGate())
        self.assertEqual(refused.activations, [100])

    def test_minimized_target_must_restore_before_coordinates_are_used(self):
        old = replace(example(), x=-32000, y=-32000, minimized=True)
        restored = replace(example(), x=500, y=300)
        class Backend(FakeBackend):
            def activate(self, handle):
                super().activate(handle)
                self.items = [restored]
        backend = Backend([old], active=900)
        binding = WindowBinding(target_from_window(old), WindowManager(backend))
        class FastGate:
            def wait(self, seconds): return None
        current = binding.prepare(FastGate())
        self.assertEqual((current.x, current.y), (500, 300))
        self.assertEqual(backend.activations, [100])
        backend = FakeBackend([old], active=900, accepts_activation=False)
        binding = WindowBinding(target_from_window(old), WindowManager(backend))
        with self.assertRaises(WindowUnavailable):
            binding.prepare(FastGate())

    def test_wayland_is_explicitly_unsupported(self):
        with patch("macro_windows.sys.platform", "linux"), patch.dict(
                os.environ, {"XDG_SESSION_TYPE":"wayland","DISPLAY":":0"}):
            with self.assertRaisesRegex(WindowUnavailable, "Wayland"):
                WindowManager()

    def test_preflight_blocks_missing_resize_and_negative_screenshot(self):
        info = example()
        backend = FakeBackend([info], active=100)
        manager = WindowManager(backend)
        saved = target_from_window(info)
        a = [Action(kind="click", x=30, y=30)]
        self.assertEqual(inspect_workflow(
            a, window_target=saved, window_manager=manager, screen_size=(100,100)),
            [])
        backend.items = []
        errors = inspect_workflow(a, window_target=saved, window_manager=manager)
        self.assertEqual(errors[0].severity, "error")
        backend.items = [replace(info, width=20)]
        errors = inspect_workflow(a, window_target=saved, window_manager=manager)
        self.assertEqual(errors[0].severity, "error")
        self.assertEqual(errors[0].index, 0)
        backend.items = [replace(info, x=-200)]
        visual = [Action(kind="click_image", image_path="missing.png")]
        errors = inspect_workflow(visual, window_target=saved, window_manager=manager)
        self.assertTrue(any("negative screen origin" in e.message
                            for e in errors))

    def test_window_activation_does_not_occur_in_preflight(self):
        info = example()
        backend = FakeBackend([info], active=50)
        errors = inspect_workflow(
            [Action(kind="click", x=1, y=1)],
            window_target=target_from_window(info),
            window_manager=WindowManager(backend))
        self.assertFalse(errors)
        self.assertFalse(backend.activations)


class RuntimeTargetTests(unittest.TestCase):
    def run_actions(self, actions, manager, saved):
        mouse = FakeMouse()
        results = []
        runner = MacroExecutor(actions, 1, 0, lambda *args: None,
                               lambda *args: results.append(args),
                               automation=mouse, window_target=saved,
                               window_manager=WindowManager(manager))
        runner.run()
        return results[0], mouse, runner

    def test_foreground_activation_and_moved_target_between_clicks(self):
        info = example()
        backend = FakeBackend([info], active=999)
        saved = target_from_window(info)
        mouse = FakeMouse()
        result = []
        def moved():
            backend.items = [replace(info, x=400, y=500)]
        mouse.on_click = moved
        runner = MacroExecutor([Action(kind="click", x=10, y=20),
                                Action(kind="click", x=15, y=25)], 1, 0,
                               lambda *args:None, lambda *args: result.append(args),
                               automation=mouse, window_target=saved,
                               window_manager=WindowManager(backend))
        runner.run()
        self.assertTrue(result[0][0], result[0])
        self.assertEqual([(c[1], c[2]) for c in mouse.calls if c[0] == "move"],
                         [(160, 260), (415, 525)])
        self.assertEqual(backend.activations, [100])

    def test_drag_and_scroll_target_client(self):
        info = example()
        backend = FakeBackend([info], active=100)
        outcome, mouse, _ = self.run_actions(
            [Action(kind="drag", x=1, y=2, to_x=30, to_y=40),
             Action(kind="scroll", scroll_amount=-3)], backend,
            target_from_window(info))
        self.assertTrue(outcome[0], outcome)
        self.assertIn(("drag", 180, 280, .2, "left"), mouse.calls)
        self.assertIn(("move", 470, 480, 0), mouse.calls)
        self.assertIn(("scroll", -3), mouse.calls)

    def test_pixel_condition_relative_and_no_unintended_capture(self):
        info = example()
        backend = FakeBackend([info], active=100)
        outcome, mouse, _ = self.run_actions(
            [Action(kind="if_start", condition_source="pixel",
                    pixel_x=5, pixel_y=6, pixel_color="#00FF00"),
             Action(kind="key", keys="x"), Action(kind="if_end")],
            backend, target_from_window(info))
        self.assertTrue(outcome[0], outcome)
        self.assertIn(("capture", (155, 246, 1, 1)), mouse.calls)
        self.assertIn(("press", "x"), mouse.calls)

    def test_target_loss_is_fatal_even_when_action_policy_is_skip(self):
        info = example()
        backend = FakeBackend([], active=100)
        outcome, mouse, _ = self.run_actions(
            [Action(kind="click", x=10, y=10, failure_policy="skip"),
             Action(kind="key", keys="x")], backend, target_from_window(info))
        self.assertFalse(outcome[0])
        self.assertEqual(mouse.calls, [])

    def test_focus_loss_blocks_keyboard_without_activation(self):
        info = example()
        backend = FakeBackend([info], active=999)
        result, mouse, _ = self.run_actions(
            [Action(kind="key", keys="secret", key_mode="type")],
            backend, target_from_window(info, activate=False))
        self.assertFalse(result[0])
        self.assertFalse(mouse.calls)

    def test_no_binding_keeps_legacy_absolute_behavior(self):
        mouse, result = FakeMouse(), []
        MacroExecutor([Action(kind="click", x=-100, y=30)], 1, 0,
                      lambda *a: None, lambda *a: result.append(a),
                      automation=mouse).run()
        self.assertTrue(result[0][0])
        self.assertEqual(mouse.calls[0], ("move", -100, 30, 0))


if __name__ == "__main__":
    unittest.main()
