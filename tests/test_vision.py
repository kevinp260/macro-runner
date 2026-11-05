import tempfile
import unittest
from pathlib import Path

from PIL import Image

from macro_model import Action
from macro_vision import check_condition, locate_image, pixel_matches, poll_until


class Gate:
    def __init__(self):
        self.waits = []
    def wait(self, duration):
        self.waits.append(duration)


class VisionTests(unittest.TestCase):
    def test_match_region_and_location(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Image.new("RGB", (40, 30), (230, 230, 230))
            tile = Image.new("RGB", (5, 5))
            for y in range(5):
                for x in range(5):
                    tile.putpixel((x, y), (x * 40, y * 38, (x + y) * 18))
            image.paste(tile, (18, 12))
            filename = Path(folder) / "tile.png"
            tile.save(filename)
            def screenshot(region=None):
                if region:
                    x, y, w, h = region
                    return image.crop((x, y, x+w, y+h))
                return image
            action = Action(kind="click_image", image_path=str(filename), confidence=.97)
            self.assertEqual(locate_image(action, screenshot)[:2], (20, 14))
            action.region_x, action.region_y = 15, 9
            action.region_w, action.region_h = 12, 12
            self.assertEqual(locate_image(action, screenshot)[:2], (20, 14))
            action.region_x, action.region_y = 0, 0
            action.region_w, action.region_h = 8, 8
            self.assertIsNone(locate_image(action, screenshot))

    def test_pixel_color_tolerance_and_invert(self):
        a = Action(kind="wait_until", condition_source="pixel",
                   pixel_color="#AABBCC", pixel_tolerance=3)
        screen = lambda region=None: Image.new("RGB", (1, 1), (171, 185, 203))
        self.assertTrue(pixel_matches(a, screen))
        self.assertTrue(check_condition(a, screen))
        a.match_mode = "not_matches"
        self.assertFalse(check_condition(a, screen))

    def test_poll_until(self):
        a = Action(kind="wait_until", timeout=.3, poll_interval=.2)
        gate = Gate()
        probes = iter([False, False, True])
        self.assertTrue(poll_until(a, lambda: next(probes), gate))
        self.assertEqual(len(gate.waits), 5)
        for actual, expected in zip(gate.waits, [0, .2, 0, .1, 0]):
            self.assertAlmostEqual(actual, expected)
        with self.assertRaises(TimeoutError):
            poll_until(a, lambda: False, Gate())


if __name__ == "__main__":
    unittest.main()
