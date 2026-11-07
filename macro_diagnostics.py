"""Bounded, local, privacy-conscious execution diagnostics.

Never persist action parameters, typed text, clipboard contents, image paths or
raw exception messages. In particular, action names are user-provided and are
intentionally omitted. Screenshot capture is off unless explicitly enabled.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import tempfile
import time
import uuid

from macro_flow import OPENERS, CLOSERS

MAX_RUNS = 40
MAX_EVENTS = 250
MAX_JSON_BYTES = 3_000_000
EVENT_TYPES = frozenset({
    "action_start", "action_done", "action_error", "condition",
    "image_match", "watch_trigger", "pause", "resume", "step",
    "stop_requested", "screenshot_unavailable", "action_retry",
    "action_skipped", "breakpoint",
})
ERROR_CODES = {
    "TimeoutError": "Timed out waiting for a condition or image",
    "PermissionError": "Permission denied by the operating system",
    "FileNotFoundError": "A required file could not be found",
    "OSError": "Desktop capture or file I/O failed",
    "ValueError": "An invalid input or image caused an error",
    "RuntimeError": "The automation backend reported an error",
    "Exception": "An unexpected execution error occurred",
}
IDENT = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
CAPTURE_NAME = re.compile(r"^[a-f0-9]{32}\.jpg$")


def safe_error_code(error):
    """Only store known error categories, never raw exception text."""
    if isinstance(error, TimeoutError):
        return "TimeoutError"
    if isinstance(error, str):
        label = error
    else:
        label = type(error).__name__
    return label if label in ERROR_CODES else "Exception"


def action_paths(actions):
    """Build display-only action breadcrumbs from *types*, never user labels."""
    stack = []  # (group type, in_else_branch)
    paths = []

    def context():
        result = []
        for kind, in_else in stack:
            result.append(kind)
            if in_else:
                result.append("else")
        return result

    for action in actions:
        kind = action.kind
        if kind in CLOSERS:
            paths.append(context() + [kind])
            if stack:
                stack.pop()
        elif kind == "else":
            if stack and stack[-1][0] == "if_start":
                stack[-1] = ("if_start", True)
            paths.append(context())
        elif kind in OPENERS:
            paths.append(context() + [kind])
            stack.append((kind, False))
        else:
            paths.append(context() + [kind])
    return paths


def safe_event(raw, elapsed=0.0):
    """Enforce a strict allowlist at the persistence boundary."""
    event_type = raw.get("event")
    if event_type not in EVENT_TYPES:
        return None
    result = {"event": event_type, "at_s": round(max(0, float(elapsed)), 3)}
    for name in ("index", "cycle", "step", "attempt", "max_attempts"):
        value = raw.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000:
            result[name] = value
    kind = raw.get("kind")
    if isinstance(kind, str) and IDENT.fullmatch(kind):
        result["kind"] = kind
    path = raw.get("path")
    if isinstance(path, (list, tuple)) and len(path) <= 24 and all(
        isinstance(x, str) and IDENT.fullmatch(x) for x in path
    ):
        result["path"] = list(path)
    if raw.get("result") in (True, False):
        result["result"] = bool(raw["result"])
    code = raw.get("error")
    if code:
        result["error"] = safe_error_code(code)
    return result


class RunSession:
    def __init__(self, actions, mode="full", repeat_count=1, clock=None):
        self.clock = clock or time.monotonic
        self.started_clock = self.clock()
        self.id = uuid.uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.mode = mode if mode in ("full", "selected", "step") else "full"
        self.repeat_count = int(repeat_count)
        self.action_count = len(actions)
        self.paths = action_paths(actions)
        self.events = []
        self.dropped_events = 0
        self.completed_actions = 0
        self.skipped_actions = 0
        self.last_error = None

    def add(self, event):
        values = dict(event)
        i = values.get("index")
        if isinstance(i, int) and 0 <= i < len(self.paths):
            values["path"] = self.paths[i]
        clean = safe_event(values, self.clock() - self.started_clock)
        if clean is None:
            return
        if clean["event"] == "action_done":
            self.completed_actions += 1
        if clean["event"] == "action_skipped":
            self.skipped_actions += 1
        if clean["event"] == "action_error":
            self.last_error = clean.get("error", "Exception")
        if len(self.events) == MAX_EVENTS:
            self.events.pop(0)
            self.dropped_events += 1
        self.events.append(clean)

    def finish(self, status, screenshot=None):
        if status not in ("completed", "stopped", "error"):
            raise ValueError("Invalid run outcome.")
        ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = {
            "id": self.id, "started_at": self.started_at,
            "ended_at": ended_at,
            "duration_s": round(max(0.0, self.clock() - self.started_clock), 3),
            "status": status,
            "mode": self.mode,
            "repeat_count": self.repeat_count,
            "action_count": self.action_count,
            "completed_actions": self.completed_actions,
            "skipped_actions": self.skipped_actions,
            "events": self.events,
            "dropped_events": self.dropped_events,
        }
        if status == "error":
            record["error_code"] = self.last_error or "Exception"
        return record


class RunHistoryStore:
    """Atomic JSON history with bounded runs and optional failure screenshots."""

    def __init__(self, history_path, max_runs=MAX_RUNS, max_screenshots=5):
        self.path = Path(history_path)
        self.capture_dir = self.path.parent / "failure-captures"
        self.max_runs = max(1, min(100, int(max_runs)))
        self.max_screenshots = max(0, min(20, int(max_screenshots)))
        self.runs = self._read()
        self._prune()  # Discard orphaned private screenshots on startup.

    def _read(self):
        try:
            if not self.path.is_file() or self.path.stat().st_size > MAX_JSON_BYTES:
                return []
            content = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("schema") != 1:
                return []
            runs = content.get("runs", [])
            if not isinstance(runs, list):
                return []
            # Old or manually edited files are treated as untrusted; load only
            # recognized metadata, and re-sanitize event records.
            cleaned = []
            for run in runs[-self.max_runs:]:
                if not isinstance(run, dict):
                    continue
                status = run.get("status")
                if status not in ("completed", "stopped", "error"):
                    continue
                rec = {
                    "id": str(run.get("id", ""))[:32],
                    "started_at": str(run.get("started_at", ""))[:32],
                    "ended_at": str(run.get("ended_at", ""))[:32],
                    "status": status,
                    "duration_s": float(run.get("duration_s", 0)),
                    "mode": str(run.get("mode", "full"))[:12],
                    "repeat_count": int(run.get("repeat_count", 1)),
                    "action_count": int(run.get("action_count", 0)),
                    "completed_actions": int(run.get("completed_actions", 0)),
                    "skipped_actions": int(run.get("skipped_actions", 0)),
                    "dropped_events": int(run.get("dropped_events", 0)),
                    "events": [],
                }
                for evt in run.get("events", [])[-MAX_EVENTS:]:
                    if isinstance(evt, dict):
                        val = safe_event(evt, evt.get("at_s", 0))
                        if val is not None:
                            rec["events"].append(val)
                code = run.get("error_code")
                if code:
                    rec["error_code"] = safe_error_code(code)
                filename = run.get("screenshot")
                if isinstance(filename, str) and CAPTURE_NAME.fullmatch(filename):
                    rec["screenshot"] = filename
                cleaned.append(rec)
            return cleaned
        except (OSError, ValueError, TypeError, OverflowError, KeyError):
            return []

    def _capture_files(self):
        if not self.capture_dir.exists():
            return []
        return [p for p in self.capture_dir.iterdir()
                if p.is_file() and CAPTURE_NAME.fullmatch(p.name)]

    def _prune(self, keep_orphans=True):
        self.runs = self.runs[-self.max_runs:]
        attached = [r["screenshot"] for r in self.runs
                    if "screenshot" in r and (self.capture_dir / r["screenshot"]).is_file()]
        retain = set(attached[-self.max_screenshots:] if self.max_screenshots else [])
        for record in self.runs:
            if record.get("screenshot") not in retain:
                record.pop("screenshot", None)
        if keep_orphans:
            for file in self._capture_files():
                if file.name not in retain:
                    try:
                        file.unlink()
                    except OSError:
                        pass

    def add(self, record, capture=None):
        """Persist a completed run. Images are only saved when caller opts in."""
        allowed = ("id", "started_at", "ended_at", "duration_s",
                   "status", "mode", "repeat_count", "action_count",
                   "completed_actions", "skipped_actions",
                   "dropped_events", "error_code")
        clean = {key: record[key] for key in allowed if key in record}
        clean["events"] = [
            sanitized
            for value in record.get("events", [])[-MAX_EVENTS:]
            if isinstance(value, dict)
            for sanitized in [safe_event(value, value.get("at_s", 0))]
            if sanitized is not None
        ]
        if clean.get("error_code"):
            clean["error_code"] = safe_error_code(clean["error_code"])
        if capture is not None and clean.get("status") == "error" and self.max_screenshots:
            try:
                clean["screenshot"] = self._save_capture(capture)
            except (OSError, ValueError) as exc:
                # A denied screenshot must not discard the actual run log.
                failure = safe_event({
                    "event": "screenshot_unavailable",
                    "error": safe_error_code(exc),
                }, clean.get("duration_s", 0))
                if failure is not None:
                    clean["events"].append(failure)
                    clean["events"] = clean["events"][-MAX_EVENTS:]
        self.runs.append(clean)
        self._prune()
        self._write()

    def _save_capture(self, capture):
        """Save a reduced JPEG, not a full-resolution desktop image."""
        from PIL import Image
        self.capture_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = uuid.uuid4().hex + ".jpg"
        path = self.capture_dir / name
        temp = self.capture_dir / (name + ".tmp")
        image = capture.convert("RGB")
        image.thumbnail((1280, 800), Image.Resampling.LANCZOS)
        try:
            image.save(temp, format="JPEG", quality=70, optimize=True)
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return name

    def _write(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".history-", suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump({"schema": 1, "runs": self.runs}, stream, indent=2)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def clear(self):
        self.runs.clear()
        self._prune()
        self._write()

    def set_max_screenshots(self, number):
        self.max_screenshots = max(0, min(20, int(number)))
        self._prune()
        self._write()

    def export_safe(self, path):
        """Export no actual screenshots, action inputs, or absolute paths."""
        export = {"schema": 1, "notice": "No action input data or screenshots included.",
                  "runs": [{k: v for k, v in r.items() if k != "screenshot"}
                           for r in self.runs]}
        Path(path).write_text(json.dumps(export, indent=2), encoding="utf-8")
        return len(export["runs"])
