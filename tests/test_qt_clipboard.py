"""Offscreen Qt clipboard bridge and action-property regression tests."""
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QPlainTextEdit

from macro_clipboard import ClipboardState, ClipboardUnavailable
from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_clipboard import QtClipboardClient
from macro_qt_properties import PropertiesPanel
from qt_test_helpers import close_test_window

app = QApplication.instance() or QApplication([])


class QtClipboardTests(unittest.TestCase):
    def setUp(self):
        self.client = QtClipboardClient()
        self.client.clear()

    def tearDown(self):
        self.client.clear()
        self.client.deleteLater()

    def test_unicode_and_empty_on_gui_thread(self):
        text = "你好 ñ Γεια 🌿\nsecond line"
        self.client.set_text(text)
        self.assertEqual(self.client.read(), ClipboardState("text", text))
        self.client.clear()
        self.assertEqual(self.client.read().kind, "empty")

    def test_worker_must_use_qt_main_thread_and_remains_responsive(self):
        original = "مساء الخير 😄"
        result = {}

        def worker():
            try:
                self.client.set_text(original)
                result["state"] = self.client.read()
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 3
        while thread.is_alive() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        thread.join(timeout=0.1)
        self.assertFalse(thread.is_alive(), "Clipboard bridge deadlocked")
        self.assertNotIn("error", result)
        self.assertEqual(result["state"].text, original)

    def test_stop_cancels_a_pending_clipboard_write(self):
        self.client.set_text("original")
        result = {}
        class StopGate:
            def wait(self, seconds):
                raise RuntimeError("Stopped")

        def worker():
            try:
                self.client.set_text("should never be written", gate=StopGate())
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result.get("error"), RuntimeError)
        app.processEvents()  # Deliver canceled queued work.
        self.assertEqual(self.client.read().text, "original")

    def test_gui_clipboard_failure_keeps_messages_generic(self):
        secret = "Sensitive private clipboard text"
        with patch.object(QtClipboardClient, "_operate",
                          side_effect=ClipboardUnavailable("Clipboard unavailable")):
            with self.assertRaises(ClipboardUnavailable) as raised:
                self.client.set_text(secret)
        self.assertNotIn(secret, str(raised.exception))


class ClipboardPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.window = MacroWindow()

    def tearDown(self):
        close_test_window(self.window)

    def test_multiline_clipboard_set_properties_and_redacted_tree(self):
        text = "日本語 text\nsecond line 😀"
        w = self.window
        w._replace_actions([Action(kind="clipboard_set", clipboard_text=text)])
        w.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        editor = w.inspector.controls["clipboard_text"]
        self.assertIsInstance(editor, QPlainTextEdit)
        self.assertEqual(editor.toPlainText(), text)
        self.assertNotIn(text, w.tree.topLevelItem(0).text(0))
        editor.setPlainText("updated\nmessage")
        w.inspector.commit()
        self.assertEqual(w.actions[0].clipboard_text, "updated\nmessage")
        self.assertNotIn("updated", w.tree.topLevelItem(0).text(0))

    def test_paste_blank_is_existing_and_restore_checkbox_is_persisted(self):
        w = self.window
        w._replace_actions([Action(kind="clipboard_paste")])
        w.tree.topLevelItem(0).setSelected(True)
        app.processEvents()
        self.assertEqual(w.inspector.controls["clipboard_text"].toPlainText(), "")
        self.assertTrue(w.inspector.controls["clipboard_restore"].isChecked())
        w.inspector.controls["clipboard_text"].setPlainText("Greek γειά")
        w.inspector.controls["clipboard_restore"].setChecked(False)
        w.inspector.commit()
        self.assertEqual(w.actions[0].clipboard_text, "Greek γειά")
        self.assertFalse(w.actions[0].clipboard_restore)
        self.assertNotIn("γειά", w.tree.topLevelItem(0).text(0))
        w.inspector.controls["clipboard_text"].clear()
        w.inspector.commit()
        self.assertIsNone(w.actions[0].clipboard_text)

    def test_runtime_receives_qt_clipboard_service(self):
        self.assertIsInstance(self.window.clipboard_client, QtClipboardClient)


if __name__ == "__main__":
    unittest.main()
