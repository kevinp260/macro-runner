"""GUI-independent desktop macro playback adapter.

All mouse/keyboard operations happen in the worker thread.  The UI sends
pause/stop/step commands through PlaybackGate, never from the worker itself.
"""
import threading
from macro_flow import has_smart_actions, iter_flow_steps, validate_flow, validate_start_selection
from macro_model import validate_action
from macro_playback import PlaybackGate, iter_execution_steps, progress_total
from macro_keys import HeldKeys
from macro_diagnostics import safe_error_code
from macro_vision import locate_image, check_condition, poll_until, watch_region_change
from dataclasses import asdict


class MacroExecutor:
    def __init__(self, actions, repeat_count, start_delay, on_progress, on_finished,
                 start_index=0, step_mode=False, automation=None,
                 on_diagnostic=None, on_failure_capture=None):
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
        self.on_diagnostic = on_diagnostic
        self.on_failure_capture = on_failure_capture
        self._action_indices = {id(a): i for i, a in enumerate(self.actions)}
        self._last_conditions = {}
        self._active_index = None

    def _emit(self, event, action=None, index=None, **details):
        """Emit metadata only; never include user-defined actions or text."""
        if self.on_diagnostic is None:
            return
        if index is None and action is not None:
            index = self._action_indices.get(id(action))
        values = {"event": event}
        if index is not None:
            values["index"] = index
            if 0 <= index < len(self.actions):
                values["kind"] = self.actions[index].kind
        values.update(details)
        try:
            self.on_diagnostic(values)
        except Exception:
            # Diagnostics must never interrupt actual automation.
            pass

    def start(self):
        if self.thread is not None:
            raise RuntimeError("Macro is already running.")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self._emit("stop_requested")
        self.gate.stop()

    def pause(self):
        self._emit("pause")
        self.gate.pause()

    def resume(self):
        self._emit("resume")
        self.gate.resume()

    def step(self):
        self.gate.step()
        self._emit("step")

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
        result = check_condition(action, self._pag().screenshot)
        # Record state transitions, not every polling frame.
        key = id(action)
        if self._last_conditions.get(key) != result:
            self._last_conditions[key] = result
            self._emit("condition", action=action, result=result)
        return result

    def _watch_region(self, action, baseline=None):
        # Watch only on the worker thread. Step mode can grant one watch cycle,
        # and Stop interrupts the polling gate immediately. Preserve the last
        # accepted screen image across nested action execution.
        self.gate.begin_action()
        try:
            result = watch_region_change(action, self._pag().screenshot, self.gate,
                                         baseline=baseline)
            self._emit("watch_trigger", action=action, result=True)
            return result
        finally:
            self.gate.end_action()

    def _poll_with_retries(self, action, probe):
        """Retry *only* the pre-input polling stage after a TimeoutError.

        Click Image is deliberately never retried after sending its click:
        an OS input exception could happen *after* the click took effect.
        """
        extras = action.retry_count if action.failure_policy == "retry" else 0
        for attempt in range(extras + 1):
            self.gate.wait(0)
            try:
                return probe()
            except TimeoutError:
                # Stop takes precedence, even when a timeout races with Stop.
                self.gate.wait(0)
                if attempt == extras:
                    raise
                self._emit(
                    "action_retry", action=action, attempt=attempt + 2,
                    max_attempts=extras + 1, error="TimeoutError")
                self.gate.wait(action.retry_delay)
        raise AssertionError("Retry count was not bounded.")

    def _execute_with_policy(self, action):
        try:
            self._execute(action)
        except Exception as exc:
            # Never suppress Stop, emergency mouse-corner fail-safe, or
            # unexpected cancellation, even when Skip was selected.
            if (self.gate.stopped.is_set() or str(exc) == "Stopped" or
                    type(exc).__name__ == "FailSafeException"):
                raise
            if action.failure_policy == "skip":
                self._emit("action_skipped", action=action,
                           error=safe_error_code(exc))
                return False
            raise
        return True

    def _execute(self, a):
        pag = self._pag()
        self.gate.wait(0)
        if a.kind == "click_image":
            match = self._poll_with_retries(
                a, lambda: poll_until(
                    a, lambda: locate_image(a, pag.screenshot), self.gate))
            self._emit("image_match", action=a, result=True)
            pag.click(match[0], match[1], button=a.button)
        elif a.kind == "wait_until":
            self._poll_with_retries(
                a, lambda: poll_until(
                    a, lambda: self._condition(a), self.gate))
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
                        self._active_index = idx
                        self._emit("action_start", index=idx, cycle=repeat + 1)
                        done += 1
                        self.on_progress(repeat + 1, self.repeat_count,
                                         idx, done, self.total)
                        if self._execute_with_policy(action):
                            self._emit("action_done", index=idx,
                                       cycle=repeat + 1)
                    finally:
                        self.gate.end_action()
            success, message = True, "Workflow completed."
        except Exception as exc:
            stopped = self.gate.stopped.is_set() or str(exc) == "Stopped"
            message = "Stopped." if stopped else str(exc)
            if not stopped:
                self._emit("action_error", index=self._active_index,
                           error=safe_error_code(exc))
                if self.on_failure_capture is not None:
                    try:
                        image = self._pag().screenshot()
                        self.on_failure_capture(image)
                    except Exception as capture_exc:
                        self._emit("screenshot_unavailable",
                                   error=safe_error_code(capture_exc))
        finally:
            if self.held:
                errors = self.held.release_all()
                if errors:
                    message += " Warning: unable to release some held keys."
            self.on_finished(success, message)
