"""Timed clicker: wait for a coding agent's usage limit to reset, then paste the prompt and click Start."""
import os
import sys
import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import timeparse
import winctl
from sequence import SequenceError, Target, Settings, agent_name, run_sequence, shutdown_computer, title_filter

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
SHUTDOWN_WARN_S = 30  # visible countdown, with Cancel, before the hotkey and shutdown
HOTKEY_SETTLE_MS = 5000  # pause between the hotkey and the shutdown, for the background app to react
RED = "#b91c1c"
GREEN = "#15803d"


class App:
    def __init__(self, root):
        self.root = root
        self.s = Settings.load(CONFIG_PATH)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.fire_at = None  # epoch seconds while armed, waiting to click Start
        self.shutdown_at = None  # epoch seconds while waiting to shut down after Start was clicked
        self.warning = False  # in the final shutdown countdown
        self.tick_job = None
        root.title("Timed Clicker")
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        self.build()
        self.refresh_profiles()
        self.preview()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def px(self, n):
        return int(n * self.scale)

    def active(self):
        return self.fire_at is not None or self.shutdown_at is not None or self.warning

    # --- layout ------------------------------------------------------------

    def build(self):
        p = self.px(8)
        main = ttk.Frame(self.root, padding=p)
        main.pack(fill="both", expand=True)

        cal = ttk.LabelFrame(main, text="1 · Target app and calibration", padding=p)
        cal.pack(fill="x")
        cal.columnconfigure((0, 1, 2), weight=1)
        ttk.Label(cal, text="Target agent:").grid(row=0, column=0, sticky="w")
        self.profile_box = ttk.Combobox(cal, state="readonly")
        self.profile_box.grid(row=0, column=1, sticky="ew", padx=(p, 0))
        self.profile_box.bind("<<ComboboxSelected>>", lambda _: self.select_profile(self.profile_box.get()))
        ttk.Button(cal, text="Delete", command=self.delete_profile).grid(row=0, column=2, sticky="ew", padx=(p, 0))
        self.cal_lbl = ttk.Label(cal, justify="left")
        self.cal_lbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(p, 0))
        buttons = [("window", "Capture window"), ("prompt", "Capture prompt box"), ("start", "Capture Start button")]
        for i, (what, text) in enumerate(buttons):
            ttk.Button(cal, text=text, command=lambda w=what: self.begin_capture(w)).grid(
                row=2, column=i, sticky="ew", padx=(0 if i == 0 else p, 0), pady=(p, 0))
        ttk.Label(cal, text="Window title contains:").grid(row=3, column=0, sticky="w", pady=(p, 0))
        self.title_var = tk.StringVar()
        ttk.Entry(cal, textvariable=self.title_var).grid(row=3, column=1, columnspan=2, sticky="ew", padx=(p, 0), pady=(p, 0))
        ttk.Button(cal, text="Move window to preset", command=self.move_to_preset).grid(row=4, column=0, sticky="ew", pady=(p, 0))
        ttk.Button(cal, text="Test (stops before Start)", command=lambda: self.fire(dry_run=True)).grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(p, 0), pady=(p, 0))

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
        self.prompt_txt = tk.Text(prompt, height=4, width=64, wrap="word", font=("Segoe UI", 10), undo=True)
        self.prompt_txt.pack(fill="both", expand=True)
        self.prompt_txt.insert("1.0", self.s.prompt)

        after = ttk.LabelFrame(main, text="4 · After Start is clicked (optional)", padding=p)
        after.pack(fill="x", pady=(p, 0))
        after.columnconfigure(3, weight=1)
        self.shut_var = tk.BooleanVar(value=self.s.shutdown_on)
        self.shut_min_var = tk.StringVar(value=str(self.s.shutdown_after_min))
        self.hotkey_var = tk.StringVar(value=self.s.hotkey)
        self.force_var = tk.BooleanVar(value=self.s.force_shutdown)
        ttk.Checkbutton(after, text="Shut down the PC", variable=self.shut_var).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(after, from_=1, to=2880, increment=10, width=6, textvariable=self.shut_min_var).grid(row=0, column=1, padx=(p, 0))
        ttk.Label(after, text="minutes after clicking Start").grid(row=0, column=2, columnspan=2, sticky="w", padx=(p // 2, 0))
        ttk.Label(after, text="Press hotkey first:").grid(row=1, column=0, sticky="w", pady=(p, 0))
        ttk.Entry(after, textvariable=self.hotkey_var, width=14).grid(row=1, column=1, columnspan=2, sticky="w", padx=(p, 0), pady=(p, 0))
        ttk.Button(after, text="Test hotkey (in 3 s)", command=self.test_hotkey).grid(row=1, column=3, sticky="e", pady=(p, 0))
        ttk.Checkbutton(after, text="Force-close apps that block shutdown (may lose unsaved work)",
                        variable=self.force_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(p, 0))
        ttk.Label(after, text=f"The PC stays awake until then. You get a {SHUTDOWN_WARN_S}s warning with a Cancel button.",
                  foreground="#555").grid(row=3, column=0, columnspan=4, sticky="w", pady=(p // 2, 0))

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
        self.disarm_btn = ttk.Button(actions, text="Disarm", command=self.on_disarm, state="disabled")
        self.disarm_btn.grid(row=0, column=1, sticky="ew", padx=(p, 0))
        ttk.Button(actions, text="Run now (clicks Start!)", command=self.run_now).grid(row=0, column=2, sticky="ew", padx=(p, 0))

        self.status_var = tk.StringVar(value="Not armed")
        self.status_lbl = ttk.Label(main, textvariable=self.status_var, font=("Segoe UI", 12, "bold"), justify="left")
        self.status_lbl.pack(fill="x", pady=(p, 0))
        self.log_txt = scrolledtext.ScrolledText(main, height=3, width=64, state="disabled", font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True, pady=(p // 2, 0))

        self.locked_while_armed = [self.disarm_btn, self.log_txt]
        self.main = main

        # Open near the top-left of the screen so the whole form is visible and out of the way of the target app.
        self.root.update_idletasks()
        y = max(0, min(self.px(30), self.root.winfo_screenheight() - self.root.winfo_reqheight() - self.px(60)))
        self.root.geometry(f"+{self.px(40)}+{y}")

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

    def schedule(self, ms, fn, *args):
        """Every timed step goes through one slot so a single cancel stops whatever is pending."""
        self.tick_job = self.root.after(ms, fn, *args)

    @staticmethod
    def number(text, default, cast=int):
        try:
            return cast(text)
        except ValueError:
            return default

    def sync_settings(self):
        s = self.s
        if s.target:
            s.target.title = self.title_var.get().strip()
        s.mode = self.mode_var.get()
        s.when = self.when_var.get().strip()
        s.buffer_s = self.number(self.buffer_var.get(), 60)
        s.clear_first = self.clear_var.get()
        s.keep_awake = self.awake_var.get()
        s.paste_wait_s = self.number(self.wait_var.get(), 1.0, float)
        s.shutdown_on = self.shut_var.get()
        s.shutdown_after_min = self.number(self.shut_min_var.get(), 120)
        s.hotkey = self.hotkey_var.get().strip()
        s.force_shutdown = self.force_var.get()
        s.prompt = self.prompt_txt.get("1.0", "end-1c")

    def save(self):
        self.sync_settings()
        try:
            self.s.save(CONFIG_PATH)
        except OSError as e:
            self.log(f"Could not save settings: {e}")

    # --- target profiles and calibration -----------------------------------

    def refresh_profiles(self):
        s = self.s
        self.profile_box.config(values=sorted(s.profiles))
        self.profile_box.set(s.profile if s.target else "")
        t = s.target
        self.title_var.set(t.title if t else "")
        if t and t.rect:
            x, y, w, h = t.rect
            win = f'Window: {t.exe}  preset {w}×{h} at {x},{y}'
        else:
            win = "Window: not captured. Open the agent app, then press Capture window."
        prompt = f"+{t.prompt_pt[0]},{t.prompt_pt[1]}" if t and t.prompt_pt else "not captured"
        start = f"+{t.start_pt[0]},{t.start_pt[1]}" if t and t.start_pt else "not captured"
        self.cal_lbl.config(text=f"{win}\nPrompt box: {prompt}     Start button: {start}")

    def select_profile(self, name):
        self.sync_settings()  # keeps the title filter typed for the profile we're leaving
        self.s.profile = name
        self.refresh_profiles()
        self.save()

    def delete_profile(self):
        name = self.s.profile
        if not name or not messagebox.askyesno("Timed Clicker", f"Delete the saved target {name!r}?"):
            return
        self.s.profiles.pop(name, None)
        self.s.profile = next(iter(sorted(self.s.profiles)), "")
        self.refresh_profiles()
        self.save()

    def begin_capture(self, what):
        label = {"window": "the agent window", "prompt": "the prompt box", "start": "the Start button"}[what]
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
            name = agent_name(info.exe, info.title)
            t = s.profiles.get(name) or Target()
            if t.rect and list(info.rect[2:]) != list(t.rect[2:]):
                t.prompt_pt = t.start_pt = None
                self.log("Window size changed, so the prompt box and Start button need capturing again")
            t.exe, t.rect = info.exe, list(info.rect)
            t.title = title_filter(info.title)
            s.profiles[name] = t
            s.profile = name
            self.log(f"Detected {name}: {info.exe} - {info.title!r} ({info.rect[2]}x{info.rect[3]} at {info.rect[0]},{info.rect[1]})")
            if not t.title:
                self.log("The window title looks like it changes, so it is matched on the program name only")
        else:
            t = s.target
            if not t or not t.rect:
                self.log("Capture the window first")
                return
            if info.exe.lower() != t.exe.lower():
                self.log(f"The cursor was over {info.exe}, not {t.exe} - try again")
                return
            if list(info.rect[2:]) != list(t.rect[2:]):
                self.log("WARNING: the window is not at its preset size; use 'Move window to preset' and capture again")
            offset = [x - info.rect[0], y - info.rect[1]]
            if what == "prompt":
                t.prompt_pt = offset
            else:
                t.start_pt = offset
            self.log(f"Captured {what} point at +{offset[0]},{offset[1]} from the window corner")
        self.refresh_profiles()
        self.save()

    def move_to_preset(self):
        self.sync_settings()
        t = self.s.target
        if not t or not t.rect:
            self.log("Capture the window first")
            return
        info = winctl.find_window(t.exe, t.title)
        if not info:
            self.log(f"No visible window found for {t.exe} / {t.title!r}")
            return
        winctl.place_window(info.hwnd, t.rect)
        winctl.raise_window(info.hwnd)
        self.log(f"Moved {info.exe} - {info.title!r} to its preset position")

    # --- scheduling --------------------------------------------------------

    def resolve(self):
        self.sync_settings()
        return timeparse.resolve_target(self.s.mode, self.s.when, datetime.now(), self.s.buffer_s)

    def preview(self):
        if self.active():
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
        if self.s.shutdown_on:
            if self.s.shutdown_after_min < 1:
                return "Shutdown delay must be at least 1 minute."
            if self.s.hotkey:
                try:
                    winctl.parse_hotkey(self.s.hotkey)
                except ValueError as e:
                    return str(e)
        return None

    def confirm_shutdown(self):
        s = self.s
        if not s.shutdown_on:
            return True
        hotkey = f"press {s.hotkey}, then " if s.hotkey else ""
        force = "\n\nForce-close is ON: apps with unsaved work will be closed without asking." if s.force_shutdown else ""
        return messagebox.askyesno(
            "Timed Clicker",
            f"{s.shutdown_after_min} minutes after Start is clicked this PC will {hotkey}shut down.{force}\n\nContinue?")

    def arm(self):
        self.sync_settings()
        issue = self.problem()
        if issue:
            messagebox.showerror("Can't arm", issue)
            return
        if not self.confirm_shutdown():
            return
        self.fire_at = self.resolve().timestamp()
        self.save()
        if self.s.keep_awake:
            winctl.keep_awake(True)
        self.set_editing(False)
        self.log(f"Armed for {datetime.fromtimestamp(self.fire_at):%a %d %b %H:%M:%S}")
        self.tick()

    def run_now(self):
        self.sync_settings()
        if self.confirm_shutdown():
            self.fire()

    def on_disarm(self):
        self.log("Cancelled" if self.fire_at else "Shutdown cancelled")
        self.cancel_all()

    def cancel_all(self, message="Not armed"):
        if self.tick_job:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        self.fire_at = self.shutdown_at = None
        self.warning = False
        winctl.keep_awake(False)
        self.set_editing(True)
        self.disarm_btn.config(text="Disarm")
        self.status(message)
        self.preview()

    def tick(self):
        left = self.fire_at - time.time()
        if left <= 0:
            self.fire()
            return
        when = datetime.fromtimestamp(self.fire_at)
        self.status(f"Armed - fires {when:%a %H:%M:%S}\n{timeparse.format_remaining(left)} left", GREEN)
        self.schedule(500 if left < 120 else 1000, self.tick)

    # --- firing ------------------------------------------------------------

    def fire(self, dry_run=False, attempt=1):
        armed = self.fire_at is not None
        self.save()
        if armed and winctl.session_locked() and time.time() < self.fire_at + UNLOCK_WAIT_S:
            self.status("Time reached, but the screen is locked.\nWaiting for you to unlock it...", RED)
            self.schedule(2000, self.fire, dry_run, attempt)
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
            self.schedule(RETRY_WAIT_MS, self.fire, dry_run, attempt + 1)
            return
        if error:
            if armed:
                self.cancel_all()
            self.log(f"FAILED: {error}")
            self.status("Failed - see the log", RED)
            self.beep(300, 500)
            messagebox.showerror("Timed Clicker", error)
        elif dry_run:
            self.status("Test finished - cursor is on the Start button", GREEN)
        elif self.s.shutdown_on:
            self.begin_wait()
        else:
            if armed:
                self.cancel_all()
            self.status(f"Done at {datetime.now():%H:%M:%S}", GREEN)

    # --- after Start: wait, hotkey, shutdown -------------------------------

    def begin_wait(self):
        self.fire_at = None
        self.shutdown_at = time.time() + self.s.shutdown_after_min * 60
        winctl.keep_awake(True)  # the task is running now; sleeping would kill it whatever the checkbox says
        self.set_editing(False)
        self.disarm_btn.config(text="Cancel shutdown")
        self.log(f"Start clicked. Shutting down at {datetime.fromtimestamp(self.shutdown_at):%a %H:%M:%S}")
        self.wait_tick()

    def wait_tick(self):
        left = self.shutdown_at - time.time()
        if left <= 0:
            self.warn_tick(SHUTDOWN_WARN_S)
            return
        at = datetime.fromtimestamp(self.shutdown_at)
        self.status(f"Task running - shutdown at {at:%a %H:%M:%S}\n{timeparse.format_remaining(left)} left", GREEN)
        self.schedule(1000, self.wait_tick)

    def warn_tick(self, n):
        if n <= 0:
            self.press_hotkey_then_shutdown()
            return
        self.warning = True
        self.status(f"SHUTTING DOWN in {n}s\nPress Cancel shutdown to stop it", RED)
        self.beep(700, 80)
        self.schedule(1000, self.warn_tick, n - 1)

    def press_hotkey(self, then=None):
        """Bring this window to the front (so the keys don't land in the agent app), then press the hotkey."""
        vks = winctl.parse_hotkey(self.s.hotkey)
        self.root.deiconify()
        winctl.force_foreground(winctl.top_level_of(self.root.winfo_id()))
        self.schedule(400, self.send_hotkey, vks, then)  # let the window take focus first

    def send_hotkey(self, vks, then):
        try:
            foreground = winctl.foreground_exe()
            winctl.key_chord(*vks, hold=0.15)
            self.log(f"Pressed {self.s.hotkey} (foreground app: {foreground})")
        except Exception as e:
            self.log(f"Hotkey failed: {e}")
        if then:
            self.status("Hotkey sent - shutting down...", RED)
            self.schedule(HOTKEY_SETTLE_MS, then)

    def press_hotkey_then_shutdown(self):
        self.warning = False
        if not self.s.hotkey:
            self.issue_shutdown()
            return
        try:
            self.press_hotkey(then=self.issue_shutdown)
        except Exception as e:
            self.log(f"Hotkey failed: {e}")
            self.issue_shutdown()

    def issue_shutdown(self):
        try:
            shutdown_computer(self.s.force_shutdown)
        except Exception as e:
            self.log(f"FAILED to shut down: {e}")
            self.cancel_all("Shutdown failed - see the log")
            messagebox.showerror("Timed Clicker", f"Could not shut down: {e}")
            return
        self.log("Shutdown requested")
        self.cancel_all("Shutdown requested - the PC is shutting down")

    def test_hotkey(self):
        self.sync_settings()
        try:
            winctl.parse_hotkey(self.s.hotkey)
        except ValueError as e:
            messagebox.showerror("Hotkey", str(e))
            return
        self.log(f"Pressing {self.s.hotkey} in 3 seconds")
        self.schedule(3000, self.press_hotkey)

    def on_close(self):
        if self.active() and not messagebox.askyesno("Timed Clicker", "Something is scheduled. Quit and cancel it?"):
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
