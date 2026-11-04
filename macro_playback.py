"""Small thread-safe playback gate; no GUI dependencies."""
import time
import threading

from macro_model import loop_spans


def iter_execution_steps(actions):
    """Yield (original index, action), with each repeat block expanded lazily."""
    spans = loop_spans(actions)
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.kind == "loop_start":
            end = spans[index]
            for _ in range(action.repeats):
                for inner_index in range(index + 1, end):
                    inner = actions[inner_index]
                    if inner.enabled:
                        for __ in range(inner.repeats):
                            yield inner_index, inner
            index = end + 1
        elif action.kind == "loop_end":
            # Unreachable for a valid sequence.
            raise ValueError("Loop End without a matching Loop Start.")
        else:
            if action.enabled:
                for _ in range(action.repeats):
                    yield index, action
            index += 1


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
    """Count executable actions across all loops without expanding them."""
    spans = loop_spans(actions)
    total = 0
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.kind == "loop_start":
            end = spans[index]
            total += action.repeats * sum(
                item.repeats for item in actions[index + 1:end] if item.enabled
            )
            index = end + 1
        else:
            if action.kind != "loop_end" and action.enabled:
                total += action.repeats
            index += 1
    return total * repeat_count
