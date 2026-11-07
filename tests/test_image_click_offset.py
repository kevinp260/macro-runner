"""Image-relative click positions: match geometry, bounds and Stop safety."""
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from macro_model import Action, parse_document, serialize_document, validate_action
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_vision import image_click_point, locate_image
from macro_windows import WindowInfo, WindowManager, target_from_window


class Desktop:
    def __init__(self, image, on_screenshot=None):
        self.image = image
        self.clicks = []
        self.on_screenshot = on_screenshot

    def screenshot(self, region=None):
        if self.on_screenshot:
            self.on_screenshot()
        if region is None:
            return self.image
        x, y, w, h = region
        return self.image.crop((x, y, x + w, y + h))

    def size(self):
        return self.image.size

    def click(self, *args, **kwargs):
        self.clicks.append((args, kwargs))

    def keyDown(self, name): pass
    def keyUp(self, name): pass


class FakeBackend:
    def __init__(self, info):
        self.items = [info]
        self.active = info.handle

    def windows(self):
        return list(self.items)

    def foreground_handle(self):
        return self.active

    def activate(self, handle):
        self.active = handle


class ImageOffsetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "landmark.png"
        self.template = Image.new("RGB", (7, 5))
        for y in range(5):
            for x in range(7):
                self.template.putpixel((x, y),
                                       (23 + x * 25, 33 + y * 35, (x * y * 13) % 255))
        self.template.save(self.path)
        self.image = Image.new("RGB", (400, 360), "#eeeeee")
        self.image.paste(self.template, (120, 220))
        self.desktop = Desktop(self.image)

    def action(self, **kwargs):
        return Action(kind="click_image", image_path=str(self.path),
                      timeout=0, confidence=.99, **kwargs)

    def run_once(self, action, desktop=None, **extra):
        outcome, diagnostics = [], []
        runner = MacroExecutor(
            [action], 1, 0, lambda *a: None,
            lambda *a: outcome.append(a),
            automation=desktop or self.desktop,
            on_diagnostic=diagnostics.append,
            **extra)
        runner.run()
        return outcome, diagnostics

    def test_match_center_and_signed_offsets_use_physical_screen_points(self):
        match = locate_image(self.action(), self.desktop.screenshot)
        self.assertEqual(match[:2], (123, 222))
        for offset, point in [
            ((0, 0), (123, 222)),
            ((21, -11), (144, 211)),
            ((-12, 5), (111, 227)),
        ]:
            with self.subTest(offset=offset):
                desktop = Desktop(self.image)
                result, _ = self.run_once(
                    self.action(image_offset_x=offset[0],
                                image_offset_y=offset[1]),
                    desktop)
                self.assertTrue(result[0][0], result)
                self.assertEqual(desktop.clicks, [((point[0], point[1]), {"button":"left"})])

    def test_zero_offset_does_not_restrict_legacy_secondary_monitor_coordinates(self):
        # Some older desktop backends could click matched centers beyond
        # PyAutoGUI's primary-screen size; zero offsets must not change that.
        legacy = self.action()
        self.assertEqual(
            image_click_point(legacy, (2100, 250, .99),
                              screen_size=(1920, 1080),
                              client_rect=(0, 0, 100, 100)), (2100, 250))
        desktop = Desktop(self.image)
        with patch("macro_runtime.locate_image",
                   return_value=(2100, 250, .99)):
            result, _ = self.run_once(legacy, desktop)
        self.assertTrue(result[0][0], result)
        self.assertEqual(desktop.clicks[0][0], (2100, 250))

    def test_crop_match_center_offsets_include_region_origin_once(self):
        action = self.action(image_offset_x=-13, image_offset_y=7,
                             region_x=110, region_y=210,
                             region_w=35, region_h=30)
        match = locate_image(action, self.desktop.screenshot)
        self.assertEqual(match[:2], (123, 222))
        result, _ = self.run_once(action)
        self.assertTrue(result[0][0], result)
        self.assertEqual(self.desktop.clicks[0][0], (110, 229))

    def test_explicit_point_check_negative_and_outside_primary(self):
        action = self.action()
        self.assertEqual(image_click_point(action, (123, 222, .95),
                                           screen_size=(400, 360)), (123,222))
        for offsets, msg in [
            ((-124, 0), "negative coordinates"),
            ((0, -223), "negative coordinates"),
            ((277, 0), "outside the primary"),
            ((0, 138), "outside the primary"),
        ]:
            with self.subTest(offsets=offsets):
                action = self.action(image_offset_x=offsets[0],
                                     image_offset_y=offsets[1])
                with self.assertRaisesRegex(ValueError, msg):
                    image_click_point(action, (123, 222, .95),
                                      screen_size=(400, 360))
                desktop = Desktop(self.image)
                result, events = self.run_once(action, desktop)
                self.assertFalse(result[0][0])
                self.assertEqual(desktop.clicks, [])
                self.assertTrue(any(event["event"] == "action_error"
                                    for event in events))

    def test_client_relative_offset_cannot_hit_outside_window(self):
        info = WindowInfo(44, "Target App", "Class", 500, 100, 200, 100, 90)
        backend = FakeBackend(info)
        bound = target_from_window(info)
        action = self.action(image_offset_x=20)
        results, _ = self.run_once(
            action, window_target=bound,
            window_manager=WindowManager(backend))
        self.assertTrue(results[0][0], results)
        self.assertEqual(self.desktop.clicks[0][0], (143, 222))
        desktop = Desktop(self.image)
        results, _ = self.run_once(
            self.action(image_offset_x=90), desktop,
            window_target=bound, window_manager=WindowManager(backend))
        self.assertFalse(results[0][0])
        self.assertIn("client area", results[0][1])
        self.assertEqual(desktop.clicks, [])

    def test_window_moved_after_match_aborts_before_click(self):
        info = WindowInfo(44, "Target App", "Class", 500, 100, 200, 100, 90)
        backend = FakeBackend(info)
        desktop = Desktop(self.image, on_screenshot=lambda: backend.items.__setitem__(
            0, replace(info, x=110)))
        results, _ = self.run_once(
            self.action(image_offset_x=2), desktop,
            window_target=target_from_window(info),
            window_manager=WindowManager(backend))
        self.assertFalse(results[0][0])
        self.assertIn("moved after image matching", results[0][1])
        self.assertEqual(desktop.clicks, [])

    def test_stop_after_match_prevents_all_input(self):
        results = []
        runner = MacroExecutor(
            [self.action(image_offset_x=10)], 1, 0, lambda *a: None,
            lambda *a: results.append(a), automation=self.desktop)
        self.desktop.on_screenshot = runner.stop
        runner.run()
        self.assertFalse(results[0][0])
        self.assertEqual(results[0][1], "Stopped.")
        self.assertFalse(self.desktop.clicks)

    def test_missing_template_or_no_match_never_clicks(self):
        missing = self.action()
        missing.image_path = str(self.path.parent / "missing.png")
        result, _ = self.run_once(missing)
        self.assertFalse(result[0][0])
        self.assertEqual(self.desktop.clicks, [])
        no_match = Desktop(Image.new("RGB", self.image.size, "#eeeeee"))
        result, _ = self.run_once(self.action(), no_match)
        self.assertFalse(result[0][0])
        self.assertIn("timed out", result[0][1])
        self.assertFalse(no_match.clicks)

    def test_offset_validation_and_backward_compatibility(self):
        legacy = {"kind": "click_image", "image_path": str(self.path)}
        parsed = validate_action(legacy)
        self.assertEqual((parsed.image_offset_x, parsed.image_offset_y), (0, 0))
        original = [self.action(image_offset_x=-17, image_offset_y=32)]
        doc = serialize_document(original, 1, 0)
        self.assertEqual(parse_document(doc)[0], original)
        self.assertEqual(validate_action(asdict(parsed)), parsed)
        for invalid in (True, 2.5, "20", None, 100001, -100001):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_action({**legacy, "image_offset_x": invalid})

    def test_preflight_warns_for_impossible_offsets_and_checks_image_bounds(self):
        action = self.action(
            region_x=110, region_y=210, region_w=35, region_h=30,
            image_offset_x=400)
        findings = inspect_workflow([action], screen_size=(400,360))
        self.assertTrue(any(f.severity == "warning" and
                            "offset" in f.message for f in findings), findings)
        safe = self.action(image_offset_x=-10, image_offset_y=6,
                           region_x=110, region_y=210,
                           region_w=35, region_h=30)
        self.assertEqual(inspect_workflow([safe], screen_size=(400,360)), [])

    def test_client_rectangle_point_validation_uses_global_coordinates(self):
        action = self.action(image_offset_x=-4, image_offset_y=3)
        self.assertEqual(
            image_click_point(action, (123,222,.9),
                              screen_size=(400,360),
                              client_rect=(100,200,100,90)), (119,225))
        with self.assertRaisesRegex(ValueError, "client area"):
            image_click_point(self.action(image_offset_x=100), (123,222,.9),
                              screen_size=(400,360),
                              client_rect=(100,200,100,90))


if __name__ == "__main__":
    unittest.main()
