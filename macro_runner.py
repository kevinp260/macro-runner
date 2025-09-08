import threading
import time
import json
import os
import ctypes, sys
from dataclasses import dataclass, asdict
from typing import List, Literal, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# pip install pyautogui pillow pynput
import pyautogui as pag
from pynput import mouse

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

ActionType = Literal["click", "wait", "key", "move"]

@dataclass
class Action:
    kind: ActionType
    # Common
    name: str = ""
    repeats: int = 1

    # Click
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    clicks: int = 1
    interval: float = 0.0

    # Wait
    seconds: float = 1.0

    # Key / Type
    key_mode: str = "press"  # "press" or "type"
    keys: str = "enter"

    # Move
    move_duration: float = 0.2


class MacroRunnerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Macro Runner (Mouse/Keyboard Automator)")
        self.geometry("850x580")
        self.minsize(850, 580)

        self.actions: List[Action] = []
        self.run_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()

        # Recording state
        self.is_recording = False
        self.mouse_listener: Optional[mouse.Listener] = None
        self.last_record_ts: Optional[float] = None

        self._build_ui()

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

        self.btn_stop = ttk.Button(top, text="Stop", command=self.request_stop, state="disabled")
        self.btn_stop.grid(row=0, column=5, padx=4)

        ttk.Button(top, text="Save", command=self.save_sequence).grid(row=0, column=6, padx=4)
        ttk.Button(top, text="Load", command=self.load_sequence).grid(row=0, column=7, padx=4)

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

        ttk.Label(left, text="Actions").grid(row=0, column=0, sticky="w")

        self.lst = tk.Listbox(left, height=20, activestyle="dotbox")
        self.lst.grid(row=1, column=0, sticky="nsew")
        self.lst.bind("<<ListboxSelect>>", self.on_select)

        # Right: tabs
        right = ttk.Notebook(split)
        right.grid(row=0, column=1, sticky="ns")

        self._build_click_tab(right)  # includes Recording (moved here)
        self._build_wait_tab(right)
        self._build_key_tab(right)
        self._build_move_tab(right)

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
        ttk.Button(btns, text="▲ Up",         width=BW, command=lambda: self.move_item(-1)).grid(row=0, column=0, padx=2, sticky="w")
        ttk.Button(btns, text="▼ Down",       width=BW, command=lambda: self.move_item(1)).grid(row=0, column=1, padx=2, sticky="w")
        ttk.Button(btns, text="Delete",       width=BW, command=self.delete_item).grid(row=0, column=2, padx=2, sticky="w")
        ttk.Button(btns, text="Duplicate",    width=BW, command=self.duplicate_item).grid(row=0, column=3, padx=2, sticky="w")
        ttk.Button(btns, text="Clear",        width=BW, command=self.clear_items).grid(row=0, column=4, padx=2, sticky="w")
        ttk.Button(btns, text="Edit Repeat…", width=BW, command=self.edit_repeat_selected).grid(row=0, column=5, padx=2, sticky="w")
        ttk.Button(btns, text="Edit Name…",   width=BW, command=self.edit_name_selected).grid(row=0, column=6, padx=2, sticky="w")
        # spacer at col 7
        ttk.Label(btns, text="").grid(row=0, column=7, sticky="ew")

        # Status bar (shortcuts + safety tip)
        status = ttk.Frame(self, padding=(12, 6))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        IS_MAC = sys.platform == "darwin"
        def acc(s: str) -> str:
            return s.replace("Ctrl", "⌘").replace("Alt", "⌥").replace("Shift", "⇧") if IS_MAC else s

        # shortcuts_text = f"Shortcuts: F5 Run, Esc Stop, Del Delete, {acc('Ctrl+Shift+D')} Duplicate, {acc('Ctrl+↑/↓')} Move, {acc('Ctrl+E')} Edit Repeat, {acc('Ctrl+S')} Save, {acc('Ctrl+O')} Load, {acc('Ctrl+R')} Record"
        # ttk.Label(status, text=shortcuts_text, foreground="#666").grid(row=0, column=0, sticky="w")
        ttk.Label(status, text="Tip: Move mouse to TOP-LEFT corner to abort while running.", foreground="#0a7").grid(row=0, column=1, sticky="e", padx=(8,0))

        # Bind keyboard shortcuts last (widgets exist now)
        self._bind_shortcuts()

        def _lock_right_width():
            right.update_idletasks()
            split.columnconfigure(1, minsize=right.winfo_reqwidth())

        self.after(0, _lock_right_width)

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
        ttk.Button(tab, text="Add Click Action", command=self.add_click)\
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

        ttk.Button(tab, text="Add Wait Action", command=self.add_wait)\
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

        ttk.Button(tab, text="Add Key Action", command=self.add_key)\
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

        ttk.Button(tab, text="Add Move Action", command=self.add_move)\
            .grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))

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
            ("Delete selected", "Del"),
            ("Duplicate selected", acc("Ctrl+Shift+D")),
            ("Move selected", acc("Ctrl+↑ / Ctrl+↓")),
            ("Edit repeat", acc("Ctrl+E")),
            ("Save sequence", acc("Ctrl+S")),
            ("Load sequence", acc("Ctrl+O")),
            ("Start/Stop recording", acc("Ctrl+R")),
        ]
        for i, (name, keys) in enumerate(rows):
            ttk.Label(frm, text=name).grid(row=i, column=0, sticky="w", padx=(0, 18), pady=4)
            ttk.Label(frm, text=keys, foreground="#444").grid(row=i, column=1, sticky="w", pady=4)
        ttk.Button(frm, text="Close", command=dlg.destroy).grid(row=len(rows), column=0, columnspan=2, pady=(12,0))

    # ---------- Action add helpers ----------
    def add_click(self):
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
        self.actions.append(a)
        self.refresh_list()

    def add_wait(self):
        a = Action(
            kind="wait",
            name=self.wname.get().strip(),
            repeats=max(1, int(self.wrepeats.get())),
            seconds=max(0.0, float(self.wseconds.get()))
        )
        self.actions.append(a)
        self.refresh_list()

    def add_key(self):
        mode = self.kmode.get()
        keys = self.kkeys.get().strip()
        if not keys:
            messagebox.showerror("Invalid input", "Please enter a key name (e.g., 'enter') or text to type.")
            return
        a = Action(kind="key", 
                   name=self.kname.get().strip(),
                   repeats=max(1, int(self.krepeats.get())), 
                   key_mode=mode, keys=keys)
        self.actions.append(a)
        self.refresh_list()

    def add_move(self):
        a = Action(
            kind="move",
            name=self.mname.get().strip(),
            repeats=max(1, int(self.mrepeats.get())),
            x=int(self.mx.get()),
            y=int(self.my.get()),
            move_duration=max(0.0, float(self.mdur.get()))
        )
        self.actions.append(a)
        self.refresh_list()

    # ---------- List management ----------
    def refresh_list(self):
        self.lst.delete(0, tk.END)
        for i, a in enumerate(self.actions):
            self.lst.insert(tk.END, f"{i+1}. {self.describe(a)}")

    def describe(self, a: Action) -> str:
        rep = f" ×{a.repeats}" if a.repeats > 1 else ""
        label = f"[{a.name}] " if a.name.strip() else ""
        if a.kind == "click":
            return f"{label}Click({a.button}) @({a.x},{a.y}) clicks={a.clicks} interval={a.interval}s{rep}"
        if a.kind == "wait":
            return f"{label}Wait {a.seconds}s{rep}"
        if a.kind == "key":
            d = f'Type "{a.keys}"' if a.key_mode == "type" else f"Key press: {a.keys}"
            return f"{label}{d}{rep}"
        if a.kind == "move":
            return f"{label}Move @({a.x},{a.y}) over {a.move_duration}s{rep}"
        return str(a)
    
    def edit_name_selected(self):
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
            a.name = var.get().strip()
            self.refresh_list()
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
        sel = self.lst.curselection()
        if not sel:
            return
        del self.actions[sel[0]]
        self.refresh_list()

    def duplicate_item(self):
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        self.actions.insert(idx + 1, Action(**asdict(self.actions[idx])))
        self.refresh_list()
        self.lst.selection_set(idx + 1)

    def clear_items(self):
        if messagebox.askyesno("Confirm", "Clear all actions?"):
            self.actions.clear()
            self.refresh_list()

    def edit_repeat_selected(self):
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        a = self.actions[idx]

        dlg = tk.Toplevel(self)
        dlg.title("Edit Repeat")
        dlg.grab_set()
        ttk.Label(dlg, text="Repeat (per-action):").grid(row=0, column=0, padx=10, pady=10)
        var = tk.IntVar(value=a.repeats)
        ttk.Entry(dlg, width=8, textvariable=var).grid(row=0, column=1, padx=10, pady=10)
        def ok():
            try:
                a.repeats = max(1, int(var.get()))
                self.refresh_list()
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
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Save Sequence"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(a) for a in self.actions], f, indent=2)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def load_sequence(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Load Sequence"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.actions = [Action(**item) for item in data]
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not load file:\n{e}")

    # ---------- Recording ----------
    def start_recording(self):
        if self.is_running():
            messagebox.showwarning("Busy", "Stop the running sequence before recording.")
            return
        if self.is_recording:
            return

        # 3-second countdown
        self.rec_status.config(text="Recording starts in 3…")
        self.btn_rec.config(state="disabled")
        self.btn_rec_stop.config(state="disabled")

        def start_after_countdown(n=3):
            if n == 0:
                self._begin_mouse_listener()
                return
            self.rec_status.config(text=f"Recording starts in {n}…")
            self.after(1000, lambda: start_after_countdown(n - 1))

        start_after_countdown(3)

    def _begin_mouse_listener(self):
        self.is_recording = True
        self.last_record_ts = None
        self.rec_status.config(text="Recording…")
        self.btn_rec_stop.config(state="normal")

        def on_click(x, y, button, pressed):
            if not self.is_recording:
                return False  # stop listener
            if not pressed:
                return  # only on press

            # Insert wait (gap since last)
            now = time.time()
            if self.rec_insert_waits_var.get() and self.last_record_ts is not None:
                gap = now - self.last_record_ts
                if gap >= float(self.rec_min_wait_var.get()):
                    self._append_action_threadsafe(Action(kind="wait", seconds=round(gap, 3), repeats=1))
            self.last_record_ts = now

            # Map button
            bname = "left"
            try:
                bname = str(button).split(".")[-1].lower()
            except Exception:
                pass

            # Recorded per-action repeats
            rep = max(1, int(self.rec_repeats_var.get()))
            a = Action(kind="click", x=int(x), y=int(y), button=bname, clicks=1, interval=0.0, repeats=rep)
            self._append_action_threadsafe(a)

        self.mouse_listener = mouse.Listener(on_click=on_click)
        self.mouse_listener.start()

    def _append_action_threadsafe(self, action: Action):
        def _do():
            self.actions.append(action)
            self.refresh_list()
            self.lst.selection_clear(0, tk.END)
            self.lst.selection_set(tk.END)
            self.lst.see(tk.END)
        self.after(0, _do)

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self.mouse_listener is not None:
            try:
                self.mouse_listener.stop()
            except Exception:
                pass
            self.mouse_listener = None
        self.rec_status.config(text="Ready")
        self.btn_rec.config(state="normal")
        self.btn_rec_stop.config(state="disabled")

    # ---------- Running ----------
    def is_running(self) -> bool:
        return bool(self.run_thread and self.run_thread.is_alive())

    def request_stop(self):
        self.stop_flag.set()

    def start_run(self):
        if self.is_recording:
            messagebox.showwarning("Recording active", "Stop recording before running.")
            return
        if not self.actions:
            messagebox.showerror("No actions", "Add at least one action.")
            return
        try:
            repeats = max(1, int(self.repeat_var.get()))
            start_delay = max(0.0, float(self.start_delay_var.get()))
        except Exception:
            messagebox.showerror("Invalid settings", "Repeat count and start delay must be numbers.")
            return
        if self.is_running():
            messagebox.showwarning("Already running", "Wait for the current run to finish or press Stop.")
            return

        self.stop_flag.clear()
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        # recording buttons live in Click tab; disable Start during run
        try:
            self.btn_rec.config(state="disabled")
            self.btn_rec_stop.config(state="disabled")
        except Exception:
            pass

        self.run_thread = threading.Thread(target=self._run_sequence, args=(repeats, start_delay), daemon=True)
        self.run_thread.start()

    def _run_sequence(self, repeats: int, start_delay: float):
        try:
            if start_delay > 0:
                for i in range(int(start_delay), 0, -1):
                    self.btn_run.config(text=f"Starting in {i}…")
                    time.sleep(1)
                    if self.stop_flag.is_set():
                        raise RuntimeError("Stopped")
                leftover = start_delay - int(start_delay)
                if leftover > 0:
                    time.sleep(leftover)
                self.btn_run.config(text="Run")

            for _ in range(repeats):
                if self.stop_flag.is_set():
                    raise RuntimeError("Stopped")
                for a in self.actions:
                    if self.stop_flag.is_set():
                        raise RuntimeError("Stopped")
                    for __ in range(max(1, int(a.repeats))):
                        self._execute_action(a)
                time.sleep(0.001)

            messagebox.showinfo("Done", f"Finished {repeats} loop(s).")
        except Exception as e:
            msg = "Stopped." if str(e).lower().startswith("stopped") else f"Stopped: {e}"
            messagebox.showwarning("Aborted", msg)
        finally:
            self.btn_run.config(state="normal", text="Run")
            self.btn_stop.config(state="disabled")
            try:
                self.btn_rec.config(state="normal")
                self.btn_rec_stop.config(state="disabled")
            except Exception:
                pass

    def _execute_action(self, a: Action):
        if a.kind == "click":
            if a.x is not None and a.y is not None:
                pag.moveTo(a.x, a.y, duration=0)
            pag.click(clicks=a.clicks, interval=a.interval, button=a.button)

        elif a.kind == "wait":
            time.sleep(max(0.0, a.seconds))

        elif a.kind == "key":
            if a.key_mode == "type":
                pag.typewrite(a.keys)
            else:
                combo = [k.strip() for k in a.keys.split("+") if k.strip()]
                if len(combo) == 1:
                    pag.press(combo[0])
                else:
                    pag.hotkey(*combo)

        elif a.kind == "move":
            if a.x is not None and a.y is not None:
                pag.moveTo(a.x, a.y, duration=max(0.0, a.move_duration))


if __name__ == "__main__":
    app = MacroRunnerApp()
    try:
        app.iconbitmap(resource_path("macro_runner_icon.ico"))
    except Exception:
        # Optional fallback: if you also ship a PNG, you can use iconphoto
        # from tkinter import PhotoImage
        # app.iconphoto(True, PhotoImage(file=resource_path("macro_runner_icon.png")))
        pass
    app.mainloop()
