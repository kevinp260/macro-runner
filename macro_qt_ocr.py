"""Read-only live OCR preview. No screenshots or recognized text persist."""
import threading

from PIL import ImageDraw
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from macro_ocr import check_engine, find_text, OCRError
from macro_windows import WindowBinding


class OCRPreviewWorker(QThread):
    frame = Signal(object)
    error = Signal(str)

    def __init__(self, action, window_target=None, screenshot=None, parent=None):
        super().__init__(parent)
        self.action = action
        self.window_target = window_target
        self.screenshot = screenshot
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            engine = check_engine(self.action.text_language)
            screenshot = self.screenshot
            if screenshot is None:
                import pyautogui
                screenshot = pyautogui.screenshot
            binding = (WindowBinding(self.window_target)
                       if self.window_target is not None else None)
            while not self._stop.is_set():
                current = self.action
                if binding is not None:
                    # Read-only preview must not activate another application.
                    current = binding.transform(current, binding.resolve())
                region = ((current.region_x, current.region_y,
                           current.region_w, current.region_h)
                          if current.region_x is not None else None)
                if region is not None and (region[0] < 0 or region[1] < 0):
                    raise OCRError("OCR region cannot start at negative screen coordinates.")
                capture = screenshot(region=region) if region else screenshot()
                match = find_text(
                    current, lambda region=None: capture, executable=engine)
                if self._stop.is_set():
                    return
                reduced = capture.convert("RGB")
                reduced.thumbnail((680, 360))
                if match is not None:
                    dx, dy = (region[0], region[1]) if region else (0, 0)
                    sx = reduced.width / capture.width
                    sy = reduced.height / capture.height
                    box = [
                        (round((match.x - dx) * sx), round((match.y - dy) * sy)),
                        (round((match.x - dx + match.width) * sx),
                         round((match.y - dy + match.height) * sy)),
                    ]
                    ImageDraw.Draw(reduced).rectangle(box, outline="lime", width=3)
                self.frame.emit({"image": reduced, "match": match})
                if self._stop.wait(1.5):
                    break
        except Exception as exc:
            if not self._stop.is_set():
                # OCR errors exclude recognized text, screenshot pixels and paths.
                self.error.emit(str(exc) if isinstance(exc, OCRError)
                                else "OCR preview failed. Check screen capture, "
                                     "target-window visibility and Tesseract setup.")


def _pixmap(image):
    image = image.convert("RGB")
    pixels = image.tobytes()
    qimage = QImage(pixels, image.width, image.height, image.width * 3,
                    QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


class OCRPreviewDialog(QDialog):
    """Live image and match bounds; never clicks or changes the editor."""
    def __init__(self, action, window_target=None, screenshot=None, parent=None):
        super().__init__(parent)
        self.action = action
        self.window_target = window_target
        self.screenshot = screenshot
        self.worker = None
        self.setWindowTitle("Live offline OCR preview")
        self.resize(730, 480)
        layout = QVBoxLayout(self)
        help_text = QLabel(
            "Read-only live preview. Keep this dialog away from the text being "
            "recognized. No clicking or file/network export occurs. "
            "Small text, DPI scaling, animations and poor contrast may reduce accuracy.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.picture = QLabel("Waiting for OCR…")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumSize(350, 220)
        layout.addWidget(self.picture, 1)
        self.status = QLabel("OCR has not started.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("Close preview")
        close.clicked.connect(self.close)
        layout.addWidget(close)

    def start_preview(self):
        if self.worker is not None:
            return
        self.worker = OCRPreviewWorker(self.action, self.window_target,
                                       screenshot=self.screenshot, parent=self)
        self.worker.frame.connect(self._frame)
        self.worker.error.connect(self._error)
        self.worker.start()

    def _frame(self, data):
        self.picture.setPixmap(_pixmap(data["image"]))
        match = data["match"]
        if match is None:
            self.status.setText("Target phrase not found at the selected confidence.")
        else:
            self.status.setText(
                f"Found phrase center at {match.center}; "
                f"minimum word confidence {match.confidence:.1%}. "
                "No click sent.")

    def _error(self, message):
        self.status.setText(message)

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.stop()
            if not self.worker.wait(12000):
                event.ignore()
                self.status.setText("Waiting for the local OCR process to stop.")
                return
            self.worker = None
        event.accept()
