# Timed Clicker

Waits until a time you give it (e.g. when your Codex or Claude usage limit resets), then moves the coding
agent's desktop window to a saved position, pastes your prompt into the prompt box, and clicks Start.
Optionally, a set time after that, it presses a hotkey and shuts the PC down. It never touches any agent
account: it only moves the mouse and presses keys like you would, and you tell it the reset time.

Windows only. Needs Python 3 with tkinter (no other packages).

## Use it

Double-click `run.bat` (or `python timed_click.py`).

**1 · Target app and calibration** (once per agent app; redo if you resize its window or its layout changes)

1. Open the agent app (Codex, Claude, Cursor, ...) and put its window where you want it. Type a character in
   the prompt box so the Start/send button is visible and enabled.
2. Click **Capture window**. The Timed Clicker window hides and a countdown appears in the bottom-right
   corner. Hover over the agent window and keep still until the beep. The app detects which program it is
   and saves it under a name in **Target agent** (e.g. `Claude`, `Codex (ChatGPT)`; unknown apps are named
   after their program). Capturing a different app adds another entry; pick the one to drive from the list.
3. Click **Capture prompt box**, hover over the box you type in, wait for the beep.
4. Click **Capture Start button**, hover over the button, wait for the beep.
5. Optional: drag the window somewhere else, then press **Test (stops before Start)**. It should jump back to
   the preset, paste your prompt, and park the cursor on Start without clicking.

*Window title contains* is filled in from the captured window when the title is short and stable. Long titles
(usually a document or conversation name, as in VS Code) are not used, so the window is matched on the
program name alone. Edit the field if you have several windows of the same program.

**2 · When to start**: read the reset time in the app and enter it either as a countdown (`2h 14m`, `45m`,
`1:05`) or as a clock time (`18:45`, `6:45 PM`, `2026-10-22 03:15`, `Oct 22 3:15 AM`). A clock time that has
already passed today means tomorrow. *Extra seconds* (default 60) is added so it doesn't fire a moment
before the limit actually resets.

**3 · Prompt**: type the text to paste. Then press **Arm**. Leave the app running; **Disarm** cancels.

**4 · After Start is clicked (optional)**: tick *Shut down the PC*, set the minutes after clicking Start, and
optionally a hotkey (default `alt+s`) to press just before shutdown, for example to stop a background app
cleanly. Use **Test hotkey** to check the hotkey does what you expect. When the time comes you get a 30 s
warning with a **Cancel shutdown** button, then the hotkey is pressed, 5 s later the PC shuts down. Arming asks
for confirmation first. The PC is kept awake for the whole wait so the agent's task isn't interrupted.
*Force-close* makes Windows close apps that hold unsaved work; leave it off if you'd rather the shutdown be
held up than lose work.

## What happens at the fire time

1. Finds the agent window, restores it if minimized or maximized, moves and resizes it to the preset, and
   raises it.
2. Clicks the prompt box, selects all (if *Clear box first* is ticked), pastes the prompt.
3. Waits (*Wait after paste*), then clicks Start.

Before each click it checks that the agent window is really the window under the pointer. If something else
covers that spot it stops without clicking. A failed run is retried up to 3 times, 20 s apart, and an error
is shown if it still fails. Everything is logged to `timed_click.log`.

## Things to know

- The PC must be awake and **unlocked** at the fire time: clicks can't reach a locked screen or a sleeping PC.
  *Keep PC awake while armed* stops idle sleep and screen-off (also on battery, whatever the power plan says)
  for as long as the app is running, but not locking, closing the lid, the power button or Sleep from the Start
  menu. If the screen is locked when the time comes, it waits up to an hour for you to unlock. Set "require
  sign-in" to Never in Windows settings if you want it fully hands-off.
- On battery, staying awake drains the battery; plug in for long waits.
- It uses the real mouse and keyboard for a few seconds when it fires, so don't use the PC at that moment.
- The hotkey is pressed while the Timed Clicker window is in front, so it doesn't land in the agent app. The
  log records which app had the focus.
- Your clipboard is overwritten with the prompt.
- *Clear box first* sends Ctrl+A before pasting. Untick it if the target is a terminal where Ctrl+A means
  "start of line".
- `config.json` (next to the script) stores your settings including the prompt.

## Checking it

```
python -m unittest test_timeparse test_helpers   # parsing, hotkeys, settings
python selftest.py                               # end to end against a fake window; moves your mouse for ~15 s
```
