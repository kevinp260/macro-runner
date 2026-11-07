"""Thread-safe Qt clipboard access through the GUI thread.

All QClipboard operations are performed by a QObject on QApplication's thread.
The playback worker waits for a bounded response and can still be stopped.
"""
import threading
import time

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication


from macro_clipboard import ClipboardState, ClipboardUnavailable


class QtClipboardClient(QObject):
    request = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.request.connect(self._handle_request, Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _operate(operation, value=None):
        app = QApplication.instance()
        if app is None:
            raise ClipboardUnavailable("The clipboard needs a running desktop application.")
        clipboard = app.clipboard()
        if clipboard is None:
            raise ClipboardUnavailable("Clipboard service is unavailable.")
        try:
            if operation == "read":
                mime = clipboard.mimeData()
                if mime is None or not mime.formats():
                    return ClipboardState("empty")
                if not mime.hasText():
                    return ClipboardState("other")
                return ClipboardState("text", clipboard.text())
            if operation == "set":
                clipboard.setText(value, QClipboard.Mode.Clipboard)
                if clipboard.text(QClipboard.Mode.Clipboard) != value:
                    raise ClipboardUnavailable("Unable to set clipboard text.")
                return None
            if operation == "clear":
                clipboard.clear(QClipboard.Mode.Clipboard)
                return None
        except Exception:
            # Qt/platform errors may carry sensitive clipboard data.
            raise ClipboardUnavailable("Desktop clipboard access failed.") from None
        raise ValueError("Unrecognized clipboard operation.")

    @Slot(object)
    def _handle_request(self, item):
        if item["cancelled"].is_set():
            return
        try:
            item["result"] = self._operate(item["operation"], item["value"])
        except Exception as exc:
            item["error"] = exc
        finally:
            item["done"].set()

    def _call(self, operation, value=None, gate=None, *, cleanup=False):
        if QThread.currentThread() == self.thread():
            return self._operate(operation, value)
        item = {
            "operation": operation, "value": value,
            "done": threading.Event(), "cancelled": threading.Event(),
            "result": None, "error": None,
        }
        self.request.emit(item)
        deadline = time.monotonic() + 5.0
        while not item["done"].wait(0.05):
            if time.monotonic() >= deadline:
                item["cancelled"].set()
                raise ClipboardUnavailable("Desktop clipboard request timed out.")
            if gate is not None and not cleanup:
                try:
                    gate.wait(0)
                except Exception:
                    item["cancelled"].set()
                    raise
        if item["error"] is not None:
            raise item["error"]
        return item["result"]

    def read(self, gate=None, *, cleanup=False):
        return self._call("read", gate=gate, cleanup=cleanup)

    def set_text(self, text, gate=None, *, cleanup=False):
        if not isinstance(text, str):
            raise ValueError("Clipboard text must be a string.")
        self._call("set", text, gate=gate, cleanup=cleanup)

    def clear(self, gate=None, *, cleanup=False):
        self._call("clear", gate=gate, cleanup=cleanup)
