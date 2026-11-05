"""Playback sequencing and thread-safe pause/stop/step controls."""
import time
import threading

from macro_model import loop_spans


def iter_execution_steps(actions, start_index=0):
    """Yield (original index, action) lazily, starting at a selected list row.

    A selection inside a repeat block starts partway through its first cycle.
    Subsequent cycles are complete; earlier blocks are skipped without iteration.
    Selecting Loop End begins after that block.
    """
    if not 0 <= start_index < len(actions) and not (start_index == 0 and not actions):
        raise ValueError("Selected action is out of range.")
    spans = loop_spans(actions)
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.kind == "loop_start":
            end = spans[index]
            if end <= start_index:
                index = end + 1
                continue
            for cycle in range(action.repeats):
                first = max(index + 1, start_index) if cycle == 0 else index + 1
                for inner_index in range(first, end):
                    inner = actions[inner_index]
                    if inner.enabled:
                        for _ in range(inner.repeats):
                            yield inner_index, inner
            index = end + 1
        elif action.kind == "loop_end":
            raise ValueError("Loop End without matching Loop Start.")
        else:
            if index >= start_index and action.enabled:
                for _ in range(action.repeats):
                    yield index, action
            index += 1


class PlaybackGate:
    """Gate each action separately; a Step permits one complete action."""

    def __init__(self, stop_event=None):
        self.stopped = stop_event if stop_event is not None else threading.Event()
        self._condition = threading.Condition()
        self._paused = False
        self._step_tokens = 0
        self._step_active = False

    @property
    def paused(self):
        with self._condition:
            return self._paused

    def pause(self):
        with self._condition:
            self._paused = True
            self._step_tokens = 0

    def resume(self):
        with self._condition:
            self._paused = False
            self._step_tokens = 0
            self._condition.notify_all()

    def step(self):
        with self._condition:
            if not self._paused:
                raise RuntimeError("Pause before stepping.")
            if self.stopped.is_set():
                raise RuntimeError("Stopped")
            self._step_tokens += 1
            self._condition.notify_all()

    def stop(self):
        self.stopped.set()
        with self._condition:
            self._step_tokens = 0
            self._condition.notify_all()

    def reset(self):
        with self._condition:
            self.stopped.clear()
            self._paused = False
            self._step_tokens = 0
            self._step_active = False
            self._condition.notify_all()

    def begin_action(self):
        """Wait until running or a single-step token is granted."""
        with self._condition:
            while self._paused and self._step_tokens == 0 and not self.stopped.is_set():
                self._condition.wait(0.05)
            if self.stopped.is_set():
                raise RuntimeError("Stopped")
            if self._paused:
                self._step_tokens -= 1
                self._step_active = True
            else:
                self._step_active = False

    def end_action(self):
        """Release single-step permission at the action boundary."""
        with self._condition:
            was_step = self._step_active
            self._step_active = False
            self._condition.notify_all()
            return was_step and self._paused

    def wait(self, duration):
        """Wait for active time; Stop interrupts, a Step runs to completion."""
        remaining = max(0.0, float(duration))
        while True:
            if self.stopped.is_set():
                raise RuntimeError("Stopped")
            with self._condition:
                if self._paused and not self._step_active:
                    self._condition.wait(0.05)
                    continue
            if remaining <= 0:
                return
            step = min(0.05, remaining)
            started = time.monotonic()
            if self.stopped.wait(step):
                raise RuntimeError("Stopped")
            remaining -= time.monotonic() - started


def progress_total(actions, repeat_count, start_index=0):
    """Count executable steps without expanding loops, with optional suffix."""
    if isinstance(repeat_count, bool) or not isinstance(repeat_count, int) or repeat_count < 1:
        raise ValueError("Repeat count must be a positive integer.")
    if not 0 <= start_index < len(actions) and not (start_index == 0 and not actions):
        raise ValueError("Selected action is out of range.")
    spans = loop_spans(actions)
    total = 0
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.kind == "loop_start":
            end = spans[index]
            if end <= start_index:
                index = end + 1
                continue
            full_cycle = sum(a.repeats for a in actions[index + 1:end] if a.enabled)
            first_index = max(index + 1, start_index)
            first_cycle = sum(a.repeats for a in actions[first_index:end] if a.enabled)
            total += first_cycle + (action.repeats - 1) * full_cycle
            index = end + 1
        else:
            if action.kind != "loop_end" and action.enabled and index >= start_index:
                total += action.repeats
            index += 1
    return total * repeat_count
