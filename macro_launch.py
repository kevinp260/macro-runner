"""OS-native launch/open actions without invoking a command shell.

Paths are explicit, absolute local paths. Application arguments are one argv
element per line; no shell quoting, escaping or interpolation takes place.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


class LaunchError(ValueError):
    """Invalid configuration or an unavailable OS launcher."""


def _local_path(text, *, purpose):
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise LaunchError(f"{purpose} needs an absolute local path. Use Browse…")
    if not path.is_file():
        raise LaunchError(f"{purpose} does not exist or is not a file: {path}")
    return path


def validate_launch(action, *, check_files=False, platform_name=None):
    """Validate a launch action before doing anything with the desktop."""
    platform_name = platform_name or sys.platform
    if action.launch_mode not in ("application", "file", "url"):
        raise LaunchError("Choose Application, File, or URL.")
    target, arguments = action.launch_target, action.launch_args
    if not isinstance(target, str) or not isinstance(arguments, str):
        raise LaunchError("Launch target and arguments must be text.")
    if not target or target != target.strip() or any(
            c in target for c in ("\x00", "\r", "\n", "\t")):
        raise LaunchError("Enter a target without leading/trailing whitespace or control characters.")
    if "\x00" in arguments or "\r" in arguments:
        raise LaunchError("Arguments cannot contain NUL or carriage-return characters.")
    if action.launch_mode == "url":
        if arguments.strip():
            raise LaunchError("URL actions do not take application arguments.")
        try:
            parsed = urlsplit(target)
            host = parsed.hostname
            _ = parsed.port  # Reject invalid port ranges and port syntax.
        except ValueError as exc:
            raise LaunchError("The HTTP(S) URL is malformed.") from exc
        if (parsed.scheme not in ("http", "https") or not host or
                parsed.username is not None or parsed.password is not None or
                any(ord(c) < 33 or ord(c) == 127 for c in target)):
            raise LaunchError("Enter an HTTP(S) URL without embedded credentials.")
        return target
    if action.launch_mode == "file" and arguments.strip():
        raise LaunchError("Open File uses the system default app and cannot take arguments.")
    # Reject relative executable/file paths even before checking the filesystem.
    path = Path(target).expanduser()
    if not path.is_absolute():
        raise LaunchError("Choose an absolute local path (Browse…).")
    if not check_files:
        return path
    path = _local_path(target, purpose="Application" if action.launch_mode == "application" else "File")
    if action.launch_mode == "application":
        if platform_name == "win32":
            if path.suffix.lower() not in (".exe", ".com"):
                raise LaunchError("On Windows, choose an .exe or .com executable.")
        elif not os.access(path, os.X_OK):
            raise LaunchError(f"Application is not executable: {path}")
    elif not os.access(path, os.R_OK):
        raise LaunchError(f"File is not readable: {path}")
    return path


def arguments_list(text):
    """Every nonblank line is exactly one argument; quotes are literal."""
    return [line for line in text.split("\n") if line]


def launch_target(action, *, platform_name=None, popen=None, startfile=None,
                  find_command=None):
    """Request a launch; never wait for or control the lifetime of the new app.

    A successful return means OS launch accepted the request, not that a
    browser/document was displayed or the child eventually exited cleanly.
    """
    platform_name = platform_name or sys.platform
    target = validate_launch(action, check_files=True, platform_name=platform_name)
    popen = popen or subprocess.Popen
    find_command = find_command or shutil.which
    if platform_name == "win32":
        startfile = startfile or getattr(os, "startfile", None)
        if action.launch_mode in ("file", "url"):
            if startfile is None:
                raise LaunchError("Windows default-file opener is unavailable.")
            try:
                startfile(str(target))
            except OSError as exc:
                raise LaunchError(f"Windows could not open the {action.launch_mode}: {exc.strerror or type(exc).__name__}") from None
            return
    elif platform_name.startswith("linux"):
        if action.launch_mode in ("file", "url"):
            opener = find_command("xdg-open")
            if not opener:
                raise LaunchError("xdg-open is unavailable; install xdg-utils and configure a default application.")
            command = [opener, str(target)]
        else:
            command = [str(target), *arguments_list(action.launch_args)]
    else:
        raise LaunchError("Open Application/File/URL supports Windows and Linux only.")

    if platform_name == "win32":
        command = [str(target), *arguments_list(action.launch_args)]
    try:
        # No shell=True, no string command, no terminal requirement. Avoid
        # retaining pipes or leaking launched output into MacroRunner logs.
        child = popen(command, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      shell=False)
        # For OS openers, catch *immediate* failure when no association exists.
        # Do not wait for the application process itself to exit.
        if action.launch_mode != "application" and child.poll() not in (None, 0):
            raise LaunchError(
                "The OS could not open this file or URL. "
                "Check its default application and desktop permissions.")
    except OSError as exc:
        if isinstance(exc, PermissionError):
            raise LaunchError("Permission denied while launching the selected application or opener.") from None
        if isinstance(exc, FileNotFoundError):
            raise LaunchError("Executable or operating-system opener was not found.") from None
        raise LaunchError(f"OS launch failed: {exc.strerror or type(exc).__name__}") from None
