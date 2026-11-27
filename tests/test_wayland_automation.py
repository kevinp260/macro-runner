"""Managed Wayland playback tests; no native portal or desktop input."""
import threading
import unittest
from unittest.mock import Mock

from PIL import Image
from macro_model import Action
from macro_platform import DesktopUnavailable
from macro_playback import PlaybackGate
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_wayland_automation import (WaylandAutomation, key_symbol, text_symbol,
                                      validate_wayland_action)


class FakeSession:
    def __init__(self, app_id, stopped):
        self.stopped = stopped
        self.logical_size = (20, 10)
        self.held = []
        self.broken = False
        self.revoked = False
        self.active = False
        self.events = []
        self.geometry_guard = None
        self.on_motion = None

    def __enter__(self):
        self.active = True
        return self

    def check(self):
        if not self.active or self.broken:
            raise DesktopUnavailable("Session inactive")
        if self.stopped.is_set():
            raise RuntimeError("Stopped")
        if self.revoked:
            raise DesktopUnavailable("Permission revoked")
        if self.geometry_guard:
            self.geometry_guard()

    def move_absolute(self, x, y):
        self.check()
        self.events.append(("move", x, y))
        if self.on_motion:
            self.on_motion()

    def _input(self, kind, code, pressed):
        self.check()
        self.events.append((kind, code, pressed))
        if pressed:
            self.held.append((kind, code))
        else:
            self.held.remove((kind, code))

    def key(self, code, pressed):
        self._input("key", code, pressed)

    def button(self, name, pressed):
        self._input("button", name, pressed)

    def scroll(self, steps):
        self.check()
        self.events.append(("scroll", steps))

    def close(self):
        if self.active:
            for kind, code in reversed(self.held):
                self.events.append((kind, code, False))
            self.held.clear()
            self.active = False
            self.events.append(("session closed",))
        return True


class FakeCapture:
    def __init__(self, session):
        self.session = session
        self.active = False

    def __enter__(self):
        self.active = True
        return self

    def check(self):
        self.session.check()
        if not self.active:
            raise DesktopUnavailable("Capture inactive")

    def screenshot(self, region=None):
        self.check()
        self.session.events.append(("capture",))
        return Image.new("RGB", (region[2], region[3]) if region else (20, 10), "green")

    def close(self):
        if self.active:
            self.active = False
            self.session.events.append(("capture closed",))
        return True


def backend(gate, size=(20, 10), invalidated=None):
    return WaylandAutomation(gate, size, invalidated or threading.Event(),
                             session_factory=FakeSession, capture_factory=FakeCapture)


class AdapterTests(unittest.TestCase):
    def test_key_mapping_and_validation(self):
        self.assertEqual(key_symbol("Control"), 0xffe3)
        self.assertEqual(key_symbol("F24"), 0xffd5)
        self.assertEqual(text_symbol("A"), 65)
        self.assertEqual(text_symbol("\n"), 0xff0d)
        for action in (Action(kind="key", keys="unknown"),
                       Action(kind="key", key_mode="type", keys="é"),
                       Action(kind="key", keys="ctrl+control"),
                       Action(kind="clipboard_paste"), Action(kind="wait_window")):
            with self.subTest(kind=action.kind), self.assertRaises(DesktopUnavailable):
                validate_wayland_action(action)

    def test_frame_before_input_and_cleanup_order(self):
        gate = PlaybackGate()
        adapter = backend(gate)
        with adapter:
            adapter.moveTo(2, 3)
            adapter.click(button="right")
            adapter.scroll(102)
            adapter.hotkey("shift", "a")
            adapter.keyDown("ctrl")
        self.assertEqual(adapter.session.events, [
            ("capture",), ("move", 2, 3), ("move", 2, 3),
            ("button", "right", True), ("button", "right", False),
            ("scroll", -100), ("scroll", -2),
            ("key", 0xffe1, True), ("key", 97, True),
            ("key", 97, False), ("key", 0xffe1, False),
            ("key", 0xffe3, True), ("key", 0xffe3, False),
            ("session closed",), ("capture closed",)])

    def test_geometry_mismatch_prevents_capture_and_input(self):
        adapter = backend(PlaybackGate(), size=(30, 10))
        with self.assertRaisesRegex(DesktopUnavailable, "differs"):
            with adapter:
                self.fail("Incorrect display became active")
        self.assertEqual(adapter.session.events, [("session closed",)])

    def test_display_change_prevents_input(self):
        adapter = backend(PlaybackGate())
        with adapter:
            adapter.invalidated.set()
            with self.assertRaisesRegex(DesktopUnavailable, "configuration"):
                adapter.moveTo(1, 1)
        self.assertNotIn(("move", 1, 1), adapter.session.events)

    def test_timed_move_requires_known_start(self):
        adapter = backend(PlaybackGate())
        with adapter:
            with self.assertRaisesRegex(DesktopUnavailable, "immediate Move"):
                adapter.moveTo(5, 5, duration=.02)
            adapter.moveTo(1, 1)
            adapter.moveTo(5, 5, duration=.04)
        self.assertIn(("move", 3.0, 3.0), adapter.session.events)
        self.assertIn(("move", 5.0, 5.0), adapter.session.events)

    def test_pause_with_held_key_aborts(self):
        gate = PlaybackGate()
        adapter = backend(gate)
        with adapter:
            gate.health_check = adapter.check
            adapter.keyDown("shift")
            gate.pause()
            with self.assertRaisesRegex(DesktopUnavailable, "held input"):
                gate.wait(0)
        self.assertIn(("key", 0xffe1, False), adapter.session.events)

    def test_drag_pause_aborts_and_releases_button(self):
        gate = PlaybackGate()
        adapter = backend(gate)
        with self.assertRaises(DesktopUnavailable):
            with adapter:
                gate.health_check = adapter.check
                adapter.moveTo(1, 1)
                adapter.session.on_motion = gate.pause
                adapter.dragTo(5, 5, duration=.04)
        self.assertIn(("button", "left", False), adapter.session.events)
        self.assertNotIn(("move", 5, 5), adapter.session.events)

    def test_existing_modifier_not_released_by_chord(self):
        adapter = backend(PlaybackGate())
        with adapter:
            adapter.keyDown("shift")
            adapter.hotkey("shift", "a")
            self.assertEqual(adapter.session.held, [("key", 0xffe1)])
            adapter.keyUp("shift")
        self.assertEqual(adapter.session.events.count(("key", 0xffe1, False)), 1)


class IntegrationTests(unittest.TestCase):
    def test_runtime_uses_managed_adapter_and_closes(self):
        outcomes = []
        adapters = []

        def factory(gate):
            adapter = backend(gate)
            adapters.append(adapter)
            return adapter

        actions = [Action(kind="click", x=2, y=3),
                   Action(kind="key_down", keys="shift"),
                   Action(kind="key", keys="a")]
        runner = MacroExecutor(actions, 1, 0, lambda *a: None,
                               lambda *a: outcomes.append(a), wayland_factory=factory)
        runner.run()
        self.assertTrue(outcomes[0][0], outcomes)
        self.assertIn(("key", 0xffe1, False), adapters[0].session.events)
        self.assertEqual(adapters[0].session.events[-2:],
                         [("session closed",), ("capture closed",)])

    def test_revocation_during_wait_is_fatal_even_with_skip(self):
        outcomes = []
        adapters = []

        def factory(gate):
            adapter = backend(gate)
            adapters.append(adapter)
            return adapter

        def progress(*args):
            if args[2] == 1:
                adapters[0].session.revoked = True

        runner = MacroExecutor([Action(kind="key", keys="a"),
                                Action(kind="wait", seconds=1, failure_policy="skip"),
                                Action(kind="key", keys="b")],
                               1, 0, progress, lambda *a: outcomes.append(a),
                               wayland_factory=factory)
        runner.run()
        self.assertFalse(outcomes[0][0])
        self.assertIn("revoked", outcomes[0][1])
        self.assertNotIn(("key", 98, True), adapters[0].session.events)

    def test_unsupported_action_rejected_before_permission(self):
        factory = Mock(side_effect=AssertionError("requested permission"))
        outcomes = []
        runner = MacroExecutor([Action(kind="key", keys="a"),
                                Action(kind="clipboard_paste")],
                               1, 0, lambda *a: None, lambda *a: outcomes.append(a),
                               wayland_factory=factory)
        runner.run()
        self.assertFalse(outcomes[0][0])
        factory.assert_not_called()

    def test_non_desktop_workflow_does_not_request_permission(self):
        outcomes = []
        factory = Mock(side_effect=AssertionError("requested permission"))
        runner = MacroExecutor([Action(kind="wait", seconds=0)], 1, 0,
                               lambda *a: None, lambda *a: outcomes.append(a),
                               wayland_factory=factory)
        runner.run()
        self.assertTrue(outcomes[0][0])
        factory.assert_not_called()

    def test_preflight_trial_vs_default(self):
        settings = dict(platform_name="linux", session_type="wayland")
        actions = [Action(kind="click", x=2, y=3)]
        findings = inspect_workflow(actions, **settings)
        self.assertTrue(any(f.severity == "error" for f in findings))
        findings = inspect_workflow(actions, wayland_ready=True, **settings)
        self.assertFalse(any(f.severity == "error" for f in findings))
        self.assertTrue(any(f.severity == "warning" for f in findings))
        findings = inspect_workflow([Action(kind="clipboard_paste")],
                                    wayland_ready=True, **settings)
        self.assertTrue(any(f.severity == "error" for f in findings))


if __name__ == "__main__":
    unittest.main()
