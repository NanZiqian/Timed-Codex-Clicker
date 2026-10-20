"""Settings, and the move-window / paste / click sequence that runs when the timer fires."""
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field, fields

import winctl

# Friendly names for coding-agent apps, keyed by lower-case exe name. Anything else is named after its exe.
KNOWN_AGENTS = {
    "chatgpt.exe": "Codex (ChatGPT)",
    "codex.exe": "Codex",
    "claude.exe": "Claude",
    "cursor.exe": "Cursor",
    "windsurf.exe": "Windsurf",
    "code.exe": "VS Code",
    "zed.exe": "Zed",
    "windowsterminal.exe": "Windows Terminal",
}
MAX_STABLE_TITLE = 30  # longer titles usually carry a document or conversation name that changes


def agent_name(exe, title=""):
    known = KNOWN_AGENTS.get(exe.lower())
    if known:
        return known
    return os.path.splitext(exe)[0] or title or "Window"


def title_filter(title):
    """Title text to match on, or "" (match on the exe alone) when the title looks like it changes."""
    return title if len(title) <= MAX_STABLE_TITLE else ""


class SequenceError(Exception):
    pass


@dataclass
class Target:
    """One coding-agent window: how to find it, where it lives, and where to click inside it."""
    exe: str = ""
    title: str = ""  # substring match
    rect: list = None  # preset window position and size: x, y, w, h
    prompt_pt: list = None  # prompt box, offset from the window's top-left corner
    start_pt: list = None  # Start button, offset from the window's top-left corner

    def calibrated(self):
        return bool(self.rect and self.prompt_pt and self.start_pt and (self.exe or self.title))


@dataclass
class Settings:
    prompt: str = ""
    mode: str = "countdown"  # "countdown" or "clock"
    when: str = ""
    buffer_s: int = 60
    keep_awake: bool = True
    clear_first: bool = True
    paste_wait_s: float = 1.0
    shutdown_on: bool = False
    shutdown_after_min: int = 120  # minutes after clicking Start
    hotkey: str = "alt+s"  # pressed just before shutting down; empty = none
    force_shutdown: bool = False
    profile: str = ""
    profiles: dict = field(default_factory=dict)  # name -> Target

    @property
    def target(self):
        return self.profiles.get(self.profile)

    def calibrated(self):
        return bool(self.target and self.target.calibrated())

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        if "win_exe" in raw:  # settings from before profiles existed: one target stored flat
            name = agent_name(raw["win_exe"], raw.get("win_title", ""))
            raw["profile"] = name
            raw["profiles"] = {name: {"exe": raw["win_exe"], "title": raw.get("win_title", ""), "rect": raw.get("win_rect"),
                                      "prompt_pt": raw.get("prompt_pt"), "start_pt": raw.get("start_pt")}}
        known = {f.name for f in fields(cls)}
        target_fields = {f.name for f in fields(Target)}
        settings = cls(**{k: v for k, v in raw.items() if k in known and k != "profiles"})
        for name, t in (raw.get("profiles") or {}).items():
            settings.profiles[name] = Target(**{k: v for k, v in t.items() if k in target_fields})
        return settings

    def save(self, path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)


def _check_covering(hwnd, x, y, what):
    """Refuse to click unless the target window is what's under the pointer (avoids pasting/clicking into the wrong app)."""
    for _ in range(4):
        if winctl.root_window_at(x, y) == hwnd:
            return
        time.sleep(0.3)
    other = winctl.describe(winctl.root_window_at(x, y) or hwnd)
    raise SequenceError(f"{what} point ({x}, {y}) is covered by another window ({other.exe} - {other.title!r}); nothing was clicked")


def run_sequence(s, dry_run=False, log=print):
    """Move the target window to its preset, paste the prompt, then click Start (unless dry_run)."""
    t = s.target
    if not t or not t.calibrated():
        raise SequenceError("calibration is incomplete: capture the window, the prompt box and the Start button")
    if not s.prompt.strip():
        raise SequenceError("the prompt is empty")
    if winctl.session_locked():
        raise SequenceError("the screen is locked, so clicks can't reach the app")

    info = winctl.find_window(t.exe, t.title)
    if not info:
        raise SequenceError(f"no visible window found for {t.exe or '*'} with title containing {t.title!r}")
    hwnd = info.hwnd
    log(f"Found window {info.exe} - {info.title!r}")

    winctl.place_window(hwnd, t.rect)
    time.sleep(0.8)  # let the app lay itself out at the new size
    winctl.raise_window(hwnd)
    time.sleep(0.3)
    x0, y0, w, h = winctl.window_rect(hwnd)
    log(f"Window at {x0},{y0} size {w}x{h}")
    if (w, h) != tuple(t.rect[2:]):
        log(f"WARNING: window is {w}x{h} but the preset is {t.rect[2]}x{t.rect[3]}; the clicks may be off")

    px, py = x0 + t.prompt_pt[0], y0 + t.prompt_pt[1]
    sx, sy = x0 + t.start_pt[0], y0 + t.start_pt[1]

    _check_covering(hwnd, px, py, "prompt box")
    winctl.click(px, py)
    time.sleep(0.3)
    if s.clear_first:
        winctl.key_chord(winctl.VK_CONTROL, winctl.VK_A)
        time.sleep(0.15)
    winctl.set_clipboard(s.prompt)
    winctl.key_chord(winctl.VK_CONTROL, winctl.VK_V)
    log(f"Pasted {len(s.prompt)} characters")
    time.sleep(s.paste_wait_s)

    _check_covering(hwnd, sx, sy, "Start button")
    if dry_run:
        winctl.move_cursor(sx, sy)
        log("Test run: stopped on the Start button without clicking")
        return
    winctl.click(sx, sy)
    log("Clicked Start")


def shutdown_computer(force=False, run=subprocess.run):
    """Shut Windows down now. Without force, an app with unsaved work can hold the shutdown up."""
    cmd = ["shutdown", "/s", "/t", "0"] + (["/f"] if force else [])
    run(cmd, check=True, creationflags=0x08000000)  # CREATE_NO_WINDOW
