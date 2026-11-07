"""Wait for desktop window states without activating or injecting input.

Uses the existing Win32/X11 window identity rules. Absence of a window is
distinct from "hidden": hidden requires an actual enumerated, hidden window.
"""
import math

from macro_windows import WindowManager, WindowUnavailable, identify_target, validate_target


STATES = ("appears", "active", "hidden", "closed")
SOURCES = ("custom", "workflow")


def validate_window_wait(action):
    """Validate a window wait without requiring the window to exist yet."""
    if action.window_wait_state not in STATES:
        raise ValueError("Window state must be appears, active, hidden, or closed.")
    if action.window_wait_source not in SOURCES:
        raise ValueError("Window source must be custom or workflow.")
    for key in ("window_wait_title", "window_wait_class"):
        text = getattr(action, key)
        if not isinstance(text, str) or len(text) > 1024:
            raise ValueError("Window title/class must be text within 1024 characters.")
    for key in ("window_wait_handle", "window_wait_pid"):
        val = getattr(action, key)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise ValueError("Selected window handle/PID must be nonnegative integers.")
    if action.window_wait_source == "custom" and action.window_wait_handle:
        saved = {
            "handle": action.window_wait_handle,
            "pid": action.window_wait_pid,
            "title": action.window_wait_title,
            "class_name": action.window_wait_class,
            "relative": False,
            "activate": False,
        }
        validate_target(saved)
    if (isinstance(action.timeout, bool) or not isinstance(action.timeout, (int, float))
            or not math.isfinite(action.timeout) or not 0 <= action.timeout <= 86400):
        raise ValueError("Wait for window timeout must be 0–86400 seconds.")
    if (isinstance(action.poll_interval, bool) or
            not isinstance(action.poll_interval, (int, float)) or
            not math.isfinite(action.poll_interval) or
            not 0.1 <= action.poll_interval <= 60):
        raise ValueError("Window polling interval must be 0.1–60 seconds.")


def _find_window(action, available, workflow_target=None):
    """Match a selected instance when possible, otherwise exact title/class."""
    if action.window_wait_source == "workflow":
        if workflow_target is None:
            raise WindowUnavailable(
                "This window wait needs a workflow target. Choose a target window.")
        saved = validate_target(workflow_target)
    elif action.window_wait_handle:
        saved = {
            "handle": action.window_wait_handle, "pid": action.window_wait_pid,
            "title": action.window_wait_title, "class_name": action.window_wait_class,
            "relative": False, "activate": False,
        }
    else:
        matches = [window for window in available
                   if window.title == action.window_wait_title and
                   (not action.window_wait_class or
                    window.class_name == action.window_wait_class)]
        if len(matches) > 1:
            raise WindowUnavailable(
                "Multiple windows match the title/class. Pick a specific window.")
        return matches[0] if matches else None
    try:
        return identify_target(saved, available)
    except WindowUnavailable as exc:
        if str(exc).startswith("Target window was not found."):
            return None
        raise


def _state_reached(action, manager, workflow_target=None):
    """One read-only poll. Never activate a window or send desktop input."""
    windows = manager.all_windows()
    match = _find_window(action, windows, workflow_target)
    state = action.window_wait_state
    if state == "closed":
        return match is None
    if match is None:
        return False
    if state == "hidden":
        return bool(match.hidden or match.minimized)
    if state == "appears":
        return not (match.hidden or match.minimized)
    return not (match.hidden or match.minimized) and (
        manager.foreground_handle() == match.handle)


def wait_for_window(action, gate, *, workflow_target=None, manager=None):
    """Poll on active workflow time; Pause freezes timeout, Stop cancels.

    Timeout 0 means check once. No busy loop; each unsuccessful check is
    followed by a cancellable wait of at least 0.1 seconds.
    """
    validate_window_wait(action)
    if action.window_wait_source == "custom" and not action.window_wait_title.strip():
        raise WindowUnavailable("Choose a window or enter its exact title to wait for.")
    if action.window_wait_source == "workflow" and workflow_target is None:
        raise WindowUnavailable(
            "This window wait needs a workflow target. Choose a target window.")
    manager = manager or WindowManager()
    remaining = action.timeout
    while True:
        gate.wait(0)
        if _state_reached(action, manager, workflow_target):
            return
        if remaining <= 0:
            raise TimeoutError(
                f"Timed out waiting for the window to {action.window_wait_state}.")
        interval = min(action.poll_interval, remaining)
        gate.wait(interval)
        remaining -= interval
