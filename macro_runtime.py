"""GUI-independent desktop macro playback adapter.

All mouse/keyboard operations happen in the worker thread.  The UI sends
pause/stop/step commands through PlaybackGate, never from the worker itself.
"""
import math
import threading
from macro_flow import has_smart_actions, iter_flow_steps, validate_flow, validate_start_selection
from macro_model import validate_action
from macro_playback import PlaybackGate, iter_execution_steps, progress_total
from macro_keys import HeldKeys
from macro_diagnostics import safe_error_code
from macro_vision import (ConditionTimeout, locate_image, image_click_point,
                          check_condition, poll_until, watch_region_change)
from dataclasses import asdict
from macro_windows import WindowBinding, WindowUnavailable
from macro_clipboard import ClipboardUnavailable, paste_clipboard
from macro_launch import launch_target
from macro_window_wait import wait_for_window


class MacroExecutor:
    def __init__(self, actions, repeat_count, start_delay, on_progress, on_finished,
                 start_index=0, step_mode=False, automation=None,
                 on_diagnostic=None, on_failure_capture=None,
                 breakpoints=(), debug_gap=0.0,
                 window_target=None, window_manager=None,
                 clipboard=None):
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
        if isinstance(debug_gap, bool) or not isinstance(debug_gap, (int, float)) or (
                not math.isfinite(debug_gap) or not 0 <= debug_gap <= 5):
            raise ValueError("Debug gap must be between 0 and 5 seconds.")
        if any(isinstance(index, bool) or not isinstance(index, int) or
               index < 0 or index >= len(self.actions)
               for index in breakpoints):
            raise ValueError("Breakpoint action index is out of range.")
        self.breakpoints = frozenset(
            index for index in breakpoints
            if self.actions[index].enabled and self.actions[index].kind not in
            ("loop_start", "loop_end", "if_start", "if_end", "else",
             "until_start", "until_end", "watch_start", "watch_end"))
        self.debug_gap = float(debug_gap)
        self.window_binding = (WindowBinding(window_target, manager=window_manager)
                               if window_target is not None else None)
        self.clipboard = clipboard
        self.window_manager = (self.window_binding.manager
                               if self.window_binding is not None else window_manager)
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

    def _bound_action(self, action):
        """Resolve target again immediately before a screen/input operation."""
        if self.window_binding is None:
            return action
        info = self.window_binding.prepare(self.gate)
        bound = self.window_binding.transform(action, info)
        if (bound.kind in ("click_image", "wait_until", "if_start",
                           "until_start", "watch_start") and
                (bound.kind == "watch_start" or bound.condition_source == "image")
                and bound.region_x is not None and
                (bound.region_x < 0 or bound.region_y < 0)):
            raise WindowUnavailable(
                "Window screenshot region has a negative screen origin. "
                "Move the window onto a positive-coordinate display.")
        if (bound.kind in ("wait_until", "if_start", "until_start") and
                bound.condition_source == "pixel" and
                (bound.pixel_x < 0 or bound.pixel_y < 0)):
            raise WindowUnavailable(
                "Window pixel is on a negative-coordinate display, "
                "which this screenshot backend does not support.")
        return bound

    def _condition(self, action):
        # Markers run between actions: do not block on Pause before the next
        # executable action can acquire its Step token.
        if self.gate.stopped.is_set():
            raise RuntimeError("Stopped")
        bound = self._bound_action(action)
        result = check_condition(bound, self._pag().screenshot)
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
            bound = self._bound_action(action)
            screenshot = self._pag().screenshot
            if self.window_binding is not None:
                # Recheck foreground on every capture. In relative mode also
                # re-resolve the rectangle after each window move.
                def screenshot(region=None):
                    current = self._bound_action(action)
                    if self.window_binding.spec["relative"]:
                        region = (current.region_x, current.region_y,
                                  current.region_w, current.region_h)
                    return self._pag().screenshot(region=region)
            result = watch_region_change(bound, screenshot, self.gate,
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
            except ConditionTimeout:
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
                    isinstance(exc, WindowUnavailable) or
                    type(exc).__name__ == "FailSafeException"):
                raise
            if action.failure_policy == "skip":
                self._emit("action_skipped", action=action,
                           error=safe_error_code(exc))
                return False
            raise
        return True

    def _execute(self, a):
        # Opening apps/files/URLs and setting clipboard text do not need
        # PyAutoGUI or a configured global input session.
        pag = self._pag() if a.kind not in (
            "wait", "clipboard_set", "launch", "wait_window") else None
        self.gate.wait(0)
        # Set clipboard does not send input, so it must not steal focus.
        bound = self._bound_action(a) if a.kind not in (
            "wait", "clipboard_set", "launch", "wait_window") else a
        if a.kind == "click_image":
            last_region = None

            def find():
                nonlocal last_region
                current = self._bound_action(a)
                last_region = (current.region_x, current.region_y,
                               current.region_w, current.region_h)
                return locate_image(current, pag.screenshot)

            match = self._poll_with_retries(
                a, lambda: poll_until(a, find, self.gate))
            self._emit("image_match", action=a, result=True)
            client_rect = None
            if self.window_binding is not None:
                info = self.window_binding.prepare(self.gate)
                current = self.window_binding.transform(a, info)
                if (current.region_x, current.region_y,
                        current.region_w, current.region_h) != last_region:
                    raise WindowUnavailable(
                        "Target window moved after image matching. Run again.")
                if self.window_binding.spec["relative"]:
                    client_rect = (info.x, info.y, info.width, info.height)
            # The detector returns a physical global center, including any
            # screenshot-region origin. Never add that origin twice.
            screen_size = pag.size() if hasattr(pag, "size") else None
            x, y = image_click_point(
                a, match, screen_size=screen_size, client_rect=client_rect)
            # Stop during matching, verification or Pause must not inject input.
            self.gate.wait(0)
            pag.click(x, y, button=a.button)
        elif a.kind == "wait_until":
            self._poll_with_retries(
                a, lambda: poll_until(
                    a, lambda: self._condition(a), self.gate))
        elif a.kind == "click":
            pag.moveTo(bound.x, bound.y, duration=0)
            for n in range(a.clicks):
                self.gate.wait(0)
                if self.window_binding is not None:
                    latest = self._bound_action(a)
                    # Move again if the target changed position during a
                    # multiple-click interval: never click the old screen spot.
                    if (latest.x, latest.y) != (bound.x, bound.y):
                        pag.moveTo(latest.x, latest.y, duration=0)
                        bound = latest
                pag.click(button=a.button)
                if n + 1 < a.clicks:
                    self.gate.wait(a.interval)
        elif a.kind == "wait":
            self.gate.wait(a.seconds)
        elif a.kind == "wait_window":
            wait_for_window(
                a, self.gate,
                workflow_target=(self.window_binding.spec
                                 if self.window_binding is not None else None),
                manager=self.window_manager)
        elif a.kind == "launch":
            # OS-native app/file/browser open only. No window activation or
            # shell; Stop before dispatch prevents launching.
            self.gate.wait(0)
            launch_target(a)
        elif a.kind == "clipboard_set":
            if self.clipboard is None:
                raise ClipboardUnavailable("Desktop clipboard service is unavailable.")
            self.clipboard.set_text(a.clipboard_text, gate=self.gate)
        elif a.kind == "clipboard_paste":
            if self.clipboard is None:
                raise ClipboardUnavailable("Desktop clipboard service is unavailable.")
            paste_clipboard(
                self.clipboard, pag, self.gate,
                text=a.clipboard_text, restore=a.clipboard_restore,
                prepare_focus=(lambda: self._bound_action(a))
                if self.window_binding is not None else None)
        elif a.kind == "key":
            if a.key_mode == "type":
                for character in a.keys:
                    self.gate.wait(0)
                    if self.window_binding is not None:
                        self._bound_action(a)
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
            pag.moveTo(bound.x, bound.y, duration=a.move_duration)
        elif a.kind == "scroll":
            if self.window_binding is not None:
                info = self.window_binding.prepare(self.gate)
                pag.moveTo(info.x + info.width // 2,
                           info.y + info.height // 2, duration=0)
            pag.scroll(a.scroll_amount)
        elif a.kind == "drag":
            pag.moveTo(bound.x, bound.y, duration=0)
            if self.window_binding is not None:
                latest = self._bound_action(a)
                if ((latest.x, latest.y, latest.to_x, latest.to_y) !=
                        (bound.x, bound.y, bound.to_x, bound.to_y)):
                    raise WindowUnavailable(
                        "Target window moved after drag preparation. Run again.")
            pag.dragTo(bound.to_x, bound.to_y,
                       duration=a.move_duration, button=a.button)

    def run(self):
        success, message = False, "Stopped."
        try:
            # Launch-only workflows can work without an available display
            # automation backend; input, screen watchers and conditions still
            # load PyAutoGUI as before.
            no_desktop = {"wait", "clipboard_set", "launch", "wait_window", "loop_start",
                          "loop_end", "else", "if_end", "until_end", "watch_end"}
            if any(a.enabled and a.kind not in no_desktop for a in self.actions):
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
                    # The breakpoint is consumed for this *occurrence* only.
                    # Resume/Step continues this action; the next loop visit
                    # can break again. Disabled leaves never reach this point.
                    if idx in self.breakpoints:
                        # Preserve a Step token queued before the worker reaches
                        # this breakpoint (notably the first Step at startup).
                        if not self.gate.paused:
                            self.gate.pause()
                        self._emit("breakpoint", index=idx, cycle=repeat + 1)
                    self.gate.begin_action()
                    try:
                        # A debugging-only gap before the next action, inside
                        # the gate's Step token so Pause/Stop remain responsive.
                        if done and self.debug_gap:
                            self.gate.wait(self.debug_gap)
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
