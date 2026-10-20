"""Win32 helpers for the timed clicker: cursor, mouse, keys, clipboard, windows, power state."""
import ctypes
import os
import re
import time
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

OWN_PID = os.getpid()

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_A = 0x41
VK_V = 0x56

KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

SW_RESTORE = 9
GA_ROOT = 2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DESKTOP_SWITCHDESKTOP = 0x0100
DWMWA_CLOAKED = 14

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _sig(func, restype, *argtypes):
    func.restype = restype
    func.argtypes = list(argtypes)


_sig(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
_sig(user32.SetCursorPos, wintypes.BOOL, ctypes.c_int, ctypes.c_int)
_sig(user32.mouse_event, None, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t)
_sig(user32.keybd_event, None, wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t)
_sig(user32.WindowFromPoint, wintypes.HWND, wintypes.POINT)
_sig(user32.GetAncestor, wintypes.HWND, wintypes.HWND, wintypes.UINT)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
_sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_sig(user32.GetWindowRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsZoomed, wintypes.BOOL, wintypes.HWND)
_sig(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_sig(user32.MoveWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL)
_sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
_sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
_sig(user32.GetForegroundWindow, wintypes.HWND)
_sig(user32.BringWindowToTop, wintypes.BOOL, wintypes.HWND)
_sig(user32.AttachThreadInput, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_sig(kernel32.GetCurrentThreadId, wintypes.DWORD)
_sig(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
_sig(user32.GetDesktopWindow, wintypes.HWND)
_sig(user32.OpenClipboard, wintypes.BOOL, wintypes.HWND)
_sig(user32.EmptyClipboard, wintypes.BOOL)
_sig(user32.SetClipboardData, wintypes.HANDLE, wintypes.UINT, wintypes.HANDLE)
_sig(user32.CloseClipboard, wintypes.BOOL)
_sig(user32.OpenInputDesktop, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_sig(user32.SwitchDesktop, wintypes.BOOL, wintypes.HANDLE)
_sig(user32.CloseDesktop, wintypes.BOOL, wintypes.HANDLE)
_sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_sig(kernel32.GlobalAlloc, wintypes.HGLOBAL, wintypes.UINT, ctypes.c_size_t)
_sig(kernel32.GlobalLock, ctypes.c_void_p, wintypes.HGLOBAL)
_sig(kernel32.GlobalUnlock, wintypes.BOOL, wintypes.HGLOBAL)
_sig(kernel32.GlobalFree, wintypes.HGLOBAL, wintypes.HGLOBAL)
_sig(kernel32.SetThreadExecutionState, wintypes.DWORD, wintypes.DWORD)


def enable_dpi_awareness():
    """Make cursor and window coordinates physical pixels. Call before creating any window."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


# --- mouse and keyboard ----------------------------------------------------

def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def move_cursor(x, y):
    user32.SetCursorPos(int(x), int(y))


def click(x, y):
    move_cursor(x, y)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def key_chord(*vks, hold=0.05):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    time.sleep(hold)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


_MODIFIERS = {"ctrl": VK_CONTROL, "control": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT, "win": VK_LWIN, "windows": VK_LWIN}
_NAMED_KEYS = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08}


def parse_hotkey(text):
    """Virtual-key codes (modifiers first) for a hotkey like "alt+s", "ctrl+shift+f5" or "win+7"."""
    parts = [p.strip().lower() for p in text.split("+")]
    if not text.strip() or not all(parts):
        raise ValueError("enter a hotkey such as alt+s")
    mods, keys = [], []
    for p in parts:
        if p in _MODIFIERS:
            if _MODIFIERS[p] not in mods:
                mods.append(_MODIFIERS[p])
        elif len(p) == 1 and p.isascii() and p.isalnum():
            keys.append(ord(p.upper()))  # virtual-key codes for A-Z and 0-9 are their ASCII codes
        elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", p):
            keys.append(0x70 + int(p[1:]) - 1)
        elif p in _NAMED_KEYS:
            keys.append(_NAMED_KEYS[p])
        else:
            raise ValueError(f"unknown key {p!r} in hotkey")
    if len(keys) != 1:
        raise ValueError("a hotkey needs exactly one key besides ctrl/alt/shift/win, e.g. alt+s")
    return mods + keys


# --- clipboard -------------------------------------------------------------

def set_clipboard(text):
    """Put text on the clipboard immediately (no delayed rendering, so no event loop needed)."""
    data = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("GlobalAlloc failed")
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    # A NULL owner makes SetClipboardData fail after EmptyClipboard, so own it with the desktop window.
    for _ in range(20):
        if user32.OpenClipboard(user32.GetDesktopWindow()):
            break
        time.sleep(0.05)
    else:
        kernel32.GlobalFree(handle)
        raise OSError("clipboard is busy")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


# --- windows ---------------------------------------------------------------

@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    exe: str
    rect: tuple  # x, y, width, height in screen pixels


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _exe_name(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(h)


def describe(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowInfo(int(hwnd), pid.value, _title(hwnd), _exe_name(pid.value), window_rect(hwnd))


def root_window_at(x, y):
    """Top-level window under a screen point, or 0."""
    hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return user32.GetAncestor(hwnd, GA_ROOT) or 0 if hwnd else 0


def _is_cloaked(hwnd):
    try:
        cloaked = wintypes.DWORD()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return bool(cloaked.value)
    except (AttributeError, OSError):
        return False


def find_window(exe="", title=""):
    """First visible top-level window (front to back) whose exe name equals `exe` and whose title contains `title`."""
    exe, title = exe.lower(), title.lower()
    if not exe and not title:
        return None
    found = []

    @WNDENUMPROC
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or _is_cloaked(hwnd):
            return True
        info = describe(hwnd)
        if info.pid == OWN_PID or not info.title:
            return True
        if exe and info.exe.lower() != exe:
            return True
        if title and title not in info.title.lower():
            return True
        found.append(info)
        return False

    user32.EnumWindows(visit, 0)
    return found[0] if found else None


def place_window(hwnd, rect):
    """Restore the window if minimized/maximized and move it to rect (x, y, w, h)."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    x, y, w, h = rect
    user32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)


def raise_window(hwnd):
    """Bring the window above everything else; the topmost flip works even when focus stealing is blocked."""
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)  # best effort; the click that follows activates it anyway


def top_level_of(hwnd):
    """The top-level window containing hwnd (Tk's winfo_id() is an inner window)."""
    return user32.GetAncestor(hwnd, GA_ROOT) or hwnd


def force_foreground(hwnd):
    """Take the foreground for hwnd by briefly sharing input state with the current foreground thread."""
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    my_thread = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != my_thread and user32.AttachThreadInput(my_thread, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_thread, fg_thread, False)


def foreground_exe():
    hwnd = user32.GetForegroundWindow()
    return describe(top_level_of(hwnd)).exe if hwnd else ""


# --- session / power -------------------------------------------------------

def session_locked():
    """True while the lock screen or another secure desktop is showing (clicks can't reach apps)."""
    desk = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desk:
        return True
    try:
        return not user32.SwitchDesktop(desk)
    finally:
        user32.CloseDesktop(desk)


def keep_awake(on):
    """Stop Windows sleeping or turning the display off. Must be called from the same thread to undo."""
    flags = ES_CONTINUOUS
    if on:
        flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    kernel32.SetThreadExecutionState(flags)
