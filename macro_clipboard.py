"""Clipboard text operations and best-effort cleanup, without UI dependencies."""
from dataclasses import dataclass


class ClipboardUnavailable(RuntimeError):
    """Clipboard is unavailable; messages must never contain clipboard contents."""


@dataclass(frozen=True)
class ClipboardState:
    kind: str          # "text", "empty", or "other" (image/rich formats)
    text: str = ""


def paste_clipboard(clipboard, automation, gate, *, text=None,
                    restore=True, prepare_focus=None):
    """Paste current text, or temporary text with conditional text restoration.

    Restores an earlier text/empty clipboard only if its contents still match
    the text this action supplied, to avoid clobbering another app's edits.
    Never attempts to copy/restore non-text MIME data.
    """
    gate.wait(0)
    previous = None
    if text is None:
        existing = clipboard.read(gate=gate)
        if existing.kind != "text" or not existing.text:
            raise ClipboardUnavailable("Clipboard has no text to paste.")
    else:
        if not text:
            raise ValueError("Paste text cannot be empty; use Set clipboard to clear it.")
        if restore:
            previous = clipboard.read(gate=gate)
            if previous.kind == "other":
                raise ClipboardUnavailable(
                    "Cannot restore non-text clipboard data. "
                    "Disable restoration to replace the clipboard explicitly.")
        clipboard.set_text(text, gate=gate)

    try:
        if prepare_focus is not None:
            prepare_focus()
        gate.wait(0)
        automation.hotkey("ctrl", "v")
        # The target may consume the clipboard after the shortcut returns.
        # Allow a brief cancellable interval before best-effort restoration.
        gate.wait(0.2)
    finally:
        if text is not None and restore:
            # Cleanup is attempted even after Stop or failure. It is not
            # governed by Pause/Stop, but never overwrites a changed clipboard.
            current = clipboard.read(cleanup=True)
            if current.kind == "text" and current.text == text:
                if previous.kind == "text":
                    clipboard.set_text(previous.text, cleanup=True)
                else:
                    clipboard.clear(cleanup=True)
