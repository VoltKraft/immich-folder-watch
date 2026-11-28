"""Observe the retained primary's classic popup and deliver a mouse gesture on its verified items."""

import ctypes as c
from ctypes import wintypes as w
import secrets
import time
import xml.etree.ElementTree as ET

from observe import bind, check, ordinary_console


class Mouse(c.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("data", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", c.c_size_t)]


class Input(c.Structure):
    _fields_ = [("kind", w.DWORD), ("mouse", Mouse)]


class GuiThread(c.Structure):
    _fields_ = [("size", w.DWORD), ("flags", w.DWORD), ("active", w.HWND), ("focus", w.HWND),
                ("capture", w.HWND), ("menuOwner", w.HWND), ("moveSize", w.HWND), ("caret", w.HWND), ("bounds", w.RECT)]


ACTIONS = ("open", "restart", "quit")


def expected_menus(folder):
    result = {}
    for language, file in (("en", "Strings.resx"), ("de", "Strings.de.resx")):
        source = ET.parse(folder / file)
        names = []
        for action in ACTIONS:
            name, = source.findall(f"./data[@name='Tray_{action.title()}']/value")
            names.append(name.text)
        result[language] = names
    return result


def identify_menu(rows, labels):
    if len(rows) != 5:
        raise ValueError("Unexpected number of native menu items")
    for pos, row in enumerate(rows):
        if pos % 2:
            if not row["separator"] or row["text"]:
                raise ValueError("Missing native separator between commands")
        elif (row["separator"] or not row["enabled"] or row["id"] != 1 + pos // 2 or not row["text"]
              or row["right"] <= row["left"] or row["bottom"] <= row["top"]):
            raise ValueError("The real menu did not expose an enabled command and position")
    names = [rows[pos]["text"] for pos in (0, 2, 4)]
    matches = [key for key, values in labels.items() if values == names]
    if len(matches) != 1:
        raise ValueError(f"Unexpected native menu labels {names}")
    return matches[0]


class MenuInput:
    def __init__(self, desk, api, key, tid, labels):
        self.desk, self.api, self.labels = desk, api, labels
        self.pid, self.receiver, _ = map(int, key)
        self.tid = tid
        u = c.WinDLL("user32", use_last_error=True)
        g = c.WinDLL("gdi32", use_last_error=True)
        self.send = bind(u, "SendInput", w.UINT, w.UINT, c.POINTER(Input), c.c_int)
        self.move = bind(u, "SetPhysicalCursorPos", w.BOOL, c.c_int, c.c_int)
        self.cursor = bind(u, "GetPhysicalCursorPos", w.BOOL, c.POINTER(w.POINT))
        self.key_state = bind(u, "GetAsyncKeyState", c.c_int16, c.c_int)
        self.thread = bind(u, "GetGUIThreadInfo", w.BOOL, w.DWORD, c.POINTER(GuiThread))
        self.visitor = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.windows = bind(u, "EnumThreadWindows", w.BOOL, w.DWORD, self.visitor, w.LPARAM)
        self.owner_window = bind(u, "GetWindow", w.HWND, w.HWND, w.UINT)
        self.message = bind(u, "SendMessageTimeoutW", c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM,
                            w.UINT, w.UINT, c.POINTER(c.c_size_t))
        self.count = bind(u, "GetMenuItemCount", c.c_int, w.HMENU)
        self.item_id = bind(u, "GetMenuItemID", w.UINT, w.HMENU, c.c_int)
        self.state = bind(u, "GetMenuState", w.UINT, w.HMENU, w.UINT, w.UINT)
        self.string = bind(u, "GetMenuStringW", c.c_int, w.HMENU, w.UINT, w.LPWSTR, c.c_int, w.UINT)
        self.rect = bind(u, "GetMenuItemRect", w.BOOL, w.HWND, w.HMENU, w.UINT, c.POINTER(w.RECT))
        self.getdc = bind(u, "GetDC", w.HDC, w.HWND)
        self.release = bind(u, "ReleaseDC", c.c_int, w.HWND, w.HDC)
        self.pixel = bind(g, "GetPixel", w.DWORD, w.HDC, c.c_int, c.c_int)
        if c.sizeof(Input) != 40:
            raise ValueError("Use the native x64 mouse ABI")
        self.tag = secrets.randbits(31) or 1
        self.original = self.pointer()
        self.last = self.original

    def pointer(self):
        p = w.POINT()
        check(self.cursor(c.byref(p)), "GetPhysicalCursorPos(menu)")
        return [p.x, p.y]

    def on_desktop(self):
        if not ordinary_console(self.desk.context(), "Default"):
            raise ValueError("The original unlocked input desktop changed")

    def owner(self, hwnd):
        pid = w.DWORD()
        tid = self.desk.owner(hwnd, c.byref(pid))
        return (pid.value, tid)

    def menu(self):
        self.on_desktop()
        if self.owner(self.receiver) != (self.pid, self.tid):
            raise ValueError("The original tray receiver changed")
        info = GuiThread(size=c.sizeof(GuiThread))
        check(self.thread(self.tid, c.byref(info)), "GetGUIThreadInfo(menu owner)")
        candidates = []

        @self.visitor
        def collect(hwnd, _):
            cls = c.create_unicode_buffer(32)
            if (self.owner(hwnd) == (self.pid, self.tid) and self.desk.visible(hwnd)
                    and self.desk.window_class(hwnd, cls, len(cls)) and cls.value == "#32768"):
                candidates.append(hwnd)
            return True

        self.windows(self.tid, collect, 0)
        if not candidates:
            return None
        if len(candidates) != 1:
            raise ValueError("More than one visible popup on the original receiver thread")
        hwnd, = candidates
        owner = self.owner_window(hwnd, 4)
        if self.receiver not in (owner, info.menuOwner) or not info.flags & (4 | 16):
            return None
        handle = c.c_size_t()
        if self.owner(hwnd) != (self.pid, self.tid):
            raise ValueError("The selected popup changed before reading its menu handle")
        check(self.message(hwnd, 0x1e1, 0, 0, 3, 250, c.byref(handle)), "MN_GETHMENU(original popup)")
        menu = handle.value
        if not menu or self.count(menu) != 5:
            return None
        rows = []
        for i in range(5):
            state = self.state(menu, i, 0x400)
            if state == 0xffffffff:
                raise ValueError("The real menu item could not be read")
            name = c.create_unicode_buffer(128)
            length = self.string(menu, i, name, len(name), 0x400)
            if length >= len(name) - 1:
                raise ValueError("The menu item label exceeded the observer limit")
            r = w.RECT()
            check(self.rect(None, menu, i, c.byref(r)), "GetMenuItemRect")
            rows.append(dict(id=self.item_id(menu, i), text=name.value, separator=bool(state & 0x800),
                             enabled=not bool(state & 3), left=r.left, top=r.top, right=r.right, bottom=r.bottom))
        language = identify_menu(rows, self.labels)
        if self.owner(hwnd) != (self.pid, self.tid):
            raise ValueError("Popup identity changed during label readback")
        return dict(hwnd=hwnd, menu=menu, receiver=self.receiver, tid=self.tid, pid=self.pid, popupOwner=owner,
                    menuOwner=info.menuOwner, language=language, rows=rows)

    def verify_icon(self, surface, get_rect):
        self.on_desktop()
        hit = self.desk.point_window(w.POINT(*surface["point"]))
        if (self.owner(self.receiver) != (self.pid, self.tid) or get_rect(self.receiver) != dict(hresult=0, rect=surface["rect"])
                or hit != surface["hit"] or self.desk.ancestor(hit, 2) != surface["root"] or self.owner(hit)[0] != surface["shellPid"]):
            raise ValueError("The original physical Explorer icon moved before the right-click")
        dc = check(self.getdc(None), "GetDC(physical icon)")
        try:
            color = self.pixel(dc, *surface["point"])
        finally:
            check(self.release(None, dc), "ReleaseDC(physical icon)")
        expected = bytes.fromhex(surface["rgb"])
        if color == 0xffffffff or any(abs(((color >> (8*i)) & 255) - ch) > 8 for i, ch in enumerate(expected)):
            raise ValueError("The token-specific icon color changed before the right-click")
        return dict(hit=hit, root=surface["root"], ownerPid=self.owner(hit)[0], rect=surface["rect"], colorref=color)

    def place(self, point):
        self.on_desktop()
        previous = self.pointer()
        if previous != self.last:
            raise ValueError(f"The physical pointer moved from {self.last} to {previous} before positioning")
        check(self.move(*point), "SetPhysicalCursorPos(menu)")
        self.last = list(point)
        observed = self.pointer()
        if observed != self.last:
            raise ValueError(f"The physical pointer reached {observed}, expected {self.last}")

    def click(self, point, flags, valid):
        before = valid()
        self.place(point)
        end_wait = time.monotonic() + .5
        while True:
            at_point = valid()
            position = self.pointer()
            held = [k for k in (1, 2, 4, 0x10, 0x11, 0x12, 0x5b, 0x5c) if self.key_state(k) & 0x8000]
            if position == point and not held:
                break
            if time.monotonic() >= end_wait:
                raise ValueError(f"Physical input stayed at {position} with pressed keys {held}, expected {point} and no keys")
            time.sleep(.025)
        rows = (Input * 2)()
        for row, flag in zip(rows, flags):
            row.kind, row.mouse.flags, row.mouse.extra = 0, flag, self.tag
        begin = self.api.clock()
        queued = self.send(2, rows, c.sizeof(Input))
        end = self.api.clock()
        if queued != 2:
            if queued == 1 and self.pointer() == point:
                valid()
                self.send(1, c.byref(rows[1]), c.sizeof(Input))
            raise RuntimeError("Windows did not queue the complete mouse gesture")
        return dict(point=point, flags=list(flags), tag=self.tag, queued=queued, beginQpc=begin, endQpc=end,
                    before=before, atPoint=at_point)

    def select(self, menu, action):
        row = menu["rows"][2 * ACTIONS.index(action)]
        point = [(row["left"] + row["right"]) // 2, (row["top"] + row["bottom"]) // 2]
        def validate():
            current = self.menu()
            hit = self.desk.point_window(w.POINT(*point))
            if current != menu or hit != menu["hwnd"]:
                raise ValueError("The verified command no longer has the original physical popup hit")
            return dict(hit=hit, menu=current["menu"], ownerPid=self.owner(hit)[0], id=row["id"], text=row["text"])
        return self.click(point, (2, 4), validate)

    def restore(self):
        if self.pointer() != self.original:
            self.place(self.original)
        return self.pointer() == self.original
