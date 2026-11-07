"""GUI-independent desktop macro playback adapter.

All mouse/keyboard operations happen in the worker thread.  The UI sends
pause/stop/step commands through PlaybackGate, never from the worker itself.
"""
import threading
from macro_flow import has_smart_actions, iter_flow_steps, validate_flow, validate_start_selection
from macro_model import validate_action
from macro_playback import PlaybackGate, iter_execution_steps, progress_total
from macro_keys import HeldKeys
from macro_vision import locate_image, check_condition, poll_until, watch_region_change
from dataclasses import asdict


class MacroExecutor:
    def __init__(self, actions, repeat_count, start_delay, on_progress, on_finished,
                 start_index=0, step_mode=False, automation=None):
        self.actions = [validate_action(asdict(a)) for a in actions]
        validate_flow(self.actions)
        if not self.actions:
            raise ValueError("The workflow has no actions.")
        if not any(a.enabled and a.kind not in ("loop_start", "loop_end", "if_start",
                "if_end", "else", "until_start", "until_end", "watch_start", "watch_end") for a in self.actions):
            raise ValueError("The workflow has no enabled executable actions.")
        if not isinstance(repeat_count, int) or repeat_count < 1:
            raise ValueError("Repeat count must be positive.")
        if not isinstance(start_delay, (int, float)) or not 0 <= start_delay < float("inf"):
            raise ValueError("Start delay must be nonnegative and finite.")
        self.smart = has_smart_actions(self.actions)
        if self.smart:
            validate_start_selection(self.actions, start_index)
            self.total = None
        else:
            self.total = progress_total(self.actions, repeat_count, start_index)
        if self.total == 0:
            raise ValueError("No enabled actions at the selected position.")
        self.repeat_count = repeat_count
        self.start_delay = 0 if step_mode else start_delay
        self.start_index = start_index
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.gate = PlaybackGate()
        if step_mode:
            self.gate.pause()
        self.automation = automation  # lazy import for headless model tests
        self.thread = None
        self.held = None

    def start(self):
        if self.thread is not None:
            raise RuntimeError("Macro is already running.")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.gate.stop()

    def pause(self):
        self.gate.pause()

    def resume(self):
        self.gate.resume()

    def step(self):
        self.gate.step()

    def _pag(self):
        if self.automation is None:
            import pyautogui
            self.automation = pyautogui
        return self.automation

    def _condition(self, action):
        # Markers run between actions: do not block on Pause before the next
        # executable action can acquire its Step token.
        if self.gate.stopped.is_set():
            raise RuntimeError("Stopped")
        return check_condition(action, self._pag().screenshot)

    def _watch_region(self, action, baseline=None):
        # Watch only on the worker thread. Step mode can grant one watch cycle,
        # and Stop interrupts the polling gate immediately. Preserve the last
        # accepted screen image across nested action execution.
        self.gate.begin_action()
        try:
            return watch_region_change(action, self._pag().screenshot, self.gate,
                                       baseline=baseline)
        finally:
            self.gate.end_action()

    def _execute(self, a):
        pag = self._pag()
        self.gate.wait(0)
        if a.kind == "click_image":
            match = poll_until(a, lambda: locate_image(a, pag.screenshot), self.gate)
            pag.click(match[0], match[1], button=a.button)
        elif a.kind == "wait_until":
            poll_until(a, lambda: self._condition(a), self.gate)
        elif a.kind == "click":
            pag.moveTo(a.x, a.y, duration=0)
            for n in range(a.clicks):
                self.gate.wait(0)
                pag.click(button=a.button)
                if n + 1 < a.clicks:
                    self.gate.wait(a.interval)
        elif a.kind == "wait":
            self.gate.wait(a.seconds)
        elif a.kind == "key":
            if a.key_mode == "type":
                for character in a.keys:
                    self.gate.wait(0)
                    pag.write(character)
            else:
                names = [part.strip() for part in a.keys.split("+") if part.strip()]
                if len(names) == 1:
                    pag.press(names[0])
                else:
                    pag.hotkey(*names)
        elif a.kind == "key_down":
            self.held.press(a.keys.lower())
        elif a.kind == "key_up":
            self.held.release(a.keys.lower())
        elif a.kind == "move":
            pag.moveTo(a.x, a.y, duration=a.move_duration)
        elif a.kind == "scroll":
            pag.scroll(a.scroll_amount)
        elif a.kind == "drag":
            pag.moveTo(a.x, a.y, duration=0)
            pag.dragTo(a.to_x, a.to_y, duration=a.move_duration, button=a.button)

    def run(self):
        success, message = False, "Stopped."
        try:
            pag = self._pag()
            self.held = HeldKeys(pag.keyDown, pag.keyUp)
            remaining = self.start_delay
            while remaining > 0:
                chunk = min(.2, remaining)
                self.gate.wait(chunk)
                remaining -= chunk
            done = 0
            for repeat in range(self.repeat_count):
                start = self.start_index if repeat == 0 else 0
                iterator = (iter_flow_steps(self.actions, self._condition,
                            self.gate.stopped.is_set, start,
                            watch=self._watch_region) if self.smart
                            else iter_execution_steps(self.actions, start))
                for idx, action in iterator:
                    self.gate.begin_action()
                    try:
                        done += 1
                        self.on_progress(repeat + 1, self.repeat_count,
                                         idx, done, self.total)
                        self._execute(action)
                    finally:
                        self.gate.end_action()
            success, message = True, "Workflow completed."
        except Exception as exc:
            message = "Stopped." if str(exc) == "Stopped" else str(exc)
        finally:
            if self.held:
                errors = self.held.release_all()
                if errors:
                    message += " Warning: unable to release some held keys."
            self.on_finished(success, message)
