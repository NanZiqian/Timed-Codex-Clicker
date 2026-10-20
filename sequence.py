"""Settings, and the move-window / paste / click sequence that runs when the timer fires."""
import json
import os
import time
from dataclasses import asdict, dataclass, fields

import winctl


class SequenceError(Exception):
    pass


@dataclass
class Settings:
    prompt: str = ""
    mode: str = "countdown"  # "countdown" or "clock"
    when: str = ""
    buffer_s: int = 60
    keep_awake: bool = True
    clear_first: bool = True
    paste_wait_s: float = 1.0
    win_exe: str = ""
    win_title: str = ""  # substring match
    win_rect: list = None  # preset window position and size: x, y, w, h
    prompt_pt: list = None  # prompt box, offset from the window's top-left corner
    start_pt: list = None  # Start button, offset from the window's top-left corner

    def calibrated(self):
        return bool(self.win_rect and self.prompt_pt and self.start_pt and (self.win_exe or self.win_title))

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

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
    if not s.calibrated():
        raise SequenceError("calibration is incomplete: capture the window, the prompt box and the Start button")
    if not s.prompt.strip():
        raise SequenceError("the prompt is empty")
    if winctl.session_locked():
        raise SequenceError("the screen is locked, so clicks can't reach the app")

    info = winctl.find_window(s.win_exe, s.win_title)
    if not info:
        raise SequenceError(f"no visible window found for {s.win_exe or '*'} with title containing {s.win_title!r}")
    hwnd = info.hwnd
    log(f"Found window {info.exe} - {info.title!r}")

    winctl.place_window(hwnd, s.win_rect)
    time.sleep(0.8)  # let the app lay itself out at the new size
    winctl.raise_window(hwnd)
    time.sleep(0.3)
    x0, y0, w, h = winctl.window_rect(hwnd)
    log(f"Window at {x0},{y0} size {w}x{h}")
    if (w, h) != tuple(s.win_rect[2:]):
        log(f"WARNING: window is {w}x{h} but the preset is {s.win_rect[2]}x{s.win_rect[3]}; the clicks may be off")

    px, py = x0 + s.prompt_pt[0], y0 + s.prompt_pt[1]
    sx, sy = x0 + s.start_pt[0], y0 + s.start_pt[1]

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
