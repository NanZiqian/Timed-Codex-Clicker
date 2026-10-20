"""End-to-end check against a fake "Codex" window (a text box and a Start button).

Run: python selftest.py
It moves the real mouse and types into the fake window for a few seconds - don't touch the mouse meanwhile.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk

import winctl
from sequence import SequenceError, Settings, Target, run_sequence

PROMPT = "Refactor the parser.\nSecond line with unicode: café ✓"
FAKE_TITLE = "FakeCodex 5h-limit test"


def fake_target(info_path, result_path, x, y):
    """The stand-in app: records what was pasted and whether Start was clicked."""
    winctl.enable_dpi_awareness()
    root = tk.Tk()
    root.title(FAKE_TITLE)
    root.geometry(f"700x500+{x}+{y}")
    box = tk.Text(root, height=12)
    box.pack(fill="both", expand=True, padx=10, pady=10)
    box.insert("1.0", "OLD TEXT THAT MUST BE REPLACED")

    def on_start():
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"text": box.get("1.0", "end-1c"), "clicked": True}, f)

    btn = tk.Button(root, text="Start", command=on_start)
    btn.pack(pady=(0, 10), ipadx=30, ipady=6)
    root.update()

    def center(w):
        return [w.winfo_rootx() + w.winfo_width() // 2, w.winfo_rooty() + w.winfo_height() // 2]

    with open(info_path, "w") as f:
        json.dump({"box": center(box), "start": center(btn)}, f)
    root.mainloop()


def cover_window(x, y, w, h):
    """A topmost window sitting on top of the target, to prove the safety check stops the click."""
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{w}x{h}+{x}+{y}")
    tk.Label(root, text="I'M IN THE WAY", font=("Segoe UI", 24)).pack(expand=True)
    root.mainloop()


def wait_for(path, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(path):
            time.sleep(0.2)
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        time.sleep(0.1)
    return None


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail and not ok else ''}")
    return ok


def main():
    winctl.enable_dpi_awareness()
    tmp = tempfile.mkdtemp(prefix="timedclick_")
    info_path, result_path = os.path.join(tmp, "info.json"), os.path.join(tmp, "result.json")
    procs = []
    results = []
    try:
        start_xy = (120, 120)
        procs.append(subprocess.Popen([sys.executable, __file__, "--fake", info_path, result_path, *map(str, start_xy)]))
        info = wait_for(info_path)
        if not info:
            sys.exit("fake window never started")
        found = winctl.find_window("", FAKE_TITLE)
        wx, wy, ww, wh = found.rect
        preset = [wx + 260, wy + 140, ww, wh]  # somewhere else on screen, same size
        target = Target(
            exe=found.exe, title=FAKE_TITLE, rect=preset,
            prompt_pt=[info["box"][0] - wx, info["box"][1] - wy],
            start_pt=[info["start"][0] - wx, info["start"][1] - wy],
        )
        s = Settings(prompt=PROMPT, paste_wait_s=0.5, profile="Fake", profiles={"Fake": target})

        logs = []
        run_sequence(s, dry_run=True, log=logs.append)
        now = winctl.window_rect(found.hwnd)
        results.append(check("window moved to preset", list(now) == preset, f"{list(now)} != {preset}"))
        results.append(check("test run does not click Start", not os.path.exists(result_path)))
        sx, sy = target.start_pt[0] + preset[0], target.start_pt[1] + preset[1]
        results.append(check("test run parks cursor on Start", winctl.cursor_pos() == (sx, sy), f"{winctl.cursor_pos()} != {(sx, sy)}"))

        run_sequence(s, log=logs.append)
        res = wait_for(result_path)
        results.append(check("Start was clicked", bool(res and res["clicked"])))
        results.append(check("prompt pasted, old text cleared", bool(res) and res["text"] == PROMPT, repr(res and res["text"])))
        os.remove(result_path)

        s.clear_first = False
        run_sequence(s, log=logs.append)
        res = wait_for(result_path)
        results.append(check("without clear-first the prompt is appended", bool(res) and res["text"] == PROMPT + PROMPT, repr(res and res["text"])))
        os.remove(result_path)

        procs.append(subprocess.Popen([sys.executable, __file__, "--cover", *map(str, winctl.window_rect(found.hwnd))]))
        time.sleep(1.5)
        try:
            run_sequence(s, log=logs.append)
            results.append(check("covered window aborts the run", False, "no error raised"))
        except SequenceError as e:
            results.append(check("covered window aborts the run", "covered" in str(e), str(e)))
        results.append(check("nothing was clicked while covered", not os.path.exists(result_path)))
    finally:
        for p in procs:
            p.terminate()
    print("ALL PASSED" if all(results) else "SOME FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fake":
        fake_target(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
    elif len(sys.argv) > 1 and sys.argv[1] == "--cover":
        cover_window(*map(int, sys.argv[2:6]))
    else:
        main()
