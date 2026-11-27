"""Main-thread display validation for the opt-in Wayland trial."""
import threading
import time
from contextlib import contextmanager

from PySide6.QtCore import QObject, QTimer, QThread, Signal
from PySide6.QtWidgets import QApplication

from macro_platform import DesktopUnavailable
from macro_wayland_automation import APP_ID, WaylandAutomation
from macro_wayland import WaylandSession
from macro_wayland_capture import WaylandCapture


def single_screen():
    app = QApplication.instance()
    if app is None or not app.platformName().lower().startswith("wayland"):
        raise DesktopUnavailable("MacroRunner must run with the native Qt Wayland platform.")
    screens = app.screens()
    if len(screens) != 1:
        raise DesktopUnavailable("The Wayland trial requires exactly one connected screen.")
    screen = screens[0]
    geometry = screen.geometry()
    if (geometry.x(), geometry.y()) != (0, 0) or screen.devicePixelRatio() != 1:
        raise DesktopUnavailable("The Wayland trial requires an origin screen at 100% scaling.")
    return screen, (geometry.width(), geometry.height())


class WaylandRunGuard(QObject):
    """Invalidate worker operations when the GUI sees any topology change."""
    geometry_invalidated = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.screen, self.size = single_screen()
        self.invalidated = threading.Event()
        app = QApplication.instance()
        self.signals = [app.screenAdded, app.screenRemoved,
                        self.screen.geometryChanged,
                        self.screen.logicalDotsPerInchChanged,
                        self.screen.physicalDotsPerInchChanged]
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._check)
        for signal in self.signals:
            signal.connect(self.invalidate)
        self.timer.start()

    def invalidate(self, *args):
        if not self.invalidated.is_set():
            self.invalidated.set()
            self.geometry_invalidated.emit()

    def _check(self):
        try:
            screen, size = single_screen()
            if screen != self.screen or size != self.size:
                self.invalidate()
        except (DesktopUnavailable, RuntimeError):
            self.invalidate()

    def factory(self, gate):
        # Called on the worker. Do not read Qt display objects here.
        return WaylandAutomation(gate, self.size, self.invalidated)

    def check(self):
        if self.invalidated.is_set():
            raise DesktopUnavailable("Display configuration changed during Wayland screen selection.")

    @contextmanager
    def capture_factory(self, stopped):
        """Read-only ScreenCast, never RemoteDesktop."""
        with self._capture_session(stopped, devices=0) as (_, capture):
            yield capture.screenshot

    @contextmanager
    def _capture_session(self, stopped, *, devices, cursor_mode=1):
        self.check()
        with WaylandSession(APP_ID, stopped, devices=devices, cursor_mode=cursor_mode) as session:
            if session.logical_size != self.size:
                raise DesktopUnavailable("Authorized monitor differs from the editor display.")
            session.geometry_guard = self.check
            with WaylandCapture(session) as capture:
                yield session, capture

    def pick_pointer(self, stopped, announce):
        # Wait until screen permission and the capture stream are ready.
        # The editor remains visible and no extra picker window is created.
        with self._capture_session(stopped, devices=0, cursor_mode=4) as (_, capture):
            capture.screenshot()
            announce("Move the pointer to the target — capturing in 3 seconds…")
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                capture.check()
                if stopped.wait(min(.05, max(0, deadline - time.monotonic()))):
                    raise RuntimeError("Stopped")
            return capture.pointer_sample()

    def test_move(self, stopped, x, y):
        # Explicitly authorized pointer-only action; verify capture geometry first.
        with self._capture_session(stopped, devices=2) as (session, capture):
            capture.screenshot()
            session.move_absolute(x, y)

    def close(self):
        self.timer.stop()
        for signal in self.signals:
            try:
                signal.disconnect(self.invalidate)
            except (RuntimeError, TypeError):
                pass
        self.signals.clear()
        self.deleteLater()


class EditorWorker(QThread):
    """Own native permission and capture work outside the GUI thread."""
    status = Signal(str)

    def __init__(self, operation, parent=None, *, announce=False):
        super().__init__(parent)
        self.operation = operation
        self.announce = announce
        self.stopped = threading.Event()
        self.result = None
        self.error = None

    def stop(self):
        self.stopped.set()

    def run(self):
        try:
            if self.announce:
                self.result = self.operation(self.stopped, self.status.emit)
            else:
                self.result = self.operation(self.stopped)
        except Exception as exc:
            self.error = exc

