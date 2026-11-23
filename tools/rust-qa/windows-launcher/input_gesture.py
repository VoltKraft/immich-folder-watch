"""Start the fixed launcher from a tagged F24 key-up on its test-owned input window."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
import secrets
import time

from win32 import bind, check, ordinary_console

F24 = 0x87
DOWN, UP = 0x100, 0x101


class InputUnavailable(Exception):
    """The disposable desktop could not provide a verified input target before the gesture."""


class Keyboard(c.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD), ("time", w.DWORD), ("extra", c.c_size_t)]


class InputData(c.Union):
    # On both tested native targets the largest INPUT member (MOUSEINPUT) is 32 bytes.
    _fields_ = [("keyboard", Keyboard), ("mouseSpace", c.c_ubyte * 32)]


class Input(c.Structure):
    _fields_ = [("kind", w.DWORD), ("data", InputData)]


def accept_key(rows, hwnd, marker, event):
    """Accept one down/up pair with the caller's tag and native keyboard message transition bits."""
    expected = (DOWN, UP)
    if (len(rows) >= 2 or event["message"] != expected[len(rows)] or event["hwnd"] != hwnd
            or event["vk"] != F24 or event["extra"] != marker or event["repeats"] != 1
            or (event["previous"], event["released"]) != ((0, 0) if not rows else (1, 1))):
        raise ValueError("An unexpected keyboard event reached the launch window")
    rows.append(event)
    return event["message"] == UP


class KeyWindow:
    def __init__(self, desk, user, hwnd, name, record):
        self.desk, self.hwnd, self.name, self.record = desk, hwnd, name, record
        self.get_focus = bind(user, "GetFocus", w.HWND)
        self.get_extra = bind(user, "GetMessageExtraInfo", c.c_ssize_t)
        self.peek = bind(user, "PeekMessageW", w.BOOL, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT)
        self.dispatch = bind(user, "DispatchMessageW", c.c_ssize_t, c.POINTER(w.MSG))
        self.send = bind(user, "SendInput", w.UINT, w.UINT, c.POINTER(Input), c.c_int)
        self.clock = bind(c.WinDLL("kernel32", use_last_error=True), "GetTickCount64", c.c_uint64)
        self.key_state = bind(user, "GetAsyncKeyState", c.c_int16, c.c_int)
        self.marker = secrets.randbelow(0x7fffffff) + 1
        self.tid = desk.thread()
        self.pid = os.getpid()
        self.record.update(hwnd=hwnd, callerPid=self.pid, callerThread=self.tid, marker=self.marker, keys=[])

    def owned_input(self):
        """Inspect only this window, its center hit and the caller's real foreground and keyboard focus."""
        owner, rect = w.DWORD(), w.RECT()
        tid = self.desk.owner(self.hwnd, c.byref(owner))
        state = self.record["lastTargetCheck"] = dict(owner=(tid, owner.value) == (self.tid, self.pid),
            privateInput=ordinary_console(self.desk.context(), self.name), foreground=self.desk.foreground() == self.hwnd,
            focus=self.get_focus() == self.hwnd, visible=bool(self.desk.visible(self.hwnd)))
        if not all(state.values()) or not self.desk.client_rect(self.hwnd, c.byref(rect)):
            return False
        p = w.POINT(rect.right // 2, rect.bottom // 2)
        if p.x < 1 or p.y < 1 or not self.desk.to_screen(self.hwnd, c.byref(p)):
            return False
        state.update(centerOwned=self.desk.point_window(p) == self.hwnd, foregroundAfter=self.desk.foreground() == self.hwnd)
        return state["centerOwned"] and state["foregroundAfter"]

    def before_create(self):
        if not self.owned_input() or len(self.record["keys"]) != 2:
            raise ValueError("The key handler lost its foreground window before CreateProcessW")
        self.record["beforeCreate"] = dict(hwnd=self.hwnd, tick=self.clock(), thread=self.desk.thread())

    def observe_child(self, api, proc, exe):
        parent, _ = api.processes()[proc.pid]
        if parent != self.pid or not self.owned_input() or len(self.record["keys"]) != 2:
            raise ValueError("The suspended secondary did not belong to the active gesture handler")
        self.record["created"] = dict(pid=proc.pid, parentPid=parent, creation100ns=api.process_identity(int(proc._handle)),
                                      parentCreation100ns=api.process_identity(-1), image=exe.name,
                                      foreground=self.hwnd, tick=self.clock())

    def launch(self, create):
        if c.sizeof(Input) != 40 or not self.owned_input():
            raise InputUnavailable("The owned launch window did not have foreground, focus and the center hit")
        if any(self.key_state(key) & 0x8000 for key in (F24, 0x10, 0x11, 0x12, 0x5b, 0x5c)):
            raise InputUnavailable("F24 or a system modifier was already down on the private desktop")
        pair = (Input * 2)()
        for row, flags in zip(pair, (0, 2)):
            row.kind, row.data.keyboard = 1, Keyboard(F24, 0, flags, 0, self.marker)
        if not self.owned_input():
            raise InputUnavailable("The private launch window lost its target before SendInput")
        self.record["beforeQueue"] = self.record["lastTargetCheck"].copy()
        self.record["queued"] = self.send(2, pair, c.sizeof(Input))
        if self.record["queued"] != 2:
            if self.record["queued"] == 1 and self.owned_input():
                released = self.send(1, c.byref(pair[1]), c.sizeof(Input))
                self.record["releasedPartialGesture"] = released == 1
            raise RuntimeError("SendInput did not queue a complete gesture")
        message = w.MSG()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if not self.peek(c.byref(message), self.hwnd, 0, 0, 1):
                time.sleep(.005)
                continue
            if message.message in (DOWN, UP):
                extra = self.get_extra()
                if not self.owned_input():
                    raise ValueError("The launch window lost input before its tagged key was handled")
                bits = message.lParam
                event = dict(hwnd=message.hWnd, vk=message.wParam, message=message.message, time=message.time,
                             repeats=bits & 0xffff, previous=(bits >> 30) & 1, released=(bits >> 31) & 1,
                             extra=extra, dispatchThread=self.desk.thread())
                if accept_key(self.record["keys"], self.hwnd, self.marker, event):
                    # The CreateProcessW call runs synchronously in this window's key-up handler.
                    return create()
            else:
                self.dispatch(c.byref(message))
        raise RuntimeError("The owned window did not receive its tagged key-up")


@contextmanager
def keyboard_launcher(desk, name, record):
    if not ordinary_console(desk.context(), name) or not name.startswith("IfwQa_"):
        raise ValueError("The launch window requires the fixture's private, unlocked input desktop")
    user = c.WinDLL("user32", use_last_error=True)
    create = bind(user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                  c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p)
    show = bind(user, "ShowWindow", w.BOOL, w.HWND, c.c_int)
    request = bind(user, "SetForegroundWindow", w.BOOL, w.HWND)
    focus = bind(user, "SetFocus", w.HWND, w.HWND)
    destroy = bind(user, "DestroyWindow", w.BOOL, w.HWND)
    # A push button accepts native keyboard focus and owns its interior hit.
    hwnd = check(create(0, "BUTTON", "Open the synthetic test application", 0x00CF0000,
                        80, 80, 360, 150, None, None, None, None), "CreateWindowExW(input launcher)")
    try:
        window = KeyWindow(desk, user, hwnd, name, record)
        show(hwnd, 5)  # SW_SHOW of this new test window on its own desktop
        if desk.foreground() != hwnd and ordinary_console(desk.context(), name):
            record["callerForegroundRequest"] = bool(request(hwnd))
        end = time.monotonic() + 2
        message = w.MSG()
        while time.monotonic() < end:
            if not ordinary_console(desk.context(), name):
                raise InputUnavailable("The dedicated keyboard desktop lost input during window setup")
            if desk.foreground() == hwnd:
                if window.get_focus() != hwnd:
                    focus(hwnd)
                if window.owned_input():
                    break
            if window.peek(c.byref(message), hwnd, 0, 0, 1):
                window.dispatch(c.byref(message))
            else:
                time.sleep(.015)
        yield window
    finally:
        record["windowDestroyed"] = bool(destroy(hwnd))
        check(record["windowDestroyed"], "DestroyWindow(input launcher)")
