# Timed Clicker

Waits until a time you give it (e.g. when your Codex 5-hour limit resets), then moves the Codex window to a
saved position, pastes your prompt into the prompt box, and clicks Start. It never touches your Codex
account: it only moves the mouse and presses Ctrl+V like you would, and you tell it the reset time.

Windows only. Needs Python 3 with tkinter (no other packages).

## Use it

Double-click `run.bat` (or `python timed_click.py`).

**1 · Calibrate** (once, redo if you resize the Codex window or the layout changes)

1. Open Codex and put its window where you want it. Type a character in the prompt box so the Start/send
   button is visible and enabled.
2. Click **Capture window**. The Timed Clicker window hides and a countdown appears in the bottom-right
   corner. Hover over the Codex window and keep still until the beep. This saves the window's position and
   size (the *preset*) and which program it is.
3. Click **Capture prompt box**, hover over the box you type in, wait for the beep.
4. Click **Capture Start button**, hover over the button, wait for the beep.
5. Optional: drag the Codex window somewhere else, then press **Test (stops before Start)**. It should jump
   back to the preset, paste your prompt, and park the cursor on Start without clicking.

*Window title contains* is filled in from the captured window. If the title changes between sessions
(e.g. it shows the conversation name), shorten it to the stable part such as `Codex`, or clear it to match on
the program name alone. If Codex runs in a browser, keep a title filter so the right browser window is found.

**2 · When to start**: read the reset time in Codex and enter it either as a countdown (`2h 14m`, `45m`,
`1:05`) or as a clock time (`18:45`, `6:45 PM`, `2026-10-22 03:15`, `Oct 22 3:15 AM`). A clock time that has
already passed today means tomorrow. *Extra seconds* (default 60) is added so it doesn't fire a moment
before the limit actually resets.

**3 · Prompt**: type the text to paste. Then press **Arm**. Leave the app running; **Disarm** cancels.

## What happens at the fire time

1. Finds the Codex window, restores it if minimized or maximized, moves and resizes it to the preset, and
   raises it.
2. Clicks the prompt box, selects all (if *Clear box first* is ticked), pastes the prompt.
3. Waits (*Wait after paste*), then clicks Start.

Before each click it checks that the Codex window is really the window under the pointer. If something else
covers that spot it stops without clicking. A failed run is retried up to 3 times, 20 s apart, and an error
is shown if it still fails. Everything is logged to `timed_click.log`.

## Things to know

- The PC must be awake and **unlocked** at the fire time: clicks can't reach a locked screen or a sleeping PC.
  *Keep PC awake while armed* stops idle sleep and screen-off, but not locking. If the screen is locked when
  the time comes, it waits up to an hour for you to unlock. Turn off "require sign-in after sleep/screen off"
  in Windows settings if you want it fully hands-off.
- Closing the lid, or choosing Sleep/Shut down, stops the timer.
- It uses the real mouse and keyboard for a few seconds when it fires, so don't use the PC at that moment.
- Your clipboard is overwritten with the prompt.
- *Clear box first* sends Ctrl+A before pasting. Untick it if Codex runs in a terminal where Ctrl+A means
  "start of line".
- `config.json` (next to the script) stores your settings including the prompt.

## Checking it

```
python -m unittest test_timeparse     # time parsing
python selftest.py                    # end to end against a fake window; moves your mouse for ~15 s
```
