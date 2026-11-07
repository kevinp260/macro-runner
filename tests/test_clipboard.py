"""Clipboard action validation, privacy and cancellable playback tests."""
import threading
import unittest
from unittest.mock import patch

from macro_clipboard import (ClipboardState, ClipboardUnavailable,
                             paste_clipboard)
from macro_model import Action, parse_document, serialize_document, validate_action
from macro_runtime import MacroExecutor
from macro_qt_workflow import description
from macro_workflow import default_node


class FakeClipboard:
    def __init__(self, state=None):
        self.state = state or ClipboardState("empty")
        self.events = []
        self.fail_read = False
        self.fail_write = False

    def read(self, gate=None, *, cleanup=False):
        self.events.append(("read", cleanup))
        if self.fail_read:
            raise ClipboardUnavailable("unavailable")
        return self.state

    def set_text(self, text, gate=None, *, cleanup=False):
        self.events.append(("set", text, cleanup))
        if self.fail_write:
            raise ClipboardUnavailable("unavailable")
        self.state = ClipboardState("text", text)

    def clear(self, gate=None, *, cleanup=False):
        self.events.append(("clear", cleanup))
        self.state = ClipboardState("empty")


class FakeDesktop:
    def __init__(self, on_paste=None):
        self.events = []
        self.on_paste = on_paste

    def hotkey(self, *keys):
        self.events.append(("hotkey", keys))
        if self.on_paste:
            self.on_paste()

    def press(self, key): self.events.append(("press", key))
    def keyDown(self, key): self.events.append(("down", key))
    def keyUp(self, key): self.events.append(("up", key))


class Gate:
    def __init__(self):
        self.waits = []
        self.stopped = False

    def wait(self, seconds):
        self.waits.append(seconds)
        if self.stopped:
            raise RuntimeError("Stopped")


class ClipboardActionTests(unittest.TestCase):
    def test_palette_defaults_schema_and_old_macros(self):
        self.assertEqual(default_node("clipboard_set").action.clipboard_text, "")
        self.assertIsNone(default_node("clipboard_paste").action.clipboard_text)
        for kind in ("clipboard_set", "clipboard_paste"):
            self.assertEqual(validate_action(vars(default_node(kind).action)).kind, kind)
        old = serialize_document([Action(kind="key", keys="a")], 1, 3)
        self.assertEqual(parse_document(old)[0][0].kind, "key")
        actions = [Action(kind="clipboard_set", clipboard_text="😀 你好 ñ"),
                   Action(kind="clipboard_paste", clipboard_text="🔒",
                          clipboard_restore=False)]
        self.assertEqual(parse_document(serialize_document(actions, 1, 0))[0], actions)
        self.assertNotIn("😀", description(actions[0]))
        self.assertNotIn("🔒", description(actions[1]))

    def test_invalid_clipboard_fields_are_rejected(self):
        invalid = [
            dict(kind="clipboard_set"),
            dict(kind="clipboard_set", clipboard_text=10),
            dict(kind="clipboard_paste", clipboard_text=123),
            dict(kind="clipboard_paste", clipboard_restore="yes"),
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_action(item)

    def test_set_clipboard_including_empty_does_not_inject_keystrokes(self):
        fake, keyboard = FakeClipboard(), FakeDesktop()
        results = []
        run = MacroExecutor([
            Action(kind="clipboard_set", clipboard_text="こんにちは 😀"),
            Action(kind="clipboard_set", clipboard_text=""),
        ], 1, 0, lambda *a: None, lambda *a: results.append(a),
            automation=keyboard, clipboard=fake)
        run.run()
        self.assertTrue(results[0][0], results)
        self.assertEqual(fake.state.text, "")
        self.assertEqual(fake.events[0], ("set", "こんにちは 😀", False))
        self.assertEqual(keyboard.events, [])

    def test_paste_existing_unicode_and_empty_behavior(self):
        fake = FakeClipboard(ClipboardState("text", "مرحبا π 😄"))
        keyboard = FakeDesktop()
        paste_clipboard(fake, keyboard, Gate())
        self.assertEqual(keyboard.events, [("hotkey", ("ctrl", "v"))])
        self.assertEqual(fake.state.text, "مرحبا π 😄")
        for state in (ClipboardState("empty"), ClipboardState("text", ""),
                      ClipboardState("other")):
            with self.subTest(state=state), self.assertRaises(ClipboardUnavailable):
                paste_clipboard(FakeClipboard(state), keyboard, Gate())
        self.assertEqual(len(keyboard.events), 1)

    def test_temp_unicode_restores_previous_text_or_empty(self):
        for previous in (ClipboardState("text", "prior 😀"), ClipboardState("empty")):
            with self.subTest(previous=previous):
                clipboard, desk = FakeClipboard(previous), FakeDesktop()
                paste_clipboard(clipboard, desk, Gate(), text="Живей 🌿",
                                restore=True)
                self.assertEqual(clipboard.state, previous)
                self.assertEqual(desk.events, [("hotkey", ("ctrl", "v"))])
                self.assertTrue(any(e[0] == "read" and e[1]
                                    for e in clipboard.events))

    def test_other_app_clipboard_change_is_not_overwritten(self):
        fake = FakeClipboard(ClipboardState("text", "old"))
        desk = FakeDesktop(lambda: setattr(
            fake, "state", ClipboardState("text", "external update")))
        paste_clipboard(fake, desk, Gate(), text="paste this", restore=True)
        self.assertEqual(fake.state.text, "external update")

    def test_nontext_backup_refused_and_no_clipboard_modified(self):
        fake = FakeClipboard(ClipboardState("other"))
        desk = FakeDesktop()
        with self.assertRaises(ClipboardUnavailable):
            paste_clipboard(fake, desk, Gate(), text="hello", restore=True)
        self.assertEqual(fake.state.kind, "other")
        self.assertEqual(desk.events, [])
        paste_clipboard(fake, desk, Gate(), text="hello", restore=False)
        self.assertEqual(fake.state.text, "hello")

    def test_stop_and_focus_failure_restore_without_paste(self):
        fake = FakeClipboard(ClipboardState("text", "previous"))
        gate = Gate()
        gate.stopped = True
        desk = FakeDesktop()
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            paste_clipboard(fake, desk, gate, text="temporary")
        self.assertEqual(fake.state.text, "previous")
        self.assertEqual(desk.events, [])
        with self.assertRaisesRegex(RuntimeError, "focus"):
            paste_clipboard(fake, desk, Gate(), text="temporary",
                            prepare_focus=lambda: (_ for _ in ()).throw(
                                RuntimeError("focus lost")))
        self.assertEqual(fake.state.text, "previous")

    def test_stop_after_shortcut_still_restores(self):
        fake = FakeClipboard(ClipboardState("text", "original"))
        gate = Gate()
        desk = FakeDesktop(lambda: setattr(gate, "stopped", True))
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            paste_clipboard(fake, desk, gate, text="temporary", restore=True)
        self.assertEqual(fake.state.text, "original")
        self.assertEqual(desk.events, [("hotkey", ("ctrl", "v"))])

    def test_partial_write_failure_still_restores_previous_text(self):
        class PartiallyWritten(FakeClipboard):
            def set_text(self, text, gate=None, *, cleanup=False):
                super().set_text(text, gate=gate, cleanup=cleanup)
                if text == "temporary":
                    raise ClipboardUnavailable("write rejected after change")

        fake = PartiallyWritten(ClipboardState("text", "previous"))
        desk = FakeDesktop()
        with self.assertRaises(ClipboardUnavailable):
            paste_clipboard(fake, desk, Gate(), text="temporary", restore=True)
        self.assertEqual(fake.state.text, "previous")
        self.assertEqual(desk.events, [])

    def test_cleanup_failure_does_not_hide_target_focus_error(self):
        class FailingRestore(FakeClipboard):
            def read(self, gate=None, *, cleanup=False):
                if cleanup:
                    raise ClipboardUnavailable("read failed")
                return super().read(gate=gate, cleanup=cleanup)

        fake = FailingRestore(ClipboardState("text", "previous"))
        with self.assertRaisesRegex(RuntimeError, "focus lost"):
            paste_clipboard(
                fake, FakeDesktop(), Gate(), text="temporary",
                prepare_focus=lambda: (_ for _ in ()).throw(
                    RuntimeError("focus lost")))

    def test_runtime_disabled_and_step_behavior(self):
        fake = FakeClipboard(ClipboardState("text", "already"))
        desk = FakeDesktop()
        finished = threading.Event()
        results = []
        runner = MacroExecutor([
            Action(kind="clipboard_set", clipboard_text="disabled", enabled=False),
            Action(kind="clipboard_paste"),
        ], 1, 0, lambda *a: None,
            lambda *a: (results.append(a), finished.set()),
            automation=desk, clipboard=fake, step_mode=True)
        runner.start()
        self.assertFalse(finished.wait(.03))
        self.assertFalse(desk.events)
        runner.step()
        self.assertTrue(finished.wait(2))
        self.assertTrue(results[0][0])
        self.assertEqual(fake.state.text, "already")
        self.assertEqual(desk.events, [("hotkey", ("ctrl", "v"))])

    def test_no_clipboard_service_errors_without_data_leak(self):
        secret = "private🔐value"
        results, diagnostics = [], []
        runner = MacroExecutor([
            Action(kind="clipboard_set", clipboard_text=secret),
        ], 1, 0, lambda *a: None, lambda *a: results.append(a),
            automation=FakeDesktop(), on_diagnostic=diagnostics.append)
        runner.run()
        self.assertFalse(results[0][0])
        self.assertNotIn(secret, str(results) + str(diagnostics))

    def test_clipboard_failure_skip_policy_and_no_keystrokes(self):
        fake = FakeClipboard()
        fake.fail_write = True
        results, events = [], []
        desk = FakeDesktop()
        MacroExecutor([
            Action(kind="clipboard_set", clipboard_text="sensitive",
                   failure_policy="skip"),
            Action(kind="key", keys="a"),
        ], 1, 0, lambda *a: None, lambda *a: results.append(a),
            automation=desk, clipboard=fake, on_diagnostic=events.append).run()
        self.assertTrue(results[0][0])
        self.assertIn(("press", "a"), desk.events)  # see fake below
        self.assertTrue(any(e["event"] == "action_skipped" for e in events))
        self.assertNotIn("sensitive", str(events))


if __name__ == "__main__":
    unittest.main()
