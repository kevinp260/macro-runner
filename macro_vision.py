"""Screenshot-only OpenCV image matching and pixel/color checks.

PyAutoGUI is supplied by the runtime. Pure tests use synthetic screenshots.
"""
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image


@lru_cache(maxsize=24)
def _load_template(path):
    try:
        with Image.open(path) as image:
            return np.asarray(image.convert("RGB"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to open image {path!r}: {exc}") from exc


def _region(action):
    if action.region_x is None:
        return None
    return (action.region_x, action.region_y, action.region_w, action.region_h)


def locate_image(action, screenshot):
    """Return (center_x, center_y, similarity) for the closest match or None."""
    region = _region(action)
    screen = screenshot(region=region) if region else screenshot()
    haystack = np.asarray(screen.convert("RGB"))
    template = _load_template(action.image_path)
    th, tw = template.shape[:2]
    sh, sw = haystack.shape[:2]
    if tw > sw or th > sh:
        return None
    # SQDIFF_NORMED handles uniform templates, unlike CCOEFF_NORMED.
    result = cv2.matchTemplate(haystack, template, cv2.TM_SQDIFF_NORMED)
    minimum, _, (x, y), _ = cv2.minMaxLoc(result)
    score = 1.0 - float(minimum)
    if score < action.confidence:
        return None
    ox, oy = (region[0], region[1]) if region else (0, 0)
    return ox + x + tw // 2, oy + y + th // 2, score


def pixel_matches(action, screenshot):
    rgb = screenshot(region=(action.pixel_x, action.pixel_y, 1, 1))
    found = rgb.convert("RGB").getpixel((0, 0))
    expected = tuple(int(action.pixel_color[i:i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= action.pixel_tolerance for a, b in zip(found, expected))


def check_condition(action, screenshot):
    matched = (locate_image(action, screenshot) is not None
               if action.condition_source == "image"
               else pixel_matches(action, screenshot))
    return matched if action.match_mode == "matches" else not matched


def poll_until(action, probe, gate):
    """Poll up to timeout active seconds; pausing does not consume the budget."""
    remaining = action.timeout
    while True:
        gate.wait(0)
        value = probe()
        if value:
            return value
        if remaining <= 0:
            raise TimeoutError(f"{action.name or action.kind}: condition timed out.")
        interval = min(action.poll_interval, remaining)
        gate.wait(interval)
        remaining -= interval
