"""One private, atomic crash-recovery snapshot per editor installation.

The recovery snapshot is never a user workflow file. It contains the complete
macro (including typed text and image paths) and must stay local/private.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Optional

from macro_model import parse_document, serialize_document

MAX_RECOVERY_BYTES = 10_000_000
RECOVERY_SCHEMA = 1


@dataclass(frozen=True)
class RecoverySnapshot:
    actions: list
    repeat_count: int
    start_delay: float
    source_file: Optional[str]
    saved_at: str
    window_target: Optional[dict] = None


def atomic_json_write(path, payload, max_bytes=None):
    """Write valid UTF-8 JSON via an adjacent private temp file and os.replace."""
    path = Path(path)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if max_bytes is not None and len(encoded) > max_bytes:
        raise ValueError("Workflow is too large for local recovery (10 MB limit).")
    temporary = None
    try:
        # mkstemp creates a private file (0600 on POSIX), on the same volume.
        fd, temporary = tempfile.mkstemp(prefix=".macro-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


class RecoveryStore:
    def __init__(self, path):
        self.path = Path(path)

    def write(self, actions, repeat_count, start_delay, source_file=None,
              window_target=None):
        document = serialize_document(actions, repeat_count, start_delay,
                                      window_target)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self.path, {
            "schema": RECOVERY_SCHEMA,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_file": str(source_file) if source_file else None,
            "document": document,
        }, max_bytes=MAX_RECOVERY_BYTES)

    def read(self):
        if not self.path.exists():
            return None
        if self.path.stat().st_size > MAX_RECOVERY_BYTES:
            raise ValueError("Recovery snapshot exceeds the 10 MB limit.")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("Recovery snapshot is unreadable or invalid.") from exc
        if not isinstance(data, dict) or data.get("schema") != RECOVERY_SCHEMA:
            raise ValueError("Unrecognized recovery snapshot version.")
        source = data.get("source_file")
        saved_at = data.get("saved_at")
        if (source is not None and (not isinstance(source, str) or len(source) > 4096)
                or not isinstance(saved_at, str) or len(saved_at) > 64):
            raise ValueError("Recovery snapshot has invalid metadata.")
        try:
            datetime.fromisoformat(saved_at)
            actions, settings = parse_document(data["document"])
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise ValueError("Recovery snapshot contains an invalid workflow.") from exc
        if settings is None:
            # Existing action-list macros remain readable when wrapped in a
            # recovery envelope, without migrating user documents.
            settings = {"repeat_count": 1, "start_delay": 3.0}
        return RecoverySnapshot(actions, settings["repeat_count"],
                                settings["start_delay"], source, saved_at,
                                settings.get("window_target"))

    def clear(self):
        self.path.unlink(missing_ok=True)
