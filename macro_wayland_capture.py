"""Read-only capture for an authorized, worker-owned Wayland session.

A fresh sample must match the selected monitor's logical size exactly. There is
no scaling approximation, desktop-wide capture fallback or cached-image return.
"""
import os
import time

from PIL import Image

from macro_platform import DesktopUnavailable

MAX_FRAME_BYTES = 256 * 1024 * 1024
MAX_FRAME_AGE_NS = 500_000_000


def decode_rgbx(raw, size, stride, offset=0):
    """Copy one packed RGBx frame, including any row padding, into Pillow."""
    width, height = size
    if (type(width) is not int or type(height) is not int or
            width <= 0 or height <= 0 or type(stride) is not int or
            stride < width * 4 or type(offset) is not int or offset < 0):
        raise DesktopUnavailable("Invalid Wayland frame layout.")
    # Pillow's raw decoder expects the complete padded rows.
    end = offset + height * stride
    if end > len(raw) or end > MAX_FRAME_BYTES:
        raise DesktopUnavailable("Incomplete or oversized Wayland frame.")
    return Image.frombytes("RGB", (width, height), raw[offset:end],
                           "raw", "RGBX", stride, 1)


def region_box(region, size):
    if region is None:
        return None
    if (not isinstance(region, (tuple, list)) or len(region) != 4 or
            any(type(n) is not int for n in region)):
        raise DesktopUnavailable("Screen region requires four integer coordinates.")
    x, y, width, height = region
    if (x < 0 or y < 0 or width <= 0 or height <= 0 or
            x + width > size[0] or y + height > size[1]):
        raise DesktopUnavailable("Screen region is outside the authorized monitor.")
    return x, y, x + width, y + height


class GstFrameSource:
    """The only GStreamer-specific boundary; owns the remote FD and pipeline."""

    def __init__(self, session):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstApp", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, GstApp, GstVideo
        except (ImportError, ValueError) as exc:
            raise DesktopUnavailable("Wayland capture requires GStreamer, PipeWire and GI typelibs.") from exc
        self.gst, self.video = Gst, GstVideo
        self.session = session
        self.pipeline = None
        self.sink = None
        self.fd = None
        try:
            Gst.init(None)
            self.fd = session.open_pipewire_remote()
            # pipewiresrc duplicates the FD for its core connection (verified
            # in PipeWire 1.6.2 gstpipewirecore.c). Keep our FD until teardown.
            self.pipeline = Gst.parse_launch(
                f"pipewiresrc fd={self.fd} path={session.node} "
                "! videoconvert ! video/x-raw,format=RGBx "
                "! appsink name=sink max-buffers=1 drop=true sync=false wait-on-eos=false")
            self.sink = self.pipeline.get_by_name("sink")
            if not isinstance(self.sink, GstApp.AppSink):
                raise DesktopUnavailable("Wayland capture pipeline has no app sink.")
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise DesktopUnavailable("Cannot start the Wayland capture pipeline.")
        except BaseException as exc:
            self.close()
            if isinstance(exc, (DesktopUnavailable, KeyboardInterrupt, SystemExit)) or str(exc) == "Stopped":
                raise
            raise DesktopUnavailable("Cannot initialize the Wayland capture pipeline.") from exc

    def _check_stream(self):
        gst = self.gst
        message = self.pipeline.get_bus().pop_filtered(
            gst.MessageType.ERROR | gst.MessageType.EOS)
        if message is not None:
            raise DesktopUnavailable("Wayland capture stream failed or ended.")

    def running_time(self):
        self._check_stream()
        clock = self.pipeline.get_clock()
        if clock is None:
            return None
        now, base = clock.get_time(), self.pipeline.get_base_time()
        if now == self.gst.CLOCK_TIME_NONE or base == self.gst.CLOCK_TIME_NONE or now < base:
            return None
        return now - base

    def read(self, timeout_ms):
        gst = self.gst
        self._check_stream()
        sample = self.sink.try_pull_sample(timeout_ms * gst.MSECOND)
        self._check_stream()
        if sample is None:
            return None
        try:
            info = self.video.VideoInfo.new_from_caps(sample.get_caps())
            buf = sample.get_buffer()
            segment = sample.get_segment()
            if (info is None or buf is None or segment is None or
                    info.finfo.name != "RGBx" or segment.format != gst.Format.TIME):
                raise DesktopUnavailable("Unexpected Wayland frame format.")
            size = (info.width, info.height)
            if size != self.session.logical_size:
                raise DesktopUnavailable(
                    "Wayland capture size differs from logical monitor size; scaling is unsupported.")
            pts = buf.pts
            if pts == gst.CLOCK_TIME_NONE:
                return None
            timestamp = segment.to_running_time(gst.Format.TIME, pts)
            if timestamp == gst.CLOCK_TIME_NONE:
                return None
            meta = self.video.buffer_get_video_meta(buf)
            stride = meta.stride[0] if meta else info.stride[0]
            offset = meta.offset[0] if meta else info.offset[0]
            length = buf.get_size()
            if not 0 < length <= MAX_FRAME_BYTES:
                raise DesktopUnavailable("Invalid Wayland frame buffer size.")
            raw = buf.extract_dup(0, length)
            return timestamp, decode_rgbx(raw, size, stride, offset)
        except DesktopUnavailable:
            raise
        except Exception as exc:
            raise DesktopUnavailable("Cannot decode the Wayland capture frame.") from exc

    def close(self):
        ok = True
        try:
            if self.pipeline is not None:
                if self.pipeline.set_state(self.gst.State.NULL) == self.gst.StateChangeReturn.FAILURE:
                    ok = False
        except Exception:
            ok = False
        finally:
            self.sink = None
            self.pipeline = None
            if self.fd is not None:
                fd, self.fd = self.fd, None
                try:
                    os.close(fd)
                except OSError:
                    ok = False
        return ok


class WaylandCapture:
    """Single-use capture owner; close the pipeline and its owned descriptor."""

    def __init__(self, session, *, source_factory=GstFrameSource, timeout=3.0):
        if not 0 < timeout <= 10:
            raise ValueError("Frame timeout must be between zero and ten seconds.")
        self.session = session
        self.source_factory = source_factory
        self.timeout = timeout
        self.source = None
        self.used = False
        self.last_timestamp = -1

    def __enter__(self):
        if self.used:
            raise RuntimeError("A Wayland capture cannot be restarted.")
        self.used = True
        self.session.check()
        try:
            self.source = self.source_factory(self.session)
            self.session.check()
            return self
        except BaseException:
            self.session.broken = True
            self.close()
            raise

    def check(self):
        self.session.check()
        if self.source is None:
            raise DesktopUnavailable("Wayland capture is not active.")
        try:
            self.source.running_time()  # Also checks the GStreamer bus for errors.
        except Exception:
            self.session.broken = True
            raise

    def screenshot(self, region=None):
        """Return an independent RGB image from a fresh, validated sample."""
        if self.source is None:
            raise DesktopUnavailable("Wayland capture is not active.")
        self.session.check()
        try:
            box = region_box(region, self.session.logical_size)
            deadline = time.monotonic() + self.timeout
            cutoff = self.source.running_time()
            while time.monotonic() < deadline:
                self.session.check()
                # Do not request a blocking sample beyond the remaining budget.
                wait_ms = max(0, min(50, int((deadline - time.monotonic()) * 1000)))
                sample = self.source.read(wait_ms)
                self.session.check()
                if sample is None:
                    continue
                timestamp, image = sample
                if image.size != self.session.logical_size:
                    raise DesktopUnavailable(
                        "Wayland capture size differs from logical monitor size; scaling is unsupported.")
                now = self.source.running_time()
                if now is None or timestamp > now:
                    continue
                if (timestamp <= self.last_timestamp or
                        (cutoff is not None and timestamp < cutoff) or
                        now - timestamp > MAX_FRAME_AGE_NS):
                    continue
                if time.monotonic() >= deadline:
                    break
                self.session.check()
                self.last_timestamp = timestamp
                return image.crop(box) if box is not None else image.copy()
            raise DesktopUnavailable("No fresh Wayland screen frame received before timeout.")
        except BaseException:
            # A failed capture is fatal to combined input/capture execution.
            self.session.broken = True
            raise

    def close(self):
        if self.source is None:
            return True
        source, self.source = self.source, None
        try:
            ok = source.close()
        except Exception:
            ok = False
        if not ok:
            self.session.broken = True
        return ok

    def __exit__(self, exc_type, exc, traceback):
        if not self.close() and exc_type is None:
            raise DesktopUnavailable("Wayland capture cleanup could not be confirmed.")
        return False
