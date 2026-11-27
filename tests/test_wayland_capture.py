"""Capture and coordinate tests with fake frames, no GI or desktop required."""
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from macro_platform import DesktopUnavailable
from macro_wayland_capture import (WaylandCapture, decode_rgbx, region_box,
                                   MAX_FRAME_AGE_NS)


class FakeSession:
    def __init__(self):
        self.logical_size = (4, 3)
        self.broken = False
        self.stopped = False
        self.revoked = False

    def check(self):
        if self.stopped:
            raise RuntimeError("Stopped")
        if self.revoked:
            raise DesktopUnavailable("Revoked")
        if self.broken:
            raise DesktopUnavailable("Broken")


class FakeSource:
    def __init__(self, session):
        self.frames = []
        self.clock = 100
        self.closed = False
        self.session = session
        self.on_read = None

    def running_time(self):
        return self.clock

    def read(self, timeout_ms):
        if self.on_read:
            self.on_read()
        if not self.frames:
            return None
        timestamp, image = self.frames.pop(0)
        self.clock = max(self.clock, timestamp)
        return timestamp, image

    def close(self):
        self.closed = True
        return True


class FrameTests(unittest.TestCase):
    def test_padded_rows_and_offset(self):
        raw = b"abc" + bytes([255, 0, 0, 0, 0, 255, 0, 0, 9, 9, 9, 9,
                              0, 0, 255, 0, 255, 255, 255, 0, 9, 9, 9, 9])
        image = decode_rgbx(raw, (2, 2), 12, 3)
        self.assertEqual([image.getpixel((x, y)) for y in range(2) for x in range(2)], [(255, 0, 0), (0, 255, 0),
                                                (0, 0, 255), (255, 255, 255)])

    def test_invalid_layout(self):
        for stride, offset, raw in ((3, 0, bytes(16)), (8, -1, bytes(16)),
                                    (8, 0, bytes(15))):
            with self.assertRaises(DesktopUnavailable):
                decode_rgbx(raw, (2, 2), stride, offset)

    def test_region_bounds(self):
        self.assertIsNone(region_box(None, (4, 3)))
        self.assertEqual(region_box((1, 1, 3, 2), (4, 3)), (1, 1, 4, 3))
        for region in ((-1, 0, 1, 1), (0, 0, 0, 1), (2, 2, 3, 1),
                       (0, 0, 1, 4), (True, 0, 1, 1), (0, 0, 1.0, 1), "1234"):
            with self.subTest(region=region), self.assertRaises(DesktopUnavailable):
                region_box(region, (4, 3))


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.source = FakeSource(self.session)
        self.capture = WaylandCapture(self.session, source_factory=lambda _: self.source,
                                      timeout=.02)
        self.red = Image.new("RGB", (4, 3), "red")
        self.blue = Image.new("RGB", (4, 3), "blue")

    def test_new_frame_after_request_and_independent_crop(self):
        self.source.frames = [(99, self.red), (101, self.blue), (101, self.red),
                              (102, self.red)]
        with self.capture as capture:
            first = capture.screenshot()
            self.assertEqual(first.getpixel((0, 0)), (0, 0, 255))
            first.putpixel((0, 0), (0, 0, 0))
            self.assertEqual(self.blue.getpixel((0, 0)), (0, 0, 255))
            second = capture.screenshot((1, 1, 2, 2))
            self.assertEqual(second.size, (2, 2))
            self.assertEqual(second.getpixel((0, 0)), (255, 0, 0))
        self.assertTrue(self.source.closed)

    def test_stale_frame_fails_closed(self):
        self.source.frames = [(99, self.red)]
        self.source.clock = MAX_FRAME_AGE_NS + 100
        with self.capture as capture:
            with self.assertRaisesRegex(DesktopUnavailable, "fresh"):
                capture.screenshot()
        self.assertTrue(self.session.broken)
        self.assertTrue(self.source.closed)

    def test_duplicate_frame_times_out(self):
        self.source.frames = [(101, self.red), (101, self.blue)]
        with self.capture as capture:
            capture.screenshot()
            with self.assertRaisesRegex(DesktopUnavailable, "fresh"):
                capture.screenshot()
        self.assertTrue(self.session.broken)

    def test_mismatched_dimensions_fail_closed(self):
        self.source.frames = [(101, Image.new("RGB", (8, 6)))]
        with self.capture as capture:
            with self.assertRaisesRegex(DesktopUnavailable, "scaling"):
                capture.screenshot()
        self.assertTrue(self.session.broken)

    def test_invalid_region_fails_without_reading(self):
        self.source.read = Mock(side_effect=AssertionError("read unexpectedly"))
        with self.capture as capture:
            with self.assertRaises(DesktopUnavailable):
                capture.screenshot((0, 0, 5, 3))
        self.source.read.assert_not_called()

    def test_stop_during_pull_prevents_frame_return(self):
        self.source.frames = [(101, self.red)]
        self.source.on_read = lambda: setattr(self.session, "stopped", True)
        with self.capture as capture:
            with self.assertRaisesRegex(RuntimeError, "Stopped"):
                capture.screenshot()
        self.assertTrue(self.source.closed)

    def test_revocation_during_pull_prevents_frame_return(self):
        self.source.frames = [(101, self.red)]
        self.source.on_read = lambda: setattr(self.session, "revoked", True)
        with self.capture as capture:
            with self.assertRaisesRegex(DesktopUnavailable, "Revoked"):
                capture.screenshot()
        self.assertTrue(self.source.closed)

    def test_stream_failure_is_fatal(self):
        self.source.read = Mock(side_effect=DesktopUnavailable("stream ended"))
        with self.capture as capture:
            with self.assertRaisesRegex(DesktopUnavailable, "stream ended"):
                capture.screenshot()
        self.assertTrue(self.session.broken)
        self.assertTrue(self.source.closed)

    def test_cleanup_failure_is_reported(self):
        self.source.close = Mock(return_value=False)
        with self.assertRaisesRegex(DesktopUnavailable, "cleanup"):
            with self.capture:
                pass
        self.assertTrue(self.session.broken)
        self.source.close.assert_called_once()

    def test_capture_cannot_be_reopened(self):
        with self.capture:
            pass
        with self.assertRaises(RuntimeError):
            with self.capture:
                pass


if __name__ == "__main__":
    unittest.main()
