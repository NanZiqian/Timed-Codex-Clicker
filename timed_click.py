"""Timed clicker: wait for the Codex 5h limit to reset, then paste the prompt and click Start."""
import os
import sys
import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import timeparse
import winctl
from sequence import SequenceError, Settings, run_sequence

try:
    import winsound
except ImportError:
    winsound = None

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "timed_click.log")

CAPTURE_SECONDS = 5
MAX_ATTEMPTS = 3
RETRY_WAIT_MS = 20_000
UNLOCK_WAIT_S = 3600  # how long past the fire time to keep waiting for the screen to be unlocked
RED = "#b91c1c"
GREEN = "#15803d"


class App:
    def __init__(self, root):
        self.root = root
        self.s = Settings.load(CONFIG_PATH)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.fire_at = None  # epoch seconds while armed
        self.tick_job = None
        root.title("Timed Clicker")
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        self.build()
        self.refresh_calibration()
        self.preview()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def px(self, n):
        return int(n * self.scale)

    # --- layout ------------------------------------------------------------

    def build(self):
        p = self.px(8)
        main = ttk.Frame(self.root, padding=p)
        main.pack(fill="both", expand=True)

        cal = ttk.LabelFrame(main, text="1 · Calibrate", padding=p)
        cal.pack(fill="x")
        cal.columnconfigure((0, 1, 2), weight=1)
        self.cal_lbl = ttk.Label(cal, justify="left")
        self.cal_lbl.grid(row=0, column=0, columnspan=3, sticky="w")
        buttons = [("window", "Capture window"), ("prompt", "Capture prompt box"), ("start", "Capture Start button")]
        for i, (what, text) in enumerate(buttons):
            ttk.Button(cal, text=text, command=lambda w=what: self.begin_capture(w)).grid(
                row=1, column=i, sticky="ew", padx=(0 if i == 0 else p, 0), pady=(p, 0))
        ttk.Label(cal, text="Window title contains:").grid(row=2, column=0, sticky="w", pady=(p, 0))
        self.title_var = tk.StringVar(value=self.s.win_title)
        ttk.Entry(cal, textvariable=self.title_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(p, 0), pady=(p, 0))
        ttk.Button(cal, text="Move window to preset", command=self.move_to_preset).grid(row=3, column=0, sticky="ew", pady=(p, 0))
        ttk.Button(cal, text="Test (stops before Start)", command=lambda: self.fire(dry_run=True)).grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(p, 0), pady=(p, 0))

        when = ttk.LabelFrame(main, text="2 · When to start", padding=p)
        when.pack(fill="x", pady=(p, 0))
        when.columnconfigure(1, weight=1)
        self.mode_var = tk.StringVar(value=self.s.mode)
        ttk.Radiobutton(when, text="Countdown from now  (e.g. 2h 14m)", value="countdown",
                        variable=self.mode_var, command=self.preview).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(when, text="Clock time  (e.g. 18:45 or 6:45 PM)", value="clock",
                        variable=self.mode_var, command=self.preview).grid(row=1, column=0, columnspan=2, sticky="w")
        self.when_var = tk.StringVar(value=self.s.when)
        self.when_var.trace_add("write", lambda *_: self.preview())
        ttk.Entry(when, textvariable=self.when_var).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(p, 0))
        self.buffer_var = tk.StringVar(value=str(self.s.buffer_s))
        self.buffer_var.trace_add("write", lambda *_: self.preview())
        ttk.Label(when, text="Extra seconds after the reset:").grid(row=3, column=0, sticky="w", pady=(p, 0))
        ttk.Spinbox(when, from_=0, to=3600, increment=15, width=6, textvariable=self.buffer_var).grid(
            row=3, column=1, sticky="w", padx=(p, 0), pady=(p, 0))
        self.preview_lbl = ttk.Label(when)
        self.preview_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(p, 0))

        prompt = ttk.LabelFrame(main, text="3 · Prompt to paste", padding=p)
        prompt.pack(fill="both", expand=True, pady=(p, 0))
        self.prompt_txt = tk.Text(prompt, height=5, width=64, wrap="word", font=("Segoe UI", 10), undo=True)
        self.prompt_txt.pack(fill="both", expand=True)
        self.prompt_txt.insert("1.0", self.s.prompt)

        opts = ttk.Frame(main)
        opts.pack(fill="x", pady=(p, 0))
        self.clear_var = tk.BooleanVar(value=self.s.clear_first)
        self.awake_var = tk.BooleanVar(value=self.s.keep_awake)
        self.wait_var = tk.StringVar(value=f"{self.s.paste_wait_s:g}")
        ttk.Checkbutton(opts, text="Clear box first (Ctrl+A)", variable=self.clear_var).pack(side="left")
        ttk.Checkbutton(opts, text="Keep PC awake while armed", variable=self.awake_var).pack(side="left", padx=(p, 0))
        ttk.Label(opts, text="Wait after paste (s):").pack(side="left", padx=(p, 0))
        ttk.Spinbox(opts, from_=0.2, to=10, increment=0.2, width=5, textvariable=self.wait_var).pack(side="left", padx=(p // 2, 0))

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(p, 0))
        actions.columnconfigure((0, 1, 2), weight=1)
        self.arm_btn = ttk.Button(actions, text="Arm", command=self.arm)
        self.arm_btn.grid(row=0, column=0, sticky="ew")
        self.disarm_btn = ttk.Button(actions, text="Disarm", command=self.disarm, state="disabled")
        self.disarm_btn.grid(row=0, column=1, sticky="ew", padx=(p, 0))
        ttk.Button(actions, text="Run now (clicks Start!)", command=lambda: self.fire()).grid(
            row=0, column=2, sticky="ew", padx=(p, 0))

        self.status_var = tk.StringVar(value="Not armed")
        self.status_lbl = ttk.Label(main, textvariable=self.status_var, font=("Segoe UI", 12, "bold"), justify="left")
        self.status_lbl.pack(fill="x", pady=(p, 0))
        self.log_txt = scrolledtext.ScrolledText(main, height=4, width=64, state="disabled", font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True, pady=(p // 2, 0))

        self.locked_while_armed = [self.disarm_btn, self.log_txt]
        self.main = main

        # Open near the top-left of the screen so the whole form is visible and out of the way of the target app.
        self.root.update_idletasks()
        self.root.geometry(f"+{self.px(40)}+{self.px(30)}")

    def set_editing(self, enabled):
        """Grey out everything but Disarm and the log while armed."""
        def walk(widget):
            for child in widget.winfo_children():
                if child in self.locked_while_armed:
                    continue
                if isinstance(child, (ttk.Button, ttk.Entry, ttk.Radiobutton, ttk.Checkbutton, ttk.Spinbox)):
                    child.state(["!disabled"] if enabled else ["disabled"])
                elif isinstance(child, tk.Text):
                    child.config(state="normal" if enabled else "disabled")
                walk(child)
        walk(self.main)
        self.disarm_btn.state(["disabled"] if enabled else ["!disabled"])

    # --- small helpers -----------------------------------------------------

    def beep(self, freq=880, ms=120):
        if winsound:
            winsound.Beep(freq, ms)
        else:
            self.root.bell()

    def log(self, msg):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        self.log_txt.config(state="normal")
        self.log_txt.insert("end", line + "\n")
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
        except OSError:
            pass

    def status(self, text, color=None):
        self.status_var.set(text)
        self.status_lbl.config(foreground=color or "")

    @staticmethod
    def number(text, default, cast=int):
        try:
            return cast(text)
        except ValueError:
            return default

    def sync_settings(self):
        s = self.s
        s.win_title = self.title_var.get().strip()
        s.mode = self.mode_var.get()
        s.when = self.when_var.get().strip()
        s.buffer_s = self.number(self.buffer_var.get(), 60)
        s.clear_first = self.clear_var.get()
        s.keep_awake = self.awake_var.get()
        s.paste_wait_s = self.number(self.wait_var.get(), 1.0, float)
        s.prompt = self.prompt_txt.get("1.0", "end-1c")

    def save(self):
        self.sync_settings()
        try:
            self.s.save(CONFIG_PATH)
        except OSError as e:
            self.log(f"Could not save settings: {e}")

    # --- calibration -------------------------------------------------------

    def refresh_calibration(self):
        s = self.s
        if s.win_rect:
            x, y, w, h = s.win_rect
            win = f'Window: {s.win_exe}  "{s.win_title}"  preset {w}×{h} at {x},{y}'
        else:
            win = "Window: not captured"
        prompt = f"+{s.prompt_pt[0]},{s.prompt_pt[1]}" if s.prompt_pt else "not captured"
        start = f"+{s.start_pt[0]},{s.start_pt[1]}" if s.start_pt else "not captured"
        self.cal_lbl.config(text=f"{win}\nPrompt box: {prompt}     Start button: {start}")

    def begin_capture(self, what):
        label = {"window": "the Codex window", "prompt": "the prompt box", "start": "the Start button"}[what]
        self.sync_settings()
        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        lbl = tk.Label(overlay, text=f"Hover over {label}\ncapturing in {CAPTURE_SECONDS}…",
                       font=("Segoe UI", 14, "bold"), bg="#1f2937", fg="white", padx=16, pady=10)
        lbl.pack()
        overlay.update_idletasks()  # measure with the real text so the corner placement is right
        w, h = overlay.winfo_reqwidth(), overlay.winfo_reqheight()
        overlay.geometry(f"+{overlay.winfo_screenwidth() - w - self.px(24)}+{overlay.winfo_screenheight() - h - self.px(96)}")
        self.root.iconify()

        def step(n):
            if n == 0:
                x, y = winctl.cursor_pos()
                overlay.destroy()
                self.root.deiconify()
                self.beep(1200, 200)
                self.finish_capture(what, x, y)
                return
            lbl.config(text=f"Hover over {label}\ncapturing in {n}…")
            self.beep(600, 60)
            self.root.after(1000, step, n - 1)

        step(CAPTURE_SECONDS)

    def finish_capture(self, what, x, y):
        s = self.s
        hwnd = winctl.root_window_at(x, y)
        info = winctl.describe(hwnd) if hwnd else None
        if not info or info.pid == winctl.OWN_PID:
            self.log(f"Capture at {x},{y} found no other window under the cursor - try again")
            return
        if what == "window":
            if s.win_rect and list(info.rect[2:]) != list(s.win_rect[2:]):
                s.prompt_pt = s.start_pt = None
                self.log("Window size changed, so the prompt box and Start button need capturing again")
            s.win_exe, s.win_title, s.win_rect = info.exe, info.title, list(info.rect)
            self.title_var.set(info.title)
            self.log(f"Captured window {info.exe} - {info.title!r} ({info.rect[2]}x{info.rect[3]} at {info.rect[0]},{info.rect[1]})")
        else:
            if not s.win_rect:
                self.log("Capture the window first")
                return
            if info.exe.lower() != s.win_exe.lower():
                self.log(f"The cursor was over {info.exe}, not {s.win_exe} - try again")
                return
            if list(info.rect[2:]) != list(s.win_rect[2:]):
                self.log("WARNING: the window is not at its preset size; use 'Move window to preset' and capture again")
            offset = [x - info.rect[0], y - info.rect[1]]
            if what == "prompt":
                s.prompt_pt = offset
            else:
                s.start_pt = offset
            self.log(f"Captured {what} point at +{offset[0]},{offset[1]} from the window corner")
        self.refresh_calibration()
        self.save()

    def move_to_preset(self):
        self.sync_settings()
        if not self.s.win_rect:
            self.log("Capture the window first")
            return
        info = winctl.find_window(self.s.win_exe, self.s.win_title)
        if not info:
            self.log(f"No visible window found for {self.s.win_exe} / {self.s.win_title!r}")
            return
        winctl.place_window(info.hwnd, self.s.win_rect)
        winctl.raise_window(info.hwnd)
        self.log(f"Moved {info.exe} - {info.title!r} to its preset position")

    # --- scheduling --------------------------------------------------------

    def resolve(self):
        self.sync_settings()
        return timeparse.resolve_target(self.s.mode, self.s.when, datetime.now(), self.s.buffer_s)

    def preview(self):
        if self.fire_at:
            return
        try:
            t = self.resolve()
        except ValueError as e:
            self.preview_lbl.config(text=f"⚠ {e}", foreground=RED)
            return
        left = (t - datetime.now()).total_seconds()
        self.preview_lbl.config(text=f"Would fire {t:%a %d %b %H:%M:%S}  (in {timeparse.format_remaining(left)})", foreground="")

    def problem(self):
        if not self.s.calibrated():
            return "Calibrate first: capture the window, the prompt box and the Start button."
        if not self.s.prompt.strip():
            return "The prompt is empty."
        try:
            self.resolve()
        except ValueError as e:
            return str(e)
        return None

    def arm(self):
        self.sync_settings()
        issue = self.problem()
        if issue:
            messagebox.showerror("Can't arm", issue)
            return
        self.fire_at = self.resolve().timestamp()
        self.save()
        if self.s.keep_awake:
            winctl.keep_awake(True)
        self.set_editing(False)
        self.log(f"Armed for {datetime.fromtimestamp(self.fire_at):%a %d %b %H:%M:%S}")
        self.tick()

    def disarm(self, message="Not armed"):
        if self.tick_job:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        self.fire_at = None
        winctl.keep_awake(False)
        self.set_editing(True)
        self.status(message)
        self.preview()

    def tick(self):
        left = self.fire_at - time.time()
        if left <= 0:
            self.fire()
            return
        when = datetime.fromtimestamp(self.fire_at)
        self.status(f"Armed - fires {when:%a %H:%M:%S}\n{timeparse.format_remaining(left)} left", GREEN)
        self.tick_job = self.root.after(500 if left < 120 else 1000, self.tick)

    # --- firing ------------------------------------------------------------

    def fire(self, dry_run=False, attempt=1):
        armed = self.fire_at is not None
        self.save()
        if armed and winctl.session_locked() and time.time() < self.fire_at + UNLOCK_WAIT_S:
            self.status("Time reached, but the screen is locked.\nWaiting for you to unlock it...", RED)
            self.tick_job = self.root.after(2000, self.fire, dry_run, attempt)
            return
        self.status("Running...")
        self.root.iconify()
        self.root.update()
        time.sleep(0.5)
        error = None
        try:
            run_sequence(self.s, dry_run=dry_run, log=self.log)
        except SequenceError as e:
            error = str(e)
        except Exception:
            error = traceback.format_exc()
        self.root.deiconify()

        if error and armed and attempt < MAX_ATTEMPTS:
            self.log(f"FAILED (attempt {attempt}/{MAX_ATTEMPTS}): {error}")
            self.status(f"Failed - retrying in {RETRY_WAIT_MS // 1000}s ({attempt}/{MAX_ATTEMPTS})", RED)
            self.tick_job = self.root.after(RETRY_WAIT_MS, self.fire, dry_run, attempt + 1)
            return
        if armed:
            self.disarm()
        if error:
            self.log(f"FAILED: {error}")
            self.status("Failed - see the log", RED)
            self.beep(300, 500)
            messagebox.showerror("Timed Clicker", error)
        else:
            self.status("Test finished - cursor is on the Start button" if dry_run else f"Done at {datetime.now():%H:%M:%S}", GREEN)

    def on_close(self):
        if self.fire_at and not messagebox.askyesno("Timed Clicker", "It is armed. Quit and cancel the scheduled click?"):
            return
        self.save()
        winctl.keep_awake(False)
        self.root.destroy()


def main():
    if sys.platform != "win32":
        sys.exit("Timed Clicker only works on Windows.")
    winctl.enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
