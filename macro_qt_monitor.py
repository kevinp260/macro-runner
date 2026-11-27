"""Read-only, live screen-region diagnostics for the Qt workflow editor.

The worker only takes screenshots. It never invokes MacroExecutor, mouse or
keyboard actions, and retains no captures on disk. The monitor uses exactly the
same RegionChangeDetector as playback, including confirmation and baseline
state transitions.
"""
import sys
import threading
from contextlib import ExitStack

import numpy as np
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from macro_vision import RegionChangeDetector
from macro_windows import WindowBinding
from macro_platform import get_automation


def capture_error_text(exc):
    """Explain common desktop capture failures without hiding the real error."""
    detail = str(exc).strip() or type(exc).__name__
    if sys.platform.startswith("linux"):
        hint = ("Check screen-capture permission and the desktop session. "
                "Ubuntu X11 requires a working screenshot backend (scrot); "
                "Wayland may deny programmatic captures.")
    else:
        hint = ("Check display permissions and whether an interactive desktop "
                "session is available. Locked or protected windows may not "
                "be capturable.")
    return f"Screen capture failed: {detail}\n{hint}"


def _preview(image, size=(250, 150)):
    """Bound queued Qt image data; do not send full-size captures to the UI."""
    result = image.convert("RGB")
    result.thumbnail(size, Image.Resampling.LANCZOS)
    return result.copy()


class RegionMonitorWorker(QThread):
    frame = Signal(object)
    capture_error = Signal(str)

    def __init__(self, action, screenshot=None, parent=None, window_target=None,
                 capture_factory=None):
        super().__init__(parent)
        self.action = action
        self.screenshot = screenshot
        self.capture_factory = capture_factory
        self.window_target = window_target
        self._stop_event = threading.Event()
        self._reset_event = threading.Event()
        self._wake = threading.Event()
        self.detector = None

    def stop(self):
        self._stop_event.set()
        self._wake.set()

    def reset_baseline(self):
        self._reset_event.set()
        self._wake.set()

    def run(self):
        try:
            with ExitStack() as stack:
                screenshot = self.screenshot
                if screenshot is None:
                    if self.capture_factory is not None:
                        screenshot = stack.enter_context(self.capture_factory(self._stop_event))
                    else:
                        screenshot = get_automation().screenshot
                binding = (WindowBinding(self.window_target)
                           if self.window_target is not None else None)

                def capture():
                    current = self.action
                    if binding is not None:
                        # Follow the same client-relative region as playback.
                        # Live testing must not activate windows or send input.
                        current = binding.transform(current, binding.resolve())
                    region = (current.region_x, current.region_y,
                              current.region_w, current.region_h)
                    if region[0] < 0 or region[1] < 0:
                        raise ValueError("Screenshot region starts at negative desktop "
                                         "coordinates; move the window onto a supported display.")
                    result = screenshot(region=region).convert("RGB")
                    if result.size != (region[2], region[3]):
                        raise ValueError("Screenshot dimensions do not match the selected "
                                         "region. Check monitor scaling and region bounds.")
                    return result, region

                baseline, baseline_region = capture()
                if self._stop_event.is_set():
                    return
                detector = RegionChangeDetector(self.action, baseline)
                self.detector = detector
                self.frame.emit({
                    "state": "baseline", "baseline": _preview(baseline),
                    "current": _preview(baseline),
                    "mask": Image.new("RGB", _preview(baseline).size, "black"),
                    "percent": 0.0, "confirmations": 0, "triggers": 0,
                    "region": baseline_region,
                })

                while not self._stop_event.is_set():
                    self._wake.wait(self.action.poll_interval)
                    self._wake.clear()
                    if self._stop_event.is_set():
                        break
                    latest, latest_region = capture()
                    if self._stop_event.is_set():
                        break
                    if self._reset_event.is_set():
                        self._reset_event.clear()
                        detector = RegionChangeDetector(self.action, latest)
                        self.detector = detector
                        small = _preview(latest)
                        self.frame.emit({
                            "state": "reset", "baseline": small, "current": small,
                            "mask": Image.new("RGB", small.size, "black"),
                            "percent": 0.0, "confirmations": 0, "triggers": 0,
                            "region": latest_region,
                        })
                        continue

                    percentage, confirmations, triggered, old, mask = detector.observe(latest)
                    mask_image = Image.fromarray(np.uint8(mask) * 255, mode="L")
                    self.frame.emit({
                        "state": ("triggered" if triggered else
                                  "confirming" if confirmations else "below"),
                        "baseline": _preview(old),
                        "current": _preview(latest),
                        "mask": _preview(mask_image),
                        "percent": percentage, "confirmations": confirmations,
                        "triggers": detector.triggers, "region": latest_region,
                    })
        except Exception as exc:
            if not self._stop_event.is_set():
                self.capture_error.emit(capture_error_text(exc))
        finally:
            # Full-resolution images are kept only while actively monitoring.
            self.detector = None


def _qt_region(physical, screen):
    """Map screenshot pixels to Qt window coordinates for preview placement."""
    geometry = screen.geometry()
    scale = screen.devicePixelRatio() or 1.0
    return QRect(
        geometry.x() + round((physical.x() - geometry.x()) / scale),
        geometry.y() + round((physical.y() - geometry.y()) / scale),
        max(1, round(physical.width() / scale)),
        max(1, round(physical.height() / scale)),
    )


def _pixmap(image):
    image = image.convert("RGB")
    raw = image.tobytes()
    frame = QImage(raw, image.width, image.height, image.width * 3,
                   QImage.Format.Format_RGB888)
    return QPixmap.fromImage(frame.copy())


class RegionMonitorDialog(QDialog):
    """Small independent window showing live captures and detection decisions."""

    def __init__(self, action, screenshot=None, parent=None, window_target=None,
                 capture_factory=None):
        super().__init__(parent)
        self.action = action
        self.screenshot = screenshot
        self.capture_factory = capture_factory
        self.window_target = window_target
        self.worker = None
        self._close_requested = False
        self.setWindowTitle("Test screen-region monitoring")
        self.setMinimumWidth(820)
        self.resize(850, 410)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        self.instructions = QLabel(
            "Read-only preview — no workflow actions are executed. "
            "Keep this window outside the watched region.")
        self.instructions.setWordWrap(True)
        root.addWidget(self.instructions)

        images = QGridLayout()
        self.previews = {}
        for col, (key, label) in enumerate((
            ("baseline", "Accepted baseline"),
            ("current", "Latest capture"),
            ("mask", "Changed-pixel mask"),
        )):
            title = QLabel(label)
            images.addWidget(title, 0, col)
            target = QLabel("Waiting for capture…")
            target.setAlignment(Qt.AlignmentFlag.AlignCenter)
            target.setMinimumSize(250, 154)
            target.setStyleSheet("border: 1px solid gray; border-radius: 6px;")
            images.addWidget(target, 1, col)
            self.previews[key] = target
        root.addLayout(images)

        self.region_text = QLabel(
            f"Region: ({action.region_x}, {action.region_y}) · "
            f"{action.region_w} × {action.region_h} px")
        root.addWidget(self.region_text)
        self.settings_text = QLabel(
            f"Interval: {action.poll_interval:g}s    "
            f"Threshold: {action.watch_change_percent:g}%    "
            f"Pixel tolerance: {action.watch_pixel_tolerance}    "
            f"Confirmations required: {action.watch_confirmations}")
        self.settings_text.setWordWrap(True)
        root.addWidget(self.settings_text)

        self.percent_text = QLabel("Pixels changed: —")
        self.progress_text = QLabel("Confirmations: 0 / "
                                    f"{action.watch_confirmations}")
        self.trigger_text = QLabel("Confirmed changes: 0")
        metrics = QHBoxLayout()
        for label in (self.percent_text, self.progress_text, self.trigger_text):
            metrics.addWidget(label)
        root.addLayout(metrics)

        self.status = QLabel("Ready to sample.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.overlap_warning = QLabel("")
        self.overlap_warning.setWordWrap(True)
        root.addWidget(self.overlap_warning)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start monitoring")
        self.stop_button = QPushButton("Stop testing")
        self.reset_button = QPushButton("Recapture baseline")
        self.close_button = QPushButton("Close")
        for button in (self.start_button, self.stop_button,
                       self.reset_button, self.close_button):
            buttons.addWidget(button)
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.reset_button.clicked.connect(self.reset_baseline)
        self.close_button.clicked.connect(self.close)
        root.addLayout(buttons)
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)

    def position_away_from_region(self):
        """Prefer a corner outside the actual target-relative capture area."""
        current = self.action
        if self.window_target is not None:
            try:
                binding = WindowBinding(self.window_target)
                current = binding.transform(current, binding.resolve())
            except Exception:
                # The worker reports the target error explicitly on Start.
                return
        physical = QRect(current.region_x, current.region_y,
                         current.region_w, current.region_h)
        screen = next((
            s for s in QApplication.screens()
            if QRect(s.geometry().x(), s.geometry().y(),
                     round(s.geometry().width() * s.devicePixelRatio()),
                     round(s.geometry().height() * s.devicePixelRatio()))
            .contains(physical.center())
        ), QApplication.primaryScreen())
        if screen is None:
            return
        region = _qt_region(physical, screen)
        available = screen.availableGeometry()
        width = min(self.width(), available.width())
        height = min(self.height(), available.height())
        positions = [
            QPoint(available.left(), available.top()),
            QPoint(available.right() - width + 1, available.top()),
            QPoint(available.left(), available.bottom() - height + 1),
            QPoint(available.right() - width + 1, available.bottom() - height + 1),
        ]
        position = min(
            positions, key=lambda p: QRect(p.x(), p.y(), width, height)
            .intersected(region).width() *
            QRect(p.x(), p.y(), width, height).intersected(region).height())
        self.move(position)
        rectangle = QRect(position.x(), position.y(), width, height)
        if rectangle.intersects(region):
            self.overlap_warning.setText(
                "Warning: the preview overlaps the monitored region. "
                "Move it away or reduce the region to avoid false changes.")
        else:
            self.overlap_warning.setText("")

    def start_monitoring(self):
        if self._close_requested or (self.worker is not None):
            return
        self.status.setText("Capturing the initial baseline…")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.reset_button.setEnabled(True)
        worker = RegionMonitorWorker(
            self.action, self.screenshot, parent=self,
            window_target=self.window_target, capture_factory=self.capture_factory)
        self.worker = worker
        worker.frame.connect(self._frame_received)
        worker.capture_error.connect(self._capture_failed)
        worker.finished.connect(self._worker_finished)
        worker.start()

    def stop_monitoring(self):
        if self.worker is not None:
            self.status.setText("Stopping monitor…")
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.reset_button.setEnabled(False)

    def reset_baseline(self):
        if self.worker is not None:
            self.status.setText("Recapturing baseline…")
            self.worker.reset_baseline()

    def _frame_received(self, frame):
        if "region" in frame:
            x, y, width, height = frame["region"]
            self.region_text.setText(
                f"Captured region: ({x}, {y}) · {width} × {height} px")
        for key, label in self.previews.items():
            pixmap = _pixmap(frame[key])
            label.setPixmap(pixmap)
        self.percent_text.setText(f"Pixels changed: {frame['percent']:.2f}%")
        self.progress_text.setText(
            f"Confirmations: {frame['confirmations']} / "
            f"{self.action.watch_confirmations}")
        self.trigger_text.setText(f"Confirmed changes: {frame['triggers']}")
        self.status.setText({
            "baseline": "Initial baseline captured; waiting for a change.",
            "reset": "Baseline reset to the current screen. Waiting for a change.",
            "below": "Below change threshold — no trigger.",
            "confirming": "Change candidate detected — awaiting confirmations.",
            "triggered": "Change detected and accepted as the new baseline.",
        }[frame["state"]])

    def _capture_failed(self, text):
        self.status.setText(text)

    def _worker_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.start_button.setEnabled(not self._close_requested)
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        if self._close_requested:
            QTimer.singleShot(0, self.close)
        elif not self.status.text().startswith("Screen capture failed:"):
            self.status.setText("Monitoring stopped. Start again to recapture baseline.")

    def reject(self):
        # QDialog.closeEvent may call reject(); avoid recursion through close().
        # Keep the dialog alive until the worker's finished signal is handled.
        if self.worker is not None:
            self._close_requested = True
            self.stop_monitoring()
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_requested = True
            self.stop_monitoring()
            event.ignore()
            return
        super().closeEvent(event)
