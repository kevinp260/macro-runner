import threading
import time
import json
import os
import ctypes, sys
import queue
from dataclasses import asdict
from typing import List, Optional

from macro_model import Action, loop_spans, parse_document, serialize_document, validate_action
from macro_flow import CONTROL, has_smart_actions, iter_flow_steps, validate_flow, validate_start_selection
from macro_vision import locate_image, check_condition, poll_until
from macro_playback import PlaybackGate, iter_execution_steps, progress_total

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# pip install pyautogui pillow pynput
import pyautogui as pag
from pynput import mouse, keyboard

# ---------- single instance (mutex) ----------
def _single_instance_mutex():
    m = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\MacroRunnerMutex")
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        try:
            from tkinter import messagebox
            messagebox.showerror("Already running", "MacroRunner is already running.")
        except Exception:
            pass
        sys.exit(0)
if sys.platform == "win32":
    _single_instance_mutex()


def resource_path(rel):
    try:
        base = sys._MEIPASS  # set by PyInstaller at runtime
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, rel)


# ---------- PyAutoGUI globals ----------
pag.PAUSE = 0.05
pag.FAILSAFE = True  # move mouse to top-left corner to abort

class MacroRunnerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Macro Runner (Mouse/Keyboard Automator)")
        self.geometry("850x580")
        self.minsize(850, 580)

        self.actions: List[Action] = []
        self.run_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.playback = PlaybackGate(self.stop_flag)
        self._progress_index = None
        self._progress_total = 0
        self.events = queue.Queue()
        self._run_active = False
        self._global_hotkeys = None
        self.global_hotkeys_available = False
        self.editor_buttons = []
        self._record_pending = False
        self._record_after_id = None
        self._record_token = 0
        self._record_min_wait = 0.3
        self._record_repeats = 1
        self._record_insert_waits = True

        # Recording state
        self.is_recording = False
        self.mouse_listener: Optional[mouse.Listener] = None
        self.last_record_ts: Optional[float] = None

        self._build_ui()
        self._start_global_hotkeys()
        self.after(50, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        # rows: 0=top bar, 1=main split, 2=status bar
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)

        # Top: Run controls
        top = ttk.Frame(self, padding=(12, 10))
        top.grid(row=0, column=0, sticky="ew")
        for i in range(12):
            top.columnconfigure(i, weight=0)
        top.columnconfigure(11, weight=1)

        ttk.Label(top, text="Repeat count (whole sequence):").grid(row=0, column=0, sticky="w")
        self.repeat_var = tk.IntVar(value=1)
        ttk.Entry(top, width=8, textvariable=self.repeat_var).grid(row=0, column=1, padx=(6, 16))

        ttk.Label(top, text="Start delay (s):").grid(row=0, column=2, sticky="w")
        self.start_delay_var = tk.DoubleVar(value=3.0)
        ttk.Entry(top, width=8, textvariable=self.start_delay_var).grid(row=0, column=3, padx=(6, 16))

        self.btn_run = ttk.Button(top, text="Run", command=self.start_run)
        self.btn_run.grid(row=0, column=4, padx=4)

        self.btn_pause = ttk.Button(top, text="Pause", command=self.toggle_pause, state="disabled")
        self.btn_pause.grid(row=0, column=5, padx=4)
        self.btn_stop = ttk.Button(top, text="Stop", command=self.request_stop, state="disabled")
        self.btn_stop.grid(row=0, column=6, padx=4)

        ttk.Label(top, text="Debug:").grid(row=1, column=0, sticky="e", pady=(7, 0))
        self.btn_from_selected = ttk.Button(top, text="Run from Selected", command=self.run_from_selected)
        self.btn_from_selected.grid(row=1, column=1, columnspan=2, sticky="w", pady=(7, 0))
        self.btn_step = ttk.Button(top, text="Step", command=self.step_action)
        self.btn_step.grid(row=1, column=3, sticky="w", pady=(7, 0))
        ttk.Label(top, text="Step executes one action at a time").grid(
            row=1, column=4, columnspan=5, sticky="w", padx=(8, 0), pady=(7, 0)
        )

        ttk.Button(top, text="Save", command=self.save_sequence).grid(row=0, column=7, padx=4)
        ttk.Button(top, text="Load", command=self.load_sequence).grid(row=0, column=8, padx=4)

        # Menu (for shortcuts help)
        menubar = tk.Menu(self)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Keyboard Shortcuts…", command=self._show_shortcuts_dialog)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.config(menu=menubar)

        # Main split
        split = ttk.Frame(self, padding=(12, 10))
        split.grid(row=1, column=0, sticky="nsew")
        split.columnconfigure(0, weight=1)
        split.columnconfigure(1, weight=0)
        split.rowconfigure(0, weight=1)
        split.rowconfigure(1, weight=0)

        # Left: listbox + list controls
        left = ttk.Frame(split)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        actions_header = ttk.Frame(left)
        actions_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        actions_header.columnconfigure(0, weight=1)
        ttk.Label(actions_header, text="Actions (double-click to edit)").grid(
            row=0, column=0, sticky="w"
        )
        self._editor_button(actions_header, text="Edit…",
                            command=self.edit_action_selected).grid(
            row=0, column=1, padx=(4, 0)
        )
        self._editor_button(actions_header, text="Enable/Disable",
                            command=self.toggle_action_enabled).grid(
            row=0, column=2, padx=(4, 0)
        )

        self.lst = tk.Listbox(left, height=20, activestyle="dotbox")
        self.lst.grid(row=1, column=0, sticky="nsew")
        self.lst.bind("<<ListboxSelect>>", self.on_select)
        self.lst.bind("<Double-Button-1>", self._double_click_action)

        # Right: tabs
        right = ttk.Notebook(split)
        right.grid(row=0, column=1, sticky="ns")

        self._build_click_tab(right)  # includes Recording (moved here)
        self._build_wait_tab(right)
        self._build_key_tab(right)
        self._build_move_tab(right)
        self._build_scroll_tab(right)
        self._build_drag_tab(right)
        self._build_loop_tab(right)
        self._build_vision_tab(right)

        # Bottom: action bar (fixed-width buttons, spans full window)
        bottom = ttk.Frame(self, padding=(12, 8))
        bottom.grid(row=2, column=0, sticky="ew")

        btns = ttk.Frame(bottom)
        btns.grid(row=0, column=0, sticky="ew")

        # columns 0..6 = buttons, 7 = spacer to absorb extra width
        for i in range(7):
            btns.columnconfigure(i, weight=0)
        btns.columnconfigure(7, weight=1)

        BW = 14  # fixed width in text units
        self._editor_button(btns, text="▲ Up",         width=BW, command=lambda: self.move_item(-1)).grid(row=0, column=0, padx=2, sticky="w")
        self._editor_button(btns, text="▼ Down",       width=BW, command=lambda: self.move_item(1)).grid(row=0, column=1, padx=2, sticky="w")
        self._editor_button(btns, text="Delete",       width=BW, command=self.delete_item).grid(row=0, column=2, padx=2, sticky="w")
        self._editor_button(btns, text="Duplicate",    width=BW, command=self.duplicate_item).grid(row=0, column=3, padx=2, sticky="w")
        self._editor_button(btns, text="Clear",        width=BW, command=self.clear_items).grid(row=0, column=4, padx=2, sticky="w")
        self._editor_button(btns, text="Edit Repeat…", width=BW, command=self.edit_repeat_selected).grid(row=0, column=5, padx=2, sticky="w")
        self._editor_button(btns, text="Edit Name…",   width=BW, command=self.edit_name_selected).grid(row=0, column=6, padx=2, sticky="w")
        # spacer at col 7
        ttk.Label(btns, text="").grid(row=0, column=7, sticky="ew")

        # Status bar (shortcuts + safety tip)
        status = ttk.Frame(self, padding=(12, 6))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        IS_MAC = sys.platform == "darwin"
        def acc(s: str) -> str:
            return s.replace("Ctrl", "⌘").replace("Alt", "⌥").replace("Shift", "⇧") if IS_MAC else s

        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.progress_var).grid(row=0, column=0, sticky="w", padx=(0, 8))

        # shortcuts_text = f"Shortcuts: F5 Run, Esc Stop, Del Delete, {acc('Ctrl+Shift+D')} Duplicate, {acc('Ctrl+↑/↓')} Move, {acc('Ctrl+E')} Edit Repeat, {acc('Ctrl+S')} Save, {acc('Ctrl+O')} Load, {acc('Ctrl+R')} Record"
        # ttk.Label(status, text=shortcuts_text, foreground="#666").grid(row=0, column=0, sticky="w")
        ttk.Label(status, text="Tip: Move mouse to TOP-LEFT corner to abort while running.", foreground="#0a7").grid(row=0, column=1, sticky="e", padx=(8,0))

        # Bind keyboard shortcuts last (widgets exist now)
        self._bind_shortcuts()

        def _lock_right_width():
            right.update_idletasks()
            split.columnconfigure(1, minsize=right.winfo_reqwidth())

        self.after(0, _lock_right_width)

    def _editor_button(self, parent, **kwargs):
        button = ttk.Button(parent, **kwargs)
        self.editor_buttons.append(button)
        return button

    def _set_editing_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in self.editor_buttons:
            button.config(state=state)

    def _editing_locked(self):
        return self._run_active or self.is_recording or self._record_pending

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "click":
                    _, x, y, button, timestamp, token = event
                    if self.is_recording and token == self._record_token:
                        self._handle_recorded_click(x, y, button, timestamp)
                elif kind == "global_pause":
                    self.toggle_pause()
                elif kind == "global_stop":
                    if self._run_active:
                        self.request_stop()
                elif kind == "step_finished":
                    if self._run_active and self.playback.paused:
                        self.btn_step.config(state="normal")
                        self.progress_var.set("Paused — press Step or Resume")
                elif kind == "countdown":
                    self.progress_var.set(event[1])
                elif kind == "progress":
                    _, loop, loops, idx, step, total = event
                    self._progress_index = idx
                    self.progress_var.set(
                        f"Loop {loop}/{loops} · Step {step}/{total if total is not None else '?'}"
                    )
                    self.lst.selection_clear(0, tk.END)
                    self.lst.selection_set(idx)
                    self.lst.activate(idx)
                    self.lst.see(idx)
                elif kind == "finished":
                    _, status, message = event
                    self._run_active = False
                    self.btn_run.config(state="normal", text="Run")
                    self.btn_stop.config(state="disabled")
                    self.btn_pause.config(state="disabled", text="Pause")
                    self.btn_step.config(state="normal")
                    self.btn_from_selected.config(state="normal")
                    self._progress_index = None
                    self.progress_var.set("Ready" if status == "done" else message)
                    self.btn_rec.config(state="normal")
                    self.btn_rec_stop.config(state="disabled")
                    self._set_editing_enabled(True)
                    if status == "done":
                        messagebox.showinfo("Done", message)
                    else:
                        messagebox.showwarning("Aborted", message)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_events)

    def _close(self):
        self.playback.stop()
        if self._global_hotkeys is not None:
            self._global_hotkeys.stop()
        self.stop_recording()
        self.destroy()

    def _start_global_hotkeys(self):
        """Conservative global chords; listener callbacks only enqueue events."""
        try:
            self._global_hotkeys = keyboard.GlobalHotKeys({
                "<ctrl>+<alt>+<shift>+<f6>":
                    lambda: self.events.put(("global_pause",)),
                "<ctrl>+<alt>+<shift>+<f8>":
                    lambda: self.events.put(("global_stop",)),
            })
            self._global_hotkeys.start()
            self.global_hotkeys_available = True
        except Exception:
            # Desktop/session permissions can prevent low-level keyboard hooks.
            self._global_hotkeys = None
            self.global_hotkeys_available = False
            self.progress_var.set("Global hotkeys unavailable — use the app controls")

    # ---------- Tabs ----------
    def _build_click_tab(self, nb: ttk.Notebook):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Click")

        # Form grid setup for alignment
        for c in range(4):
            tab.columnconfigure(c, weight=0)
        tab.columnconfigure(4, weight=1)  # spacer/stretch

        r = 0
        # Row 0: Position
        ttk.Label(tab, text="Position (x, y):")  .grid(row=r, column=0, sticky="e", padx=(0,6), pady=4)
        self.cx = tk.IntVar(value=0)
        self.cy = tk.IntVar(value=0)
        ttk.Entry(tab, width=8, textvariable=self.cx).grid(row=r, column=1, sticky="w", pady=4)
        ttk.Entry(tab, width=8, textvariable=self.cy).grid(row=r, column=2, sticky="w", padx=(6,0), pady=4)
        ttk.Button(tab, text="Pick…", command=lambda: self.pick_position(self.cx, self.cy)).grid(row=r, column=3, sticky="w", padx=(10,0), pady=4)

        # Row 1: Button + Clicks
        r += 1
        ttk.Label(tab, text="Mouse button:")     .grid(row=r, column=0, sticky="e", padx=(0,6), pady=4)
        self.cbutton = tk.StringVar(value="left")
        ttk.Combobox(tab, textvariable=self.cbutton, values=["left", "right", "middle"], width=12, state="readonly")\
            .grid(row=r, column=1, sticky="w", pady=4)

        ttk.Label(tab, text="Clicks:")           .grid(row=r, column=2, sticky="e", padx=(10,6), pady=4)
        self.cclicks = tk.IntVar(value=1)
        ttk.Entry(tab, width=8, textvariable=self.cclicks).grid(row=r, column=3, sticky="w", pady=4)

        # Row 2: Interval + Repeat
        r += 1
        ttk.Label(tab, text="Interval (s):")     .grid(row=r, column=0, sticky="e", padx=(0,6), pady=4)
        self.cinterval = tk.DoubleVar(value=0.0)
        ttk.Entry(tab, width=10, textvariable=self.cinterval).grid(row=r, column=1, sticky="w", pady=4)

        ttk.Label(tab, text="Repeat (per-action):").grid(row=r, column=2, sticky="e", padx=(10,6), pady=4)
        self.crepeats = tk.IntVar(value=1)
        ttk.Entry(tab, width=8, textvariable=self.crepeats).grid(row=r, column=3, sticky="w", pady=4)

        # Row 3: Label (optional)  ← NEW
        r += 1
        ttk.Label(tab, text="Label (optional):").grid(row=r, column=0, sticky="e", padx=(0,6), pady=4)
        self.cname = tk.StringVar(value="")
        ttk.Entry(tab, width=24, textvariable=self.cname).grid(row=r, column=1, columnspan=3, sticky="w", pady=4)

        # Row 4: Test + Add buttons  ← NEW
        r += 1
        ttk.Button(tab, text="Test Move", command=self.test_move_click_target)\
            .grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 12), padx=(0,6))
        self._editor_button(tab, text="Add Click Action", command=self.add_click)\
            .grid(row=r, column=2, columnspan=2, sticky="ew", pady=(8, 12))

        # Separator
        r += 1
        ttk.Separator(tab).grid(row=r, column=0, columnspan=5, sticky="ew", pady=(4, 8))

        # -------- Recording section (stacked & narrower) --------
        r += 1
        recbox = ttk.Labelframe(tab, text="Recording (mouse clicks)", padding=(10, 8))
        # Span only the main form columns (0..3). Column 4 in the tab remains a flexible spacer.
        recbox.grid(row=r, column=0, columnspan=4, sticky="ew")

        # Keep a simple 4-column grid inside the box; last column can stretch a bit
        for c in range(4):
            recbox.columnconfigure(c, weight=0)
        recbox.columnconfigure(3, weight=1)

        # Row 0: primary controls + status
        self.btn_rec = ttk.Button(recbox, text="Start Recording", command=self.start_recording)
        self.btn_rec.grid(row=0, column=0, padx=(0, 6), pady=4, sticky="w")

        self.btn_rec_stop = ttk.Button(recbox, text="Stop Recording", command=self.stop_recording, state="disabled")
        self.btn_rec_stop.grid(row=0, column=1, padx=(0, 12), pady=4, sticky="w")

        self.rec_status = ttk.Label(recbox, text="Ready", foreground="#0a7")
        self.rec_status.grid(row=0, column=2, columnspan=2, padx=(0, 0), pady=4, sticky="w")

        # Row 1: waits toggle (full row)
        self.rec_insert_waits_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            recbox,
            text="Insert waits between clicks",
            variable=self.rec_insert_waits_var
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 2))

        # Row 2: timing + repeats (two label/entry pairs)
        ttk.Label(recbox, text="Min wait (s):").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=4)
        self.rec_min_wait_var = tk.DoubleVar(value=0.30)
        ttk.Entry(recbox, width=8, textvariable=self.rec_min_wait_var).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(recbox, text="Recorded repeats (x):").grid(row=2, column=2, sticky="e", padx=(10, 6), pady=4)
        self.rec_repeats_var = tk.IntVar(value=1)
        ttk.Entry(recbox, width=8, textvariable=self.rec_repeats_var).grid(row=2, column=3, sticky="w", pady=4)


    def _build_wait_tab(self, nb: ttk.Notebook):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Wait")

        for c in range(4):
            tab.columnconfigure(c, weight=0)
        tab.columnconfigure(4, weight=1)

        ttk.Label(tab, text="Seconds:")          .grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        self.wseconds = tk.DoubleVar(value=2.0)
        ttk.Entry(tab, width=10, textvariable=self.wseconds).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(tab, text="Repeat (per-action):").grid(row=0, column=2, sticky="e", padx=(10,6), pady=4)
        self.wrepeats = tk.IntVar(value=1)
        ttk.Entry(tab, width=8, textvariable=self.wrepeats).grid(row=0, column=3, sticky="w", pady=4)
        
        ttk.Label(tab, text="Label (optional):").grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        self.wname = tk.StringVar(value="")
        ttk.Entry(tab, width=24, textvariable=self.wname).grid(row=1, column=1, columnspan=3, sticky="w", pady=4)

        self._editor_button(tab, text="Add Wait Action", command=self.add_wait)\
            .grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _build_key_tab(self, nb: ttk.Notebook):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Key / Type")

        for c in range(4):
            tab.columnconfigure(c, weight=0)
        tab.columnconfigure(4, weight=1)

        ttk.Label(tab, text="Mode:")             .grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        self.kmode = tk.StringVar(value="press")
        ttk.Combobox(tab, textvariable=self.kmode, values=["press", "type"], width=12, state="readonly")\
            .grid(row=0, column=1, sticky="w", padx=(0,0), pady=4)

        ttk.Label(tab, text="Repeat (per-action):").grid(row=0, column=2, sticky="e", padx=(10,6), pady=4)
        self.krepeats = tk.IntVar(value=1)
        ttk.Entry(tab, width=8, textvariable=self.krepeats).grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(tab, text='Key (e.g., "enter") or text to type:').grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 4))
        self.kkeys = tk.StringVar(value="enter")
        ttk.Entry(tab, width=44, textvariable=self.kkeys).grid(row=2, column=0, columnspan=4, sticky="w", pady=4)

        ttk.Label(tab, text="Label (optional):").grid(row=3, column=0, sticky="e", padx=(0,6), pady=4)
        self.kname = tk.StringVar(value="")
        ttk.Entry(tab, width=24, textvariable=self.kname).grid(row=3, column=1, columnspan=3, sticky="w", pady=4)

        self._editor_button(tab, text="Add Key Action", command=self.add_key)\
            .grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _build_move_tab(self, nb: ttk.Notebook):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Move")

        for c in range(4):
            tab.columnconfigure(c, weight=0)
        tab.columnconfigure(4, weight=1)

        ttk.Label(tab, text="Position (x, y):")  .grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        self.mx = tk.IntVar(value=0)
        self.my = tk.IntVar(value=0)
        ttk.Entry(tab, width=8, textvariable=self.mx).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Entry(tab, width=8, textvariable=self.my).grid(row=0, column=2, sticky="w", padx=(6,0), pady=4)
        ttk.Button(tab, text="Pick…", command=lambda: self.pick_position(self.mx, self.my)).grid(row=0, column=3, sticky="w", padx=(10,0), pady=4)

        ttk.Label(tab, text="Move duration (s):").grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        self.mdur = tk.DoubleVar(value=0.2)
        ttk.Entry(tab, width=10, textvariable=self.mdur).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(tab, text="Repeat (per-action):").grid(row=1, column=2, sticky="e", padx=(10,6), pady=4)
        self.mrepeats = tk.IntVar(value=1)
        ttk.Entry(tab, width=8, textvariable=self.mrepeats).grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(tab, text="Label (optional):").grid(row=2, column=0, sticky="e", padx=(0,6), pady=4)
        self.mname = tk.StringVar(value="")
        ttk.Entry(tab, width=24, textvariable=self.mname).grid(row=2, column=1, columnspan=3, sticky="w", pady=4)

        self._editor_button(tab, text="Add Move Action", command=self.add_move)\
            .grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def _build_scroll_tab(self, nb):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Scroll")
        self.scroll_amount = tk.StringVar(value="-3")
        self.scroll_repeats = tk.StringVar(value="1")
        self.scroll_name = tk.StringVar(value="")
        for row, (label, var) in enumerate((
            ("Scroll steps (+up / -down):", self.scroll_amount),
            ("Repeat (per-action):", self.scroll_repeats),
            ("Label (optional):", self.scroll_name),
        )):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(tab, width=23, textvariable=var).grid(row=row, column=1, sticky="w", pady=5, padx=8)
        self._editor_button(tab, text="Add Scroll Action", command=self.add_scroll).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

    def _build_drag_tab(self, nb):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Drag")
        self.drag_vars = {
            "x": tk.StringVar(value="0"), "y": tk.StringVar(value="0"),
            "to_x": tk.StringVar(value="100"), "to_y": tk.StringVar(value="100"),
            "move_duration": tk.StringVar(value="0.5"),
            "button": tk.StringVar(value="left"),
            "repeats": tk.StringVar(value="1"), "name": tk.StringVar(value=""),
        }
        fields = [
            ("Start X", "x"), ("Start Y", "y"), ("End X", "to_x"),
            ("End Y", "to_y"), ("Duration (s)", "move_duration"),
            ("Mouse button", "button"), ("Repeat", "repeats"), ("Label", "name")
        ]
        for i, (label, key) in enumerate(fields):
            ttk.Label(tab, text=label + ":").grid(row=i, column=0, sticky="w", pady=2)
            if key == "button":
                control = ttk.Combobox(tab, width=22, state="readonly",
                                       textvariable=self.drag_vars[key],
                                       values=("left", "right", "middle"))
            else:
                control = ttk.Entry(tab, width=24, textvariable=self.drag_vars[key])
            control.grid(row=i, column=1, sticky="w", padx=8, pady=2)
        self._editor_button(tab, text="Add Drag Action", command=self.add_drag).grid(
            row=len(fields), column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def add_scroll(self):
        if self._editing_locked():
            return
        try:
            self._append_validated(Action(kind="scroll", name=self.scroll_name.get().strip(),
                                          repeats=int(self.scroll_repeats.get()),
                                          scroll_amount=int(self.scroll_amount.get())))
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def add_drag(self):
        if self._editing_locked():
            return
        try:
            vars = self.drag_vars
            self._append_validated(Action(
                kind="drag", x=int(vars["x"].get()), y=int(vars["y"].get()),
                to_x=int(vars["to_x"].get()), to_y=int(vars["to_y"].get()),
                move_duration=float(vars["move_duration"].get()),
                button=vars["button"].get(), repeats=int(vars["repeats"].get()),
                name=vars["name"].get().strip()
            ))
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def _build_loop_tab(self, nb):
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Loop")
        self.loop_repeats_var = tk.StringVar(value="5")
        self.loop_name_var = tk.StringVar(value="")

        ttk.Label(tab, text="Repeat block (cycles):").grid(
            row=0, column=0, sticky="w", pady=5
        )
        ttk.Entry(tab, width=10, textvariable=self.loop_repeats_var).grid(
            row=0, column=1, sticky="w", padx=8, pady=5
        )
        ttk.Label(tab, text="Label (optional):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(tab, width=20, textvariable=self.loop_name_var).grid(
            row=1, column=1, sticky="w", padx=8, pady=5
        )
        ttk.Label(
            tab, text="Select the first action inside the block, then insert Start.\n"
                      "Select the last action inside the block, then insert End.\n"
                      "No selection: insert the marker at the end.",
            justify="left"
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 8))
        self._editor_button(tab, text="Insert Loop Start", command=self.add_loop_start).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=4
        )
        self._editor_button(tab, text="Insert Loop End", command=self.add_loop_end).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=4
        )

    def _insert_loop_marker(self, action, before_selected):
        selected = self.lst.curselection()
        index = selected[0] + (0 if before_selected else 1) if selected else len(self.actions)
        self.actions.insert(index, validate_action(asdict(action)))
        self.refresh_list()
        self._select_action(index)

    def add_loop_start(self):
        if self._editing_locked():
            return
        try:
            repeats = int(self.loop_repeats_var.get())
            self._insert_loop_marker(
                Action(kind="loop_start", name=self.loop_name_var.get().strip(),
                       repeats=repeats), before_selected=True
            )
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid loop", str(exc))

    def add_loop_end(self):
        if self._editing_locked():
            return
        self._insert_loop_marker(Action(kind="loop_end"), before_selected=False)

    def _build_vision_tab(self, nb):
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text="Vision")
        tab.columnconfigure(1, weight=1)
        self.vision_vars = {
            "kind": tk.StringVar(value="click_image"),
            "condition_source": tk.StringVar(value="image"),
            "match_mode": tk.StringVar(value="matches"),
            "image_path": tk.StringVar(value=""),
            "confidence": tk.StringVar(value="0.90"),
            "region": tk.StringVar(value=""),
            "pixel_x": tk.StringVar(value="0"),
            "pixel_y": tk.StringVar(value="0"),
            "pixel_color": tk.StringVar(value="#00FF00"),
            "pixel_tolerance": tk.StringVar(value="10"),
            "timeout": tk.StringVar(value="10"),
            "poll_interval": tk.StringVar(value="0.3"),
            "repeats": tk.StringVar(value="5"),
            "name": tk.StringVar(value=""),
        }
        v = self.vision_vars
        rows = [
            ("Action", "kind", ("click_image", "wait_until", "if_start",
                                  "else", "if_end", "until_start", "until_end")),
            ("Detect by", "condition_source", ("image", "pixel")),
            ("Condition", "match_mode", ("matches", "not_matches")),
            ("Reference image", "image_path", None),
            ("Min similarity (0–1)", "confidence", None),
            ("Search region x,y,w,h", "region", None),
            ("Pixel X", "pixel_x", None),
            ("Pixel Y", "pixel_y", None),
            ("Pixel color #RRGGBB", "pixel_color", None),
            ("Color tolerance (0–255)", "pixel_tolerance", None),
            ("Timeout (seconds)", "timeout", None),
            ("Poll interval (seconds)", "poll_interval", None),
            ("Max cycles (Repeat Until)", "repeats", None),
            ("Label", "name", None),
        ]
        for i, (label, key, choices) in enumerate(rows):
            ttk.Label(tab, text=label + ":").grid(row=i, column=0, sticky="w", pady=2)
            if choices:
                widget = ttk.Combobox(tab, width=22, textvariable=v[key],
                                      values=choices, state="readonly")
            else:
                widget = ttk.Entry(tab, width=25, textvariable=v[key])
            widget.grid(row=i, column=1, sticky="ew", pady=2, padx=(4, 0))
            if key == "image_path":
                ttk.Button(tab, text="…", width=3, command=self.pick_vision_image).grid(
                    row=i, column=2, padx=(4, 0))
        ttk.Label(tab, text="Image: choose a cropped PNG. Region is optional.\n"
                            "Block starts insert before selection; ends after.",
                  justify="left").grid(row=len(rows), column=0, columnspan=3,
                                       sticky="w", pady=(5, 4))
        self._editor_button(tab, text="Add Vision / Flow Action",
                            command=self.add_vision_action).grid(
            row=len(rows) + 1, column=0, columnspan=3, sticky="ew"
        )

    def pick_vision_image(self):
        path = filedialog.askopenfilename(
            title="Choose a cropped reference image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")]
        )
        if path:
            self.vision_vars["image_path"].set(path)

    @staticmethod
    def _vision_region(text):
        text = text.strip()
        if not text:
            return (None, None, None, None)
        parts = [part.strip() for part in text.split(",")]
        if len(parts) != 4:
            raise ValueError("Region must be x,y,width,height or blank.")
        return tuple(int(part) for part in parts)

    def add_vision_action(self):
        if self._editing_locked():
            return
        v = self.vision_vars
        kind = v["kind"].get()
        try:
            properties = {"kind": kind, "name": v["name"].get().strip()}
            if kind in ("click_image", "wait_until", "if_start", "until_start"):
                region = self._vision_region(v["region"].get())
                properties.update(
                    condition_source=v["condition_source"].get(),
                    match_mode="matches" if kind == "click_image" else v["match_mode"].get(),
                    image_path=v["image_path"].get().strip(),
                    confidence=float(v["confidence"].get()),
                    region_x=region[0], region_y=region[1],
                    region_w=region[2], region_h=region[3],
                    pixel_x=int(v["pixel_x"].get()), pixel_y=int(v["pixel_y"].get()),
                    pixel_color=v["pixel_color"].get().strip(),
                    pixel_tolerance=int(v["pixel_tolerance"].get()),
                    timeout=float(v["timeout"].get()),
                    poll_interval=float(v["poll_interval"].get())
                )
            if kind == "click_image":
                properties["condition_source"] = "image"
            if kind == "until_start":
                properties["repeats"] = int(v["repeats"].get())
            action = validate_action(asdict(Action(**properties)))
            selected = self.lst.curselection()
            before_selected = kind in ("if_start", "until_start")
            index = (selected[0] + (0 if before_selected else 1)
                     if selected else len(self.actions))
            self.actions.insert(index, action)
            self.refresh_list()
            self._select_action(index)
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid vision action", str(exc))

    # ---------- Keyboard shortcuts ----------
    def _bind_shortcuts(self):
        # List editing
        self.bind("<Delete>", self._shortcut_delete)
        self.bind("<Control-Shift-d>", self._shortcut_duplicate)
        if sys.platform == "darwin":
            self.bind("<Command-Shift-d>", self._shortcut_duplicate)

        self.bind("<Control-Up>", lambda e: self._shortcut_move(-1, e))
        self.bind("<Control-Down>", lambda e: self._shortcut_move(1, e))
        self.bind("<Control-e>", self._shortcut_edit_repeat)
        # Run/Stop
        self.bind("<F5>", lambda e: self.start_run())
        self.bind("<Escape>", lambda e: self.request_stop())
        self.bind("<F6>", lambda e: self.toggle_pause())
        # Files
        self.bind("<Control-s>", lambda e: self.save_sequence())
        self.bind("<Control-o>", lambda e: self.load_sequence())
        # Recording
        self.bind("<Control-r>", self._toggle_recording)
        self.bind("<F2>", lambda e: self.edit_name_selected())

        # Also bind Delete directly on the listbox
        self.lst.bind("<Delete>", self._shortcut_delete)

    def _is_typing_context(self, event) -> bool:
        w = getattr(event, "widget", None)
        if not w:
            return False
        klass = w.winfo_class()
        return klass in ("TEntry", "Entry", "TCombobox", "Combobox", "Text")

    def _shortcut_delete(self, event=None):
        if event and self._is_typing_context(event):
            return
        self.delete_item()
        return "break"

    def _shortcut_duplicate(self, event=None):
        if event and self._is_typing_context(event):
            return
        self.duplicate_item()
        return "break"

    def _shortcut_move(self, delta: int, event=None):
        if event and self._is_typing_context(event):
            return
        self.move_item(delta)
        return "break"

    def _shortcut_edit_repeat(self, event=None):
        if event and self._is_typing_context(event):
            return
        self.edit_repeat_selected()
        return "break"

    def _toggle_recording(self, event=None):
        if self.is_running():
            return "break"
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()
        return "break"

    def _show_shortcuts_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Keyboard Shortcuts")
        dlg.transient(self)
        dlg.grab_set()
        pad = 10
        frm = ttk.Frame(dlg, padding=pad)
        frm.pack(fill="both", expand=True)
        IS_MAC = sys.platform == "darwin"
        def acc(s: str) -> str:
            return s.replace("Ctrl", "⌘").replace("Alt", "⌥").replace("Shift", "⇧") if IS_MAC else s
        rows = [
            ("Run", "F5"),
            ("Stop", "Esc"),
            ("Pause / Resume", "F6"),
            ("Global Pause / Resume", "Ctrl+Alt+Shift+F6"),
            ("Global Stop", "Ctrl+Alt+Shift+F8"),
            ("Step (when paused)", "Step button"),
            ("Run from Selected (once)", "Debug button"),
            ("Delete selected", "Del"),
            ("Duplicate selected", acc("Ctrl+Shift+D")),
            ("Move selected", acc("Ctrl+↑ / Ctrl+↓")),
            ("Edit repeat", acc("Ctrl+E")),
            ("Save sequence", acc("Ctrl+S")),
            ("Load sequence", acc("Ctrl+O")),
            ("Start/Stop recording", acc("Ctrl+R")),
        ]
        if not self.global_hotkeys_available:
            rows.append(("Global shortcuts", "Unavailable in this desktop session"))
        for i, (name, keys) in enumerate(rows):
            ttk.Label(frm, text=name).grid(row=i, column=0, sticky="w", padx=(0, 18), pady=4)
            ttk.Label(frm, text=keys, foreground="#444").grid(row=i, column=1, sticky="w", pady=4)
        ttk.Button(frm, text="Close", command=dlg.destroy).grid(row=len(rows), column=0, columnspan=2, pady=(12,0))

    # ---------- Action add helpers ----------
    def add_click(self):
        if self._editing_locked():
            return
        try:
            a = Action(
            kind="click",
            name=self.cname.get().strip(),
            repeats=max(1, int(self.crepeats.get())),
            x=int(self.cx.get()),
            y=int(self.cy.get()),
            button=self.cbutton.get(),
            clicks=max(1, int(self.cclicks.get())),
            interval=max(0.0, float(self.cinterval.get()))
            )
            self._append_validated(a)
        except (ValueError, tk.TclError, TypeError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def add_wait(self):
        if self._editing_locked():
            return
        try:
            a = Action(
            kind="wait",
            name=self.wname.get().strip(),
            repeats=max(1, int(self.wrepeats.get())),
            seconds=max(0.0, float(self.wseconds.get()))
            )
            self._append_validated(a)
        except (ValueError, tk.TclError, TypeError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def add_key(self):
        if self._editing_locked():
            return
        try:
            mode = self.kmode.get()
            keys = self.kkeys.get().strip()
            if not keys:
                messagebox.showerror("Invalid input", "Please enter a key name (e.g., 'enter') or text to type.")
                return
            a = Action(kind="key", 
                   name=self.kname.get().strip(),
                   repeats=max(1, int(self.krepeats.get())), 
                   key_mode=mode, keys=keys)
            self._append_validated(a)
        except (ValueError, tk.TclError, TypeError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def add_move(self):
        if self._editing_locked():
            return
        try:
            a = Action(
            kind="move",
            name=self.mname.get().strip(),
            repeats=max(1, int(self.mrepeats.get())),
            x=int(self.mx.get()),
            y=int(self.my.get()),
            move_duration=max(0.0, float(self.mdur.get()))
            )
            self._append_validated(a)
        except (ValueError, tk.TclError, TypeError) as exc:
            messagebox.showerror("Invalid action", str(exc))

    def _append_validated(self, action):
        action = validate_action(asdict(action))
        self.actions.append(action)
        self.refresh_list()

    # ---------- List management ----------
    def refresh_list(self):
        selection = self.lst.curselection()
        self.lst.delete(0, tk.END)
        inside_block = False
        for i, a in enumerate(self.actions):
            prefix = "    ↳ " if inside_block and a.kind != "loop_end" else ""
            self.lst.insert(tk.END, f"{i+1}. {prefix}{self.describe(a)}")
            if a.kind == "loop_start":
                inside_block = True
            elif a.kind == "loop_end":
                inside_block = False
        if selection and selection[0] < len(self.actions):
            self.lst.selection_set(selection[0])

    def _select_action(self, index):
        self.lst.selection_clear(0, tk.END)
        if 0 <= index < len(self.actions):
            self.lst.selection_set(index)
            self.lst.activate(index)
            self.lst.see(index)

    def describe(self, a: Action) -> str:
        if not a.enabled:
            state = "[OFF] "
        else:
            state = ""
        rep = f" ×{a.repeats}" if a.repeats > 1 else ""
        label = f"[{a.name}] " if a.name.strip() else ""
        label = state + label
        if a.kind == "click":
            return f"{label}Click({a.button}) @({a.x},{a.y}) clicks={a.clicks} interval={a.interval}s{rep}"
        if a.kind == "wait":
            return f"{label}Wait {a.seconds}s{rep}"
        if a.kind == "key":
            d = f'Type "{a.keys}"' if a.key_mode == "type" else f"Key press: {a.keys}"
            return f"{label}{d}{rep}"
        if a.kind == "move":
            return f"{label}Move @({a.x},{a.y}) over {a.move_duration}s{rep}"
        if a.kind == "scroll":
            return f"{label}Scroll {a.scroll_amount} steps{rep}"
        if a.kind == "drag":
            return f"{label}Drag ({a.x},{a.y}) → ({a.to_x},{a.to_y}) in {a.move_duration}s{rep}"
        if a.kind == "loop_start":
            return f"{label}┌ Repeat block ×{a.repeats}"
        if a.kind == "loop_end":
            return f"{label}└ End block"
        if a.kind in ("click_image", "wait_until", "if_start", "until_start"):
            target = (a.image_path.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1]
                      if a.condition_source == "image"
                      else f"pixel ({a.pixel_x},{a.pixel_y}) {a.pixel_color}")
            label_kind = {"click_image": "Click image", "wait_until": "Wait until",
                          "if_start": "IF", "until_start": "Repeat until"}[a.kind]
            count = f" (max {a.repeats} cycles)" if a.kind == "until_start" else ""
            return f"{label}{label_kind} {a.match_mode} {target}{count}"
        if a.kind in ("else", "if_end", "until_end"):
            return f"{label}{a.kind.replace('_', ' ').upper()}"
        return str(a)
    
    def _double_click_action(self, event):
        if self._editing_locked():
            return "break"
        index = self.lst.nearest(event.y)
        bounds = self.lst.bbox(index)
        if bounds and bounds[1] <= event.y < bounds[1] + bounds[3]:
            self._select_action(index)
            self.edit_action_selected()
        return "break"

    def toggle_action_enabled(self):
        if self._editing_locked():
            return
        selected = self.lst.curselection()
        if not selected:
            return
        index = selected[0]
        action = self.actions[index]
        if action.kind in CONTROL:
            messagebox.showinfo("Control marker", "Control markers cannot be disabled. Disable actions inside the block instead.")
            return
        action.enabled = not action.enabled
        self.refresh_list()
        self._select_action(index)

    def edit_action_selected(self):
        """Edit an existing action without altering it until Save is validated."""
        if self._editing_locked():
            return
        selected = self.lst.curselection()
        if not selected:
            return
        index = selected[0]
        original = self.actions[index]

        dialog = tk.Toplevel(self)
        dialog.title("Edit Action")
        dialog.transient(self)
        dialog.resizable(False, False)

        form = ttk.Frame(dialog, padding=14)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        kind_var = tk.StringVar(value=original.kind)
        name_var = tk.StringVar(value=original.name)
        repeat_var = tk.StringVar(value=str(original.repeats))
        enabled_var = tk.BooleanVar(value=original.enabled)

        ttk.Label(form, text="Action type:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(form, width=25, textvariable=kind_var,
                     values=("click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end"),
                     state="readonly").grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Name:").grid(row=1, column=0, sticky="w", pady=4)
        name_entry = ttk.Entry(form, width=32, textvariable=name_var)
        name_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Repeat:").grid(row=2, column=0, sticky="w", pady=4)
        repeat_entry = ttk.Entry(form, textvariable=repeat_var)
        repeat_entry.grid(row=2, column=1, sticky="ew", pady=4)

        enabled_check = ttk.Checkbutton(form, text="Enabled", variable=enabled_var)
        enabled_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 8))

        # Each kind shows only its relevant fields. Values are kept when switching tabs.
        field_specs = {
            "click": (("x", "X coordinate", int), ("y", "Y coordinate", int),
                      ("button", "Mouse button", str), ("clicks", "Click count", int),
                      ("interval", "Interval (seconds)", float)),
            "wait": (("seconds", "Wait (seconds)", float),),
            "key": (("key_mode", "Mode", str), ("keys", "Key / Text", str)),
            "move": (("x", "X coordinate", int), ("y", "Y coordinate", int),
                     ("move_duration", "Duration (seconds)", float)),
            "scroll": (("scroll_amount", "Scroll steps (+up/-down)", int),),
            "drag": (("x", "Start X", int), ("y", "Start Y", int),
                     ("to_x", "End X", int), ("to_y", "End Y", int),
                     ("move_duration", "Duration (seconds)", float),
                     ("button", "Mouse button", str)),
            "loop_start": (),
            "loop_end": (),
        }
        fields = {}
        for kind_fields in field_specs.values():
            for key, _, _ in kind_fields:
                if key not in fields:
                    value = getattr(original, key)
                    if value is None and key in ("x", "y", "to_x", "to_y"):
                        value = 0
                    fields[key] = tk.StringVar(value=str(value))

        details = ttk.LabelFrame(form, text="Action settings", padding=8)
        details.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        details.columnconfigure(1, weight=1)

        def rebuild_fields(*_):
            marker = kind_var.get() in ("loop_start", "loop_end")
            repeat_entry.configure(state="disabled" if kind_var.get() == "loop_end" else "normal")
            if kind_var.get() == "loop_end":
                repeat_var.set("1")
            enabled_check.configure(state="disabled" if marker else "normal")
            if marker:
                enabled_var.set(True)
            for child in details.winfo_children():
                child.destroy()
            for row, (field, label, _) in enumerate(field_specs[kind_var.get()]):
                ttk.Label(details, text=label + ":").grid(
                    row=row, column=0, sticky="w", padx=(0, 10), pady=4
                )
                if field in ("button", "key_mode"):
                    choices = ("left", "right", "middle") if field == "button" else ("press", "type")
                    widget = ttk.Combobox(details, width=24, textvariable=fields[field],
                                          values=choices, state="readonly")
                else:
                    widget = ttk.Entry(details, width=25, textvariable=fields[field])
                widget.grid(row=row, column=1, sticky="ew", pady=4)

        kind_var.trace_add("write", rebuild_fields)
        rebuild_fields()

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(2, 0))

        def save():
            if self._editing_locked():
                dialog.destroy()
                return
            try:
                data = asdict(original)
                data.update(kind=kind_var.get(), name=name_var.get().strip(),
                            repeats=int(repeat_var.get()), enabled=enabled_var.get())
                for field, _, converter in field_specs[kind_var.get()]:
                    data[field] = converter(fields[field].get())
                updated = validate_action(data)
            except (ValueError, TypeError, tk.TclError, KeyError) as exc:
                messagebox.showerror("Invalid action", str(exc), parent=dialog)
                return
            self.actions[index] = updated
            self.refresh_list()
            self._select_action(index)
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Save", command=save).pack(side="left")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()
        name_entry.focus_set()

    def edit_name_selected(self):
        if self._editing_locked():
            return
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        a = self.actions[idx]

        dlg = tk.Toplevel(self)
        dlg.title("Edit Name")
        dlg.grab_set()
        ttk.Label(dlg, text="Label / Name:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        var = tk.StringVar(value=a.name)
        ttk.Entry(dlg, width=32, textvariable=var).grid(row=0, column=1, padx=10, pady=10, sticky="w")

        def ok():
            if self._editing_locked():
                dlg.destroy()
                return
            a.name = var.get().strip()
            self.refresh_list()
            self._select_action(idx)
            dlg.destroy()

        ttk.Button(dlg, text="OK", command=ok).grid(row=1, column=0, columnspan=2, pady=(0, 10))

    def test_move_click_target(self):
        try:
            x = int(self.cx.get())
            y = int(self.cy.get())
        except Exception:
            messagebox.showerror("Invalid coordinates", "Please enter valid X and Y.")
            return

        # Small countdown overlay (reuse style from pick_position)
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"260x110+{self.winfo_rootx()+60}+{self.winfo_rooty()+60}")
        frm = ttk.Frame(overlay, padding=12)
        frm.pack(expand=True, fill="both")
        lbl = ttk.Label(frm, text="Test move in 2…", font=("Segoe UI", 11))
        lbl.pack(expand=True)

        def go():
            overlay.destroy()
            try:
                # Save current pos, move to target, wait, move back
                curx, cury = pag.position()
                pag.moveTo(x, y, duration=0.35)
                time.sleep(0.6)
                pag.moveTo(curx, cury, duration=0.35)
            except Exception as e:
                messagebox.showerror("Test failed", str(e))

        # quick 2->1 countdown
        def countdown(n=2):
            if n == 0:
                self.after(50, go)
                return
            lbl.config(text=f"Test move in {n}…")
            self.after(1000, lambda: countdown(n-1))
        countdown()

    def move_item(self, delta: int):
        if self._editing_locked():
            return
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        new = idx + delta
        if new < 0 or new >= len(self.actions):
            return
        self.actions[idx], self.actions[new] = self.actions[new], self.actions[idx]
        self.refresh_list()
        self.lst.selection_set(new)

    def delete_item(self):
        if self._editing_locked():
            return
        sel = self.lst.curselection()
        if not sel:
            return
        del self.actions[sel[0]]
        self.refresh_list()

    def duplicate_item(self):
        if self._editing_locked():
            return
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        if self.actions[idx].kind in CONTROL:
            messagebox.showinfo("Duplicate block", "Duplicate executable actions, then insert the required block markers separately.")
            return
        self.actions.insert(idx + 1, Action(**asdict(self.actions[idx])))
        self.refresh_list()
        self.lst.selection_set(idx + 1)

    def clear_items(self):
        if self._editing_locked():
            return
        if messagebox.askyesno("Confirm", "Clear all actions?"):
            self.actions.clear()
            self.refresh_list()

    def edit_repeat_selected(self):
        if self._editing_locked():
            return
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        a = self.actions[idx]
        if a.kind in CONTROL and a.kind not in ("loop_start", "until_start"):
            messagebox.showinfo("Control marker", "Only Loop Start and Repeat Until have cycle counts.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Edit Repeat")
        dlg.grab_set()
        ttk.Label(dlg, text="Repeat (per-action):").grid(row=0, column=0, padx=10, pady=10)
        var = tk.IntVar(value=a.repeats)
        ttk.Entry(dlg, width=8, textvariable=var).grid(row=0, column=1, padx=10, pady=10)
        def ok():
            if self._editing_locked():
                dlg.destroy()
                return
            try:
                a.repeats = max(1, int(var.get()))
                self.refresh_list()
                self._select_action(idx)
                dlg.destroy()
            except Exception:
                messagebox.showerror("Invalid value", "Repeat must be a positive integer.")
        ttk.Button(dlg, text="OK", command=ok).grid(row=1, column=0, columnspan=2, pady=(0, 10))

    def on_select(self, _evt):
        pass

    # ---------- Pick position ----------
    def pick_position(self, varx: tk.IntVar, vary: tk.IntVar):
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"280x120+{self.winfo_rootx()+50}+{self.winfo_rooty()+50}")
        frm = ttk.Frame(overlay, padding=15)
        frm.pack(expand=True, fill="both")
        lbl = ttk.Label(frm, text="Move mouse to desired spot...\nCapturing in 3", font=("Segoe UI", 12))
        lbl.pack(expand=True)
        def do_countdown(n=3):
            if n == 0:
                try:
                    x, y = pag.position()
                    varx.set(x)
                    vary.set(y)
                finally:
                    overlay.destroy()
                return
            lbl.config(text=f"Move mouse to desired spot...\nCapturing in {n}")
            self.after(1000, lambda: do_countdown(n-1))
        do_countdown()

    # ---------- Save / Load ----------
    def save_sequence(self):
        if not self.actions:
            messagebox.showinfo("Nothing to save", "Add some actions first.")
            return
        try:
            document = serialize_document(
                self.actions, self.repeat_var.get(), self.start_delay_var.get()
            )
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Save Sequence"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(document, f, indent=2)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        messagebox.showinfo("Saved", f"Saved to {path}")

    def load_sequence(self):
        if self._editing_locked():
            return
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Load Sequence"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded, settings = parse_document(data)
            self.actions = loaded
            if settings is not None:
                self.repeat_var.set(settings["repeat_count"])
                self.start_delay_var.set(settings["start_delay"])
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not load file:\n{e}")

    # ---------- Recording ----------
    def start_recording(self):
        if self._run_active or self.is_recording or self._record_pending:
            return
        try:
            min_wait = float(self.rec_min_wait_var.get())
            repeats = int(self.rec_repeats_var.get())
            if not 0 <= min_wait < float("inf") or repeats < 1:
                raise ValueError("Recording wait must be nonnegative and repeats must be positive.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid recording settings", str(exc))
            return

        self._record_min_wait = min_wait
        self._record_repeats = repeats
        self._record_insert_waits = bool(self.rec_insert_waits_var.get())
        self._record_token += 1
        token = self._record_token
        self._record_pending = True
        self._set_editing_enabled(False)
        self.btn_rec.config(state="disabled")
        self.btn_rec_stop.config(state="normal")

        def countdown(n=3):
            if not self._record_pending or token != self._record_token:
                return
            if n <= 0:
                self._record_after_id = None
                self._begin_mouse_listener()
                return
            self.rec_status.config(text=f"Recording starts in {n}…")
            self._record_after_id = self.after(1000, lambda: countdown(n - 1))
        countdown()

    def _begin_mouse_listener(self):
        if not self._record_pending:
            return
        self._record_pending = False
        self.is_recording = True
        self.last_record_ts = None
        self.rec_status.config(text="Recording…")
        token = self._record_token

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            bname = str(button).split(".")[-1].lower()
            self.events.put(("click", int(x), int(y), bname, time.monotonic(), token))

        try:
            self.mouse_listener = mouse.Listener(on_click=on_click)
            self.mouse_listener.start()
        except Exception as exc:
            self.stop_recording()
            messagebox.showerror("Recording unavailable", str(exc))

    def _handle_recorded_click(self, x, y, button, timestamp):
        # Ignore interaction with the MacroRunner window.
        if (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()):
            return
        if button not in ("left", "right", "middle"):
            return
        if self._record_insert_waits and self.last_record_ts is not None:
            gap = timestamp - self.last_record_ts
            if gap >= self._record_min_wait:
                self.actions.append(Action(kind="wait", seconds=round(gap, 3)))
        self.last_record_ts = timestamp
        self.actions.append(Action(kind="click", x=x, y=y, button=button,
                                   repeats=self._record_repeats))
        self.refresh_list()
        self.lst.selection_clear(0, tk.END)
        self.lst.selection_set(tk.END)
        self.lst.see(tk.END)

    def stop_recording(self):
        if not self.is_recording and not self._record_pending:
            return
        self.is_recording = False
        self._record_pending = False
        self._record_token += 1
        if self._record_after_id is not None:
            self.after_cancel(self._record_after_id)
            self._record_after_id = None
        if self.mouse_listener is not None:
            try:
                self.mouse_listener.stop()
            except Exception:
                pass
            self.mouse_listener = None
        self.rec_status.config(text="Ready")
        self.btn_rec.config(state="normal")
        self.btn_rec_stop.config(state="disabled")
        self._set_editing_enabled(True)

    # ---------- Running ----------
    def is_running(self) -> bool:
        return self._run_active

    def request_stop(self):
        self.playback.stop()

    def run_from_selected(self):
        if self._run_active:
            return
        selection = self.lst.curselection()
        if not selection:
            messagebox.showinfo("Select an action", "Select an action to start from.")
            return
        self.start_run(from_selected=True)

    def step_action(self):
        if not self._run_active:
            # Start a one-pass debug run, beginning at the selected action (if any).
            self.start_run(step_mode=True)
            if not self._run_active:
                return
        if not self.playback.paused or self.stop_flag.is_set():
            return
        try:
            self.playback.step()
        except RuntimeError:
            return
        self.btn_step.config(state="disabled")
        self.progress_var.set("Stepping…")

    def toggle_pause(self):
        if not self._run_active or self.stop_flag.is_set():
            return
        if self.playback.paused:
            self.playback.resume()
            self.btn_pause.config(text="Pause")
            self.btn_step.config(state="disabled")
        else:
            self.playback.pause()
            self.btn_pause.config(text="Resume")
            self.btn_step.config(state="normal")
            self.progress_var.set("Paused")

    def start_run(self, from_selected=False, step_mode=False):
        if self.is_recording or self._record_pending:
            messagebox.showwarning("Recording active", "Stop recording before running.")
            return
        if self._run_active:
            return
        if not self.actions:
            messagebox.showerror("No actions", "Add at least one action.")
            return
        if not any(action.enabled and action.kind not in CONTROL
                   for action in self.actions):
            messagebox.showwarning("No executable actions", "Add at least one enabled executable action.")
            return
        try:
            repeats = int(self.repeat_var.get())
            start_delay = float(self.start_delay_var.get())
            if repeats < 1 or not 0 <= start_delay < float("inf"):
                raise ValueError("Repeat count must be positive and delay nonnegative.")
            snapshot = [validate_action(asdict(a)) for a in self.actions]
            validate_flow(snapshot)
            smart = has_smart_actions(snapshot)
            selection = self.lst.curselection()
            start_index = selection[0] if (from_selected or step_mode) and selection else 0
            if from_selected and not selection:
                raise ValueError("Select an action first.")
            if from_selected or step_mode:
                repeats = 1
            if step_mode:
                start_delay = 0.0
            if smart:
                validate_start_selection(snapshot, start_index)
                total = None  # Conditional paths have an unknown execution length.
            else:
                total = progress_total(snapshot, repeats, start_index)
                if total == 0:
                    raise ValueError("No enabled executable actions at or after the selection.")
        except (ValueError, TypeError, tk.TclError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.playback.reset()
        if step_mode:
            self.playback.pause()
        self._progress_total = total
        self._run_active = True
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_pause.config(state="normal", text="Resume" if step_mode else "Pause")
        self.btn_step.config(state="normal" if step_mode else "disabled")
        self.btn_from_selected.config(state="disabled")
        self.progress_var.set("Paused — press Step" if step_mode else "Starting…")
        self.btn_rec.config(state="disabled")
        self.btn_rec_stop.config(state="disabled")
        self._set_editing_enabled(False)
        self.run_thread = threading.Thread(
            target=self._run_sequence,
            args=(snapshot, repeats, start_delay, start_index, smart), daemon=True
        )
        self.run_thread.start()

    def _wait_or_stop(self, duration):
        self.playback.wait(duration)

    def _run_sequence(self, actions, repeats, start_delay, start_index=0, smart=False):
        try:
            remaining = start_delay
            while remaining > 0:
                self.events.put(("countdown", f"Starting in {remaining:.1f}s…"))
                step = min(0.2, remaining)
                self._wait_or_stop(step)
                remaining -= step
            if start_delay:
                self.events.put(("countdown", "Run"))

            total = self._progress_total
            step = 0
            for loop in range(repeats):
                # Only the first outer cycle starts from a selected row.
                begin = start_index if loop == 0 else 0
                if smart:
                    steps = iter_flow_steps(
                        actions, self._check_visual_condition,
                        self.stop_flag.is_set, begin
                    )
                else:
                    steps = iter_execution_steps(actions, begin)
                for idx, action in steps:
                    self.playback.begin_action()
                    try:
                        step += 1
                        self.events.put(("progress", loop + 1, repeats, idx, step, total))
                        self._execute_action(action)
                    finally:
                        if self.playback.end_action():
                            self.events.put(("step_finished",))
            self.events.put(("finished", "done", f"Finished {repeats} loop(s)."))
        except Exception as exc:
            msg = "Stopped." if str(exc) == "Stopped" else f"Stopped: {exc}"
            self.events.put(("finished", "aborted", msg))

    def _check_visual_condition(self, action):
        self._wait_or_stop(0)
        return check_condition(action, pag.screenshot)

    def _execute_action(self, a: Action):
        if a.kind == "click_image":
            match = poll_until(a, lambda: locate_image(a, pag.screenshot),
                               self.playback)
            self._wait_or_stop(0)
            pag.click(match[0], match[1], button=a.button)
        elif a.kind == "wait_until":
            poll_until(a, lambda: self._check_visual_condition(a), self.playback)
        elif a.kind == "click":
            if a.x is not None and a.y is not None:
                pag.moveTo(a.x, a.y, duration=0)
            for index in range(a.clicks):
                self._wait_or_stop(0)
                pag.click(button=a.button)
                if index + 1 < a.clicks:
                    self._wait_or_stop(a.interval)

        elif a.kind == "wait":
            self._wait_or_stop(a.seconds)

        elif a.kind == "key":
            if a.key_mode == "type":
                for character in a.keys:
                    self._wait_or_stop(0)
                    pag.write(character)
            else:
                combo = [k.strip() for k in a.keys.split("+") if k.strip()]
                if len(combo) == 1:
                    pag.press(combo[0])
                else:
                    pag.hotkey(*combo)

        elif a.kind == "move":
            if a.x is not None and a.y is not None:
                pag.moveTo(a.x, a.y, duration=max(0.0, a.move_duration))

        elif a.kind == "scroll":
            self._wait_or_stop(0)
            pag.scroll(a.scroll_amount)

        elif a.kind == "drag":
            self._wait_or_stop(0)
            pag.moveTo(a.x, a.y, duration=0)
            # PyAutoGUI can finish a native drag before another pause/stop check.
            pag.dragTo(a.to_x, a.to_y, duration=a.move_duration, button=a.button)


def main():
    app = MacroRunnerApp()
    try:
        app.iconbitmap(resource_path("macro_runner_icon.ico"))
    except Exception:
        # Optional fallback: if you also ship a PNG, you can use iconphoto
        # from tkinter import PhotoImage
        # app.iconphoto(True, PhotoImage(file=resource_path("macro_runner_icon.png")))
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
