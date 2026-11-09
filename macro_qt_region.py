"""Drag-to-select desktop region overlay for the Qt workflow inspector.

A translucent window is placed on each available screen. The picker
only reports coordinates; reference capture can separately save the selected
pixels. Escape cancels without changing the selected action.
"""
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QCursor
from PySide6.QtWidgets import QWidget, QApplication


def normalized_region(start, end):
    """Return X/Y/width/height for a drag in any direction."""
    left, right = sorted((start.x(), end.x()))
    top, bottom = sorted((start.y(), end.y()))
    return left, top, right - left, bottom - top


def save_reference_capture(image, assets_dir):
    """Save a new reference PNG without replacing an existing image."""
    folder = Path(assets_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"reference-{uuid4().hex}.png"
    try:
        image.save(target, format="PNG")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target)


class RegionOverlay(QWidget):
    selected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(None)
        self.screen = screen
        self.start = None
        self.end = None
        self.start_native = None
        self.setWindowFlags(Qt.WindowType.Tool |
                            Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 20, 35, 100))
        if self.start is not None and self.end is not None:
            rect = QRect(self.start, self.end).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(94, 183, 255), 2))
            painter.drawRect(rect)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(20, 32, "Drag to select a screen region · Esc to cancel")

    @staticmethod
    def _pointer_pixel():
        # Qt events report logical widget coordinates. PyAutoGUI screenshot
        # regions use physical desktop pixels, which can differ with DPI.
        import pyautogui
        x, y = pyautogui.position()
        return QPoint(int(x), int(y))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                self.start_native = self._pointer_pixel()
            except Exception:
                self.cancelled.emit()
                return
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start is None:
            return
        self.end = event.position().toPoint()
        try:
            end_native = self._pointer_pixel()
        except Exception:
            self.cancelled.emit()
            return
        x, y, width, height = normalized_region(self.start_native, end_native)
        if width < 3 or height < 3:
            self.start = None
            self.end = None
            self.start_native = None
            self.update()
            return
        self.selected.emit(x, y, width, height)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)


class RegionPicker:
    """Own overlay windows until a selection is made or cancelled."""

    def __init__(self, selected, cancelled=None):
        self._selected = selected
        self._cancelled = cancelled
        self.overlays = []
        for screen in QApplication.screens():
            overlay = RegionOverlay(screen)
            overlay.selected.connect(self._finish)
            overlay.cancelled.connect(self.cancel)
            self.overlays.append(overlay)

    def show(self):
        for overlay in self.overlays:
            overlay.show()
            overlay.raise_()
        current = QApplication.screenAt(QCursor.pos())
        for overlay in self.overlays:
            if overlay.screen == current:
                overlay.activateWindow()
                overlay.setFocus()
                break

    def _close(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def _finish(self, x, y, width, height):
        self._close()
        self._selected(x, y, width, height)

    def cancel(self, notify=True):
        self._close()
        if notify and self._cancelled:
            self._cancelled()
