"""Opt-in offline OCR using the locally installed Tesseract executable.

Screenshots are piped through memory; no network calls or image/text logs.
Only confirmed word-level matches supply click coordinates.
"""
import csv
from dataclasses import dataclass
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from PIL import Image


class OCRError(ValueError):
    """Missing local OCR setup, bad image, or recognition failure."""


@dataclass(frozen=True)
class TextMatch:
    x: int  # Physical desktop coordinates, not relative to the screenshot
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self):
        return (self.x + self.width // 2, self.y + self.height // 2)


LANGUAGE = re.compile(r"[a-z]{3}(?:\+[a-z]{3}){0,3}\Z")
MAX_IMAGE_PIXELS = 25_000_000
OCR_TIMEOUT = 8  # Bound each native subprocess; waiting can be interrupted between probes.


def engine_path():
    """Tesseract is never downloaded or bundled automatically."""
    configured = os.environ.get("TESSERACT_CMD")
    if configured:
        executable = Path(configured).expanduser()
        if executable.is_file():
            return str(executable)
        raise OCRError("TESSERACT_CMD points to a missing executable.")
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform == "win32":
        for key in ("ProgramFiles", "ProgramFiles(x86)"):
            directory = os.environ.get(key)
            if directory:
                candidate = Path(directory) / "Tesseract-OCR" / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate)
    raise OCRError(
        "Offline OCR needs Tesseract installed locally. "
        "Install tesseract-ocr (Ubuntu) or Tesseract OCR for Windows, "
        "then ensure tesseract is on PATH or set TESSERACT_CMD.")


def validate_language(language):
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language):
        raise OCRError("OCR language must be one to four three-letter codes, e.g. eng or eng+deu.")
    return language


def _run(args, *, image_bytes=None, timeout=OCR_TIMEOUT):
    try:
        result = subprocess.run(
            args, input=image_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise OCRError("Local OCR timed out. Try a smaller region.") from exc
    except OSError as exc:
        raise OCRError("Could not start the local Tesseract OCR engine.") from exc
    if result.returncode:
        # Tesseract's error output can include user-controlled paths/text.
        raise OCRError(
            "Local Tesseract failed. Verify the installed language packs "
            "and that the selected screen region can be read.")
    if len(result.stdout) > 4 * 1024 * 1024:
        raise OCRError("Tesseract returned too much text; select a smaller region.")
    return result.stdout


def check_engine(language="eng"):
    """Check language availability without capturing the desktop."""
    requested = validate_language(language).split("+")
    executable = engine_path()
    try:
        output = _run([executable, "--list-langs"], timeout=4).decode(
            "utf-8", errors="replace")
    except UnicodeError as exc:
        raise OCRError("Tesseract language listing is not readable.") from exc
    available = set(output.split())
    missing = [code for code in requested if code not in available]
    if missing:
        raise OCRError(
            "Tesseract language pack missing: " + ", ".join(missing) +
            ". Install matching traineddata locally (e.g. tesseract-ocr-eng).")
    return executable


def _words(tsv, image_size, confidence):
    try:
        reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
        if not reader.fieldnames or not {
                "level", "page_num", "block_num", "par_num", "line_num",
                "left", "top", "width", "height", "conf", "text",
        }.issubset(reader.fieldnames):
            raise ValueError("Missing OCR TSV columns.")
        groups = {}
        for row in reader:
            if row["level"] != "5":
                continue
            word = (row["text"] or "").strip()
            if not word:
                continue
            score = float(row["conf"]) / 100.0
            if not confidence <= score <= 1:
                continue
            x, y, w, h = (int(row[field])
                          for field in ("left", "top", "width", "height"))
            if (w < 1 or h < 1 or x < 0 or y < 0 or
                    x + w > image_size[0] or y + h > image_size[1]):
                continue
            line = tuple(row[field] for field in (
                "page_num", "block_num", "par_num", "line_num"))
            groups.setdefault(line, []).append((word, x, y, w, h, score))
        return groups.values()
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise OCRError("Tesseract returned unreadable text bounding boxes.") from exc


def match_tsv(tsv, query, width, height, confidence, origin=(0, 0),
              require_unique=False):
    """Match one contiguous phrase; ambiguous click targets are rejected."""
    expected = query.casefold().split()
    if not expected:
        raise ValueError("Enter the text to locate.")
    matches = []
    for line in _words(tsv, (width, height), confidence):
        for i in range(len(line) - len(expected) + 1):
            chunk = line[i:i + len(expected)]
            if [entry[0].casefold() for entry in chunk] != expected:
                continue
            x = min(entry[1] for entry in chunk)
            y = min(entry[2] for entry in chunk)
            right = max(entry[1] + entry[3] for entry in chunk)
            bottom = max(entry[2] + entry[4] for entry in chunk)
            matches.append(TextMatch(x + origin[0], y + origin[1],
                                     right - x, bottom - y,
                                     min(entry[5] for entry in chunk)))
            if require_unique and len(matches) > 1:
                raise OCRError(
                    "OCR found multiple matching phrases. Restrict the region "
                    "to a single target before enabling a click.")
    return matches[0] if matches else None


def find_text(action, screenshot, *, executable=None):
    """One read-only OCR probe; caller handles polling and optional clicks."""
    region = ((action.region_x, action.region_y,
               action.region_w, action.region_h)
              if action.region_x is not None else None)
    if region is not None and (region[0] < 0 or region[1] < 0):
        raise OCRError("OCR screenshot region has a negative desktop origin.")
    try:
        image = screenshot(region=region) if region else screenshot()
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise OCRError("OCR capture is too large; select a smaller region.")
        if region is not None and image.size != (region[2], region[3]):
            raise OCRError(
                "OCR capture dimensions differ from the requested region. "
                "Check DPI scaling and screenshot permissions.")
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
    except Exception as exc:
        if isinstance(exc, OCRError):
            raise
        raise OCRError("Cannot capture the selected screen region for OCR.") from exc

    command = executable if executable is not None else check_engine(action.text_language)
    data = _run([command, "stdin", "stdout", "-l", action.text_language,
                 "--psm", "6", "tsv"], image_bytes=buffer.getvalue())
    try:
        output = data.decode("utf-8")
    except UnicodeError as exc:
        raise OCRError("Tesseract returned invalid text encoding.") from exc
    return match_tsv(output, action.text_target, image.width, image.height,
                     action.text_confidence,
                     (region[0], region[1]) if region else (0, 0),
                     require_unique=action.text_click)
