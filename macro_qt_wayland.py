"""Main-thread display validation for the opt-in Wayland trial."""
import threading
from contextlib import contextmanager

from PySide6.QtCore import QObject, QTimer, QThread, Qt, QRect, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QDialog, QWidget, QVBoxLayout, QLabel

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

    def check(self):
        if self.invalidated.is_set():
            raise DesktopUnavailable("Display configuration changed during Wayland screen selection.")

    @contextmanager
    def capture_factory(self, stopped):
        """Read-only ScreenCast, never RemoteDesktop."""
        with self._capture_session(stopped, devices=0) as (_, capture):
            yield capture.screenshot

    @contextmanager
    def _capture_session(self, stopped, *, devices):
        self.check()
        with WaylandSession(APP_ID, stopped, devices=devices) as session:
            if session.logical_size != self.size:
                raise DesktopUnavailable("Authorized monitor differs from the editor display.")
            session.geometry_guard = self.check
            with WaylandCapture(session) as capture:
                yield session, capture

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
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.stopped = threading.Event()
        self.result = None
        self.error = None

    def stop(self):
        self.stopped.set()

    def run(self):
        try:
            self.result = self.operation(self.stopped)
        except Exception as exc:
            self.error = exc


def image_point(rect, size, x, y):
    """Map a click within the actual drawn image, excluding letterboxing."""
    if (rect.width() <= 0 or rect.height() <= 0 or
            not rect.contains(x, y)):
        return None
    return (min(size[0] - 1, (x - rect.x()) * size[0] // rect.width()),
            min(size[1] - 1, (y - rect.y()) * size[1] // rect.height()))


def selection_region(start, end):
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    return left, top, right - left + 1, bottom - top + 1


class SnapshotCanvas(QWidget):
    selected = Signal(object)

    def __init__(self, image, point_mode, parent=None):
        super().__init__(parent)
        rgb = image.convert("RGB")
        data = rgb.tobytes()
        qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                        QImage.Format.Format_RGB888)
        self.pixmap = QPixmap.fromImage(qimage.copy())
        self.image_size = rgb.size
        self.point_mode = point_mode
        self.start = None
        self.end = None
        self.drawn = QRect()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(300, 200)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#15191e"))
        fitted = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.drawn = QRect((self.width() - fitted.width()) // 2,
                           (self.height() - fitted.height()) // 2,
                           fitted.width(), fitted.height())
        painter.drawPixmap(self.drawn, self.pixmap)
        if self.start is not None and self.end is not None and not self.point_mode:
            painter.setPen(QPen(QColor("#56b7ff"), 2))
            painter.drawRect(QRect(self.start, self.end).normalized())

    def resizeEvent(self, event):
        self.start = self.end = None
        self.drawn = QRect()
        super().resizeEvent(event)

    def _point(self, position):
        return image_point(self.drawn, self.image_size, position.x(), position.y())

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        if self._point(position) is not None:
            self.start = self.end = position
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start is None:
            return
        start = self._point(self.start)
        end = self._point(event.position().toPoint())
        self.start = self.end = None
        self.update()
        if start is None or end is None:
            return
        if self.point_mode:
            self.selected.emit(end)
        else:
            region = selection_region(start, end)
            if region[2] >= 3 and region[3] >= 3:
                self.selected.emit(region)


class SnapshotPicker(QDialog):
    """Choose coordinates from the exact captured pixels, not global mouse state."""
    def __init__(self, image, point_mode=False, parent=None):
        super().__init__(parent)
        self.selection = None
        self.setWindowTitle("Select from desktop snapshot")
        self.setWindowState(Qt.WindowState.WindowMaximized)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            ("Click a point" if point_mode else "Drag a region") +
            " on the captured screen · Esc to cancel"))
        canvas = SnapshotCanvas(image, point_mode, self)
        canvas.selected.connect(self._selected)
        layout.addWidget(canvas, 1)

    def _selected(self, selection):
        self.selection = selection
        self.accept()
