"""Observe creation and destruction of HWNDs in one owned process."""
import ctypes as c
from ctypes import wintypes as w

from native import bind, checked


class WindowLifetime:
    def __init__(self, pid):
        user = c.WinDLL("user32", use_last_error=True)
        callback_type = c.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)
        hook = bind(user, "SetWinEventHook", w.HANDLE, w.DWORD, w.DWORD, w.HMODULE, callback_type,
                    w.DWORD, w.DWORD, w.DWORD)
        self.unhook = bind(user, "UnhookWinEvent", w.BOOL, w.HANDLE)
        self.events = []
        @callback_type
        def callback(_hook, event, hwnd, object_id, child, _thread, tick):
            if hwnd and object_id == 0 and child == 0:
                self.events.append((int(hwnd), "create" if event == 0x8000 else "destroy", tick))
        self.callback = callback
        self.hook = checked(hook(0x8000, 0x8001, None, callback, pid, 0, 0))

    def close(self):
        checked(self.unhook(self.hook))
