"""Small thread-safe playback gate; no GUI dependencies."""
import time
import threading


class PlaybackGate:
    def __init__(self, stop_event=None):
        self.stopped = stop_event or threading.Event()
        self._allowed = threading.Event()
        self._allowed.set()

    @property
    def paused(self):
        return not self._allowed.is_set()

    def pause(self):
        self._allowed.clear()

    def resume(self):
        self._allowed.set()

    def stop(self):
        self.stopped.set()
        self._allowed.set()

    def reset(self):
        self.stopped.clear()
        self._allowed.set()

    def wait(self, duration):
        """Wait for active (unpaused) time; Stop interrupts promptly."""
        remaining = max(0.0, float(duration))
        while True:
            if self.stopped.is_set():
                raise RuntimeError("Stopped")
            if not self._allowed.is_set():
                # Check Stop frequently even when paused.
                self.stopped.wait(0.05)
                continue
            if remaining <= 0:
                return
            step = min(0.05, remaining)
            started = time.monotonic()
            if self.stopped.wait(step):
                raise RuntimeError("Stopped")
            remaining -= time.monotonic() - started


def progress_total(actions, repeat_count):
    return sum(a.repeats for a in actions if a.enabled) * repeat_count
