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


def changed_pixel_mask(baseline, candidate, tolerance=15):
    """Boolean mask of changed RGB pixels, shared by runtime and debugger.

    A pixel differs when any RGB channel exceeds the tolerance. The screenshot
    comparison deliberately ignores alpha, as the runtime has always done.
    """
    before = np.asarray(baseline.convert("RGB"), dtype=np.int16)
    after = np.asarray(candidate.convert("RGB"), dtype=np.int16)
    if before.shape != after.shape:
        raise ValueError("Screen region dimensions changed while watching.")
    return np.any(np.abs(before - after) > tolerance, axis=2)


def changed_pixel_percent(baseline, candidate, tolerance=15):
    """Percent of RGB pixels changed beyond per-channel tolerance."""
    mask = changed_pixel_mask(baseline, candidate, tolerance)
    return 100.0 * float(np.count_nonzero(mask)) / mask.size


class RegionChangeDetector:
    """Shared state machine for real playback and the visual monitor tester.

    Only a *confirmed* screenshot replaces the baseline, so A -> B -> A is
    observed as two changes. Temporary flicker resets the confirmation count.
    """

    def __init__(self, action, baseline):
        self.action = action
        self.baseline = baseline.convert("RGB")
        self.pending = None
        self.confirmations = 0
        self.triggers = 0

    def observe(self, candidate):
        """Return (percentage, confirmation count, triggered, old baseline, mask).

        The old baseline and mask are exposed for a diagnostic preview; the
        same decision path is used for real actions and test monitoring.
        """
        candidate = candidate.convert("RGB")
        prior = self.baseline
        mask = changed_pixel_mask(prior, candidate, self.action.watch_pixel_tolerance)
        percentage = 100.0 * float(np.count_nonzero(mask)) / mask.size

        if percentage < self.action.watch_change_percent:
            self.pending = None
            self.confirmations = 0
            return percentage, 0, False, prior, mask

        if (self.pending is None or
                changed_pixel_percent(self.pending, candidate,
                                      self.action.watch_pixel_tolerance)
                >= self.action.watch_change_percent):
            self.pending = candidate
            self.confirmations = 1
        else:
            self.confirmations += 1

        count = self.confirmations
        if count >= self.action.watch_confirmations:
            self.baseline = candidate
            self.pending = None
            self.confirmations = 0
            self.triggers += 1
            return percentage, count, True, prior, mask
        return percentage, count, False, prior, mask


def watch_region_change(action, screenshot, gate, baseline=None):
    """Wait until a stable change from the last accepted screenshot occurs."""
    region = (action.region_x, action.region_y, action.region_w, action.region_h)
    gate.wait(0)
    if baseline is None:
        baseline = screenshot(region=region).convert("RGB")
    detector = RegionChangeDetector(action, baseline)
    while True:
        gate.wait(action.poll_interval)
        current = screenshot(region=region).convert("RGB")
        _, _, triggered, _, _ = detector.observe(current)
        if triggered:
            return detector.baseline
