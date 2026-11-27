"""Main-thread display validation for the opt-in Wayland trial."""
import threading

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from macro_platform import DesktopUnavailable
from macro_wayland_automation import WaylandAutomation


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
        self.invalidated.set()

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

    def close(self):
        self.timer.stop()
        for signal in self.signals:
            try:
                signal.disconnect(self.invalidate)
            except (RuntimeError, TypeError):
                pass
        self.signals.clear()
        self.deleteLater()
