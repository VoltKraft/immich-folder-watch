"""Read Win32 desktop/window identities and operate only on the fixture's own desktop."""

import ctypes as c
from contextlib import contextmanager
from ctypes import wintypes as w
import os
from pathlib import PureWindowsPath
from concurrent.futures import ThreadPoolExecutor

P = c.POINTER
READ_OBJECTS, CREATE_WINDOW, SWITCH_DESKTOP = 0x1, 0x2, 0x100
GA_ROOT, GWL_STYLE, GWL_EXSTYLE, WS_EX_TOPMOST = 2, -16, -20, 8


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype, function.argtypes = result, arguments
    return function


def check(value, api):
    if not value:
        code = c.get_last_error()
        raise OSError(code, f"{api} failed (Win32 {code})")
    return value


def native_failure():
    return {"win32Error": c.get_last_error()}


class SessionFields(c.Structure):
    _fields_ = [("session", c.c_uint32), ("state", c.c_uint32), ("flags", c.c_int32)]


class SessionData(c.Union):
    # The full SDK union contains LARGE_INTEGER. Read only its leading three fields.
    _fields_ = [("fields", SessionFields), ("alignment", c.c_int64)]


class SessionInfo(c.Structure):
    _fields_ = [("level", c.c_uint32), ("data", SessionData)]


class Desktop:
    def __init__(self):
        user = c.WinDLL("user32", use_last_error=True)
        kernel = c.WinDLL("kernel32", use_last_error=True)
        wts = c.WinDLL("wtsapi32", use_last_error=True)
        dwm = c.WinDLL("dwmapi", use_last_error=True)
        self.station = bind(user, "GetProcessWindowStation", w.HANDLE)
        self.thread_desktop = bind(user, "GetThreadDesktop", w.HANDLE, w.DWORD)
        self.info = bind(user, "GetUserObjectInformationW", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, P(w.DWORD))
        self.open_input = bind(user, "OpenInputDesktop", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.open_named = bind(user, "OpenDesktopW", w.HANDLE, w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD)
        self.create = bind(user, "CreateDesktopW", w.HANDLE, w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p)
        self.close = bind(user, "CloseDesktop", w.BOOL, w.HANDLE)
        self.switch = bind(user, "SwitchDesktop", w.BOOL, w.HANDLE)
        self.thread = bind(kernel, "GetCurrentThreadId", w.DWORD)
        self.session = bind(kernel, "ProcessIdToSessionId", w.BOOL, w.DWORD, P(w.DWORD))
        self.active = bind(kernel, "WTSGetActiveConsoleSessionId", w.DWORD)
        self.query_session = bind(wts, "WTSQuerySessionInformationW", w.BOOL, w.HANDLE, w.DWORD, c.c_int,
                                  P(c.c_void_p), P(w.DWORD))
        self.free_session = bind(wts, "WTSFreeMemory", None, c.c_void_p)
        self.shell = bind(user, "GetShellWindow", w.HWND)
        self.foreground = bind(user, "GetForegroundWindow", w.HWND)
        self.desktop_window = bind(user, "GetDesktopWindow", w.HWND)
        self.owner = bind(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, P(w.DWORD))
        self.process = bind(kernel, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.image = bind(kernel, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD, w.LPWSTR, P(w.DWORD))
        self.close_handle = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        self.window_class = bind(user, "GetClassNameW", c.c_int, w.HWND, w.LPWSTR, c.c_int)
        self.window_rect = bind(user, "GetWindowRect", w.BOOL, w.HWND, P(w.RECT))
        self.client_rect = bind(user, "GetClientRect", w.BOOL, w.HWND, P(w.RECT))
        self.to_screen = bind(user, "ClientToScreen", w.BOOL, w.HWND, P(w.POINT))
        self.visible = bind(user, "IsWindowVisible", w.BOOL, w.HWND)
        self.iconic = bind(user, "IsIconic", w.BOOL, w.HWND)
        self.style = bind(user, "GetWindowLongW", w.LONG, w.HWND, c.c_int)
        self.dpi = bind(user, "GetDpiForWindow", w.UINT, w.HWND)
        self.awareness = bind(user, "SetThreadDpiAwarenessContext", w.HANDLE, w.HANDLE)
        self.point_window = bind(user, "WindowFromPoint", w.HWND, w.POINT)
        self.ancestor = bind(user, "GetAncestor", w.HWND, w.HWND, w.UINT)
        self.attribute = bind(dwm, "DwmGetWindowAttribute", w.LONG, w.HWND, w.DWORD, c.c_void_p, w.DWORD)
        self.position = bind(user, "SetWindowPos", w.BOOL, w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)

    def name(self, handle):
        if not handle:
            return native_failure()
        value, needed = c.create_unicode_buffer(256), w.DWORD()
        if not self.info(handle, 2, value, c.sizeof(value), c.byref(needed)):
            return native_failure()
        return value.value

    def receiving_input(self, handle):
        receives, needed = w.BOOL(), w.DWORD()
        if not self.info(handle, 6, c.byref(receives), c.sizeof(receives), c.byref(needed)):
            return native_failure()
        return bool(receives.value)

    def input_object(self):
        handle = self.open_input(0, False, READ_OBJECTS)
        if not handle:
            failure = native_failure()
            return failure, failure
        try:
            return self.name(handle), self.receiving_input(handle)
        finally:
            check(self.close(handle), "CloseDesktop(input)")

    def input_name(self):
        return self.input_object()[0]

    def pid_session(self, pid):
        session = w.DWORD()
        return session.value if self.session(pid, c.byref(session)) else native_failure()

    def session_state(self, session):
        address, size = c.c_void_p(), w.DWORD()
        if not self.query_session(None, session, 25, c.byref(address), c.byref(size)):  # WTSSessionInfoEx
            return native_failure()
        try:
            if size.value < SessionInfo.data.offset + c.sizeof(SessionFields):
                return {"invalidLength": size.value}
            data = c.cast(address, P(SessionInfo)).contents
            if data.level != 1 or data.data.fields.session != session:
                return {"level": data.level, "sessionMismatch": True}
            fields = data.data.fields
            return {"session": fields.session, "connectionState": fields.state, "lockFlags": fields.flags}
        finally:
            self.free_session(address)

    def context(self):
        station = self.station()
        # USEROBJECTFLAGS is BOOL fInherit, BOOL fReserved, DWORD dwFlags.
        flags, needed = (w.DWORD * 3)(), w.DWORD()
        visible = (bool(flags[2] & 1) if self.info(station, 1, flags, c.sizeof(flags), c.byref(needed))
                   else native_failure())
        session = self.pid_session(os.getpid())
        thread = self.thread_desktop(self.thread())
        name, receives = self.input_object()
        return {"windowStation": self.name(station), "stationVisible": visible,
                "threadDesktop": self.name(thread), "threadReceivesInput": self.receiving_input(thread),
                "inputDesktop": name, "inputObjectReceivesInput": receives,
                "session": session, "activeConsoleSession": self.active(),
                "wts": self.session_state(session) if isinstance(session, int) else session}

    def process_name(self, pid):
        handle = self.process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return native_failure()
        try:
            size = w.DWORD(32768)
            name = c.create_unicode_buffer(size.value)
            return PureWindowsPath(name.value).name if self.image(handle, 0, name, c.byref(size)) else native_failure()
        finally:
            self.close_handle(handle)

    def window(self, hwnd):
        if not hwnd:
            return None
        pid, name, rect = w.DWORD(), c.create_unicode_buffer(256), w.RECT()
        tid = self.owner(hwnd, c.byref(pid))
        return {"hwnd": hex(hwnd), "pid": pid.value, "tid": tid, "executable": self.process_name(pid.value),
                "class": name.value if self.window_class(hwnd, name, len(name)) else native_failure(),
                "rect": rect_values(rect) if self.window_rect(hwnd, c.byref(rect)) else native_failure()}

    def surroundings(self):
        return {"foreground": self.window(self.foreground()), "shell": self.window(self.shell()),
                "desktopWindow": self.window(self.desktop_window())}

    def count_top_level_window(self, desktop, hwnd):
        if not desktop or not hwnd:
            raise ValueError("Expected a held desktop and an identified top-level window")
        visit_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        enumerate_windows = bind(c.WinDLL("user32", use_last_error=True), "EnumDesktopWindows",
                                 w.BOOL, w.HANDLE, visit_type, w.LPARAM)
        matches = 0

        @visit_type
        def visit(candidate, _):
            nonlocal matches
            matches += candidate == hwnd
            return True

        check(enumerate_windows(desktop, visit, 0), "EnumDesktopWindows(owned window)")
        return matches

    @contextmanager
    def enumeration_witness(self, name, report):
        """Keep an observable, never-shown window on the fixture's otherwise empty desktop."""
        if not name.startswith("IfwQa_") or not ordinary_console(self.context(), name):
            raise RuntimeError("A private, active fixture desktop is required for the observation window")
        user = c.WinDLL("user32", use_last_error=True)
        create = bind(user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                      c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
        destroy = bind(user, "DestroyWindow", w.BOOL, w.HWND)
        # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW and WS_POPUP, with no WS_VISIBLE.
        hwnd = check(create(0x08000080, "STATIC", "IFW native test enumeration", 0x80000000,
                            0, 0, 0, 0, None, None, None, None), "CreateWindowExW(hidden fixture)")
        try:
            selected = check(self.thread_desktop(self.thread()), "GetThreadDesktop")
            if (self.count_top_level_window(selected, hwnd) != 1 or self.visible(hwnd)
                    or self.window(hwnd)["pid"] != os.getpid()):
                raise RuntimeError("The enumeration witness must be owned, enumerable and hidden")
            report["hiddenEnumerationWindow"] = hex(hwnd)
            yield
        finally:
            report["hiddenWindowDestroyed"] = bool(destroy(hwnd))
            if not report["hiddenWindowDestroyed"]:
                check(False, "DestroyWindow(hidden fixture)")

    def dwm(self, hwnd, index, value):
        result = self.attribute(hwnd, index, c.byref(value), c.sizeof(value))
        if result < 0:
            return {"hresult": f"0x{result & 0xffffffff:08x}"}
        return rect_values(value) if isinstance(value, w.RECT) else value.value

    def observed(self, hwnd, pid, center=None):
        own = self.window(hwnd)
        if not own or own["pid"] != pid:
            raise RuntimeError("Subject HWND ownership changed")
        client = w.RECT()
        if self.client_rect(hwnd, c.byref(client)):
            lower, upper = w.POINT(client.left, client.top), w.POINT(client.right, client.bottom)
            bounds = ([lower.x, lower.y, upper.x, upper.y]
                      if self.to_screen(hwnd, c.byref(lower)) and self.to_screen(hwnd, c.byref(upper))
                      else native_failure())
        else:
            bounds = native_failure()
        own.update({"session": self.pid_session(pid), "threadDesktop": self.name(self.thread_desktop(own["tid"])),
                    "visible": bool(self.visible(hwnd)), "iconic": bool(self.iconic(hwnd)), "dpi": self.dpi(hwnd),
                    "style": hex(self.style(hwnd, GWL_STYLE) & 0xffffffff),
                    "extendedStyle": hex(self.style(hwnd, GWL_EXSTYLE) & 0xffffffff),
                    "clientScreenRect": bounds, "dwmCloaked": self.dwm(hwnd, 14, w.DWORD()),
                    "dwmFrameBounds": self.dwm(hwnd, 9, w.RECT())})
        result = {"subject": own, **self.surroundings()}
        if center is not None:
            hit = self.point_window(w.POINT(*center))
            root = self.ancestor(hit, GA_ROOT) if hit else None
            window = self.window(hit)
            result["fieldPoint"] = {"xy": center, "window": window, "root": self.window(root),
                                    "owned": bool(window and window["pid"] == pid and root == hwnd)}
        return result

    def order_subject(self, hwnd, pid, topmost):
        actual = w.DWORD()
        if not self.owner(hwnd, c.byref(actual)) or actual.value != pid:
            raise RuntimeError("Cannot order a window outside the fixture")
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE. Change only the subject's Z order.
        return True if self.position(hwnd, -1 if topmost else -2, 0, 0, 0, 0, 0x13) else native_failure()

    def create_detached(self, name):
        # CreateDesktop associates the creator thread with the desktop. Keep the supervisor on Default.
        def make():
            return check(self.create(name, None, None, 0, READ_OBJECTS | CREATE_WINDOW | SWITCH_DESKTOP, None),
                         "CreateDesktopW")
        with ThreadPoolExecutor(max_workers=1) as creator:
            return creator.submit(make).result()


def rect_values(rect):
    return [rect.left, rect.top, rect.right, rect.bottom]


def same_name(value, expected):
    return isinstance(value, str) and value.casefold() == expected.casefold()


def unlocked_console(context):
    # Current hosted systems use WTSActive=0 and WTS_SESSIONSTATE_UNLOCK=1.
    return (same_name(context["windowStation"], "WinSta0") and context["stationVisible"] is True
            and isinstance(context["session"], int) and context["session"] > 0
            and context["session"] == context["activeConsoleSession"]
            and context["wts"].get("session") == context["session"]
            and context["wts"].get("connectionState") == 0 and context["wts"].get("lockFlags") == 1)


def ordinary_console(context, desktop):
    return (unlocked_console(context) and same_name(context["threadDesktop"], desktop)
            and same_name(context["inputDesktop"], desktop)
            and context["threadReceivesInput"] is True and context["inputObjectReceivesInput"] is True)
