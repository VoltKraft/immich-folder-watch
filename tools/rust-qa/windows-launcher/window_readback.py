"""Read the owned launcher's Win32 windows on the selected desktop."""
import ctypes as c
from ctypes import wintypes as w
import os
import re

from win32 import bind, check

ROOT_CLASS = "Window Class"  # The qualified winit Windows platform's default root class.
RECEIVER_CLASS = "IFW RW02 synthetic tray receiver"  # The Rust receiver uses this for class and title.


class MonitorInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("monitor", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]


def monitor_work_area(hwnd):
    user = c.WinDLL("user32", use_last_error=True)
    from_window = bind(user, "MonitorFromWindow", w.HANDLE, w.HWND, w.DWORD)
    info = bind(user, "GetMonitorInfoW", w.BOOL, w.HANDLE, c.POINTER(MonitorInfo))
    handle = from_window(hwnd, 0)  # MONITOR_DEFAULTTONULL
    if not handle:
        return None
    monitor = MonitorInfo(size=c.sizeof(MonitorInfo))
    check(info(handle, c.byref(monitor)), "GetMonitorInfoW(visible primary)")
    r = monitor.work
    return [r.left, r.top, r.right, r.bottom]


def visible_surface(desk, desktop_name, pid, hwnd, result, stage, *, monitor_area=monitor_work_area,
                    unavailable=ValueError, private=None, membership_stage=None):
    window = desk.window(hwnd)
    cloaked = w.DWORD()
    if not window or window["pid"] != pid:
        raise ValueError("The visible GUI window did not belong to the original primary on its desktop")
    if private is None:
        if desk.name(desk.thread_desktop(window["tid"])) != desktop_name:
            raise ValueError("The visible GUI window did not belong to the original primary on its desktop")
    else:
        if private.name != desktop_name or private.windows.pid != pid:
            raise ValueError("The visible surface and private membership named different subjects")
        private.verify(hwnd, membership_stage or stage, visible=True, tid=window["tid"])
        if window["class"] != ROOT_CLASS:
            raise ValueError("The visible private surface did not have the primary GUI class")
    hr = desk.attribute(hwnd, 14, c.byref(cloaked), c.sizeof(cloaked))
    window.update(minimized=bool(desk.iconic(hwnd)), cloakHresult=hr,
                  cloaked=cloaked.value if hr == 0 else None)
    result[stage] = window
    if desktop_name == "Default" and window["cloaked"] != 0:
        raise unavailable("DWM did not confirm an uncloaked GUI window on the input desktop")
    rect = window["rect"]
    if (not desk.visible(hwnd) or window["minimized"]
            or not isinstance(rect, list) or rect[0] >= rect[2] or rect[1] >= rect[3]):
        raise ValueError("The native launcher window did not have a visible, non-minimized surface")
    if desktop_name == "Default":
        work = window["monitorWorkArea"] = monitor_area(hwnd)
        if work is None:
            raise ValueError("The activated GUI window did not intersect a real monitor")
        overlap = window["visibleWorkArea"] = [max(rect[0], work[0]), max(rect[1], work[1]),
                                               min(rect[2], work[2]), min(rect[3], work[3])]
        if overlap[0] >= overlap[2] or overlap[1] >= overlap[3]:
            raise ValueError("The activated GUI window did not intersect the monitor work area")


def printable(value):
    # A capped UTF-16 buffer can end between surrogate halves. Preserve its units in the UTF-8 receipt.
    return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "backslashreplace")


def window_identity(desk, windows, hwnd, expected_pid):
    pid = w.DWORD()
    tid = windows.owner(hwnd, c.byref(pid))
    row = dict(hwnd=hwnd, pid=pid.value, tid=tid)
    if not tid or pid.value != expected_pid:
        return row
    caption, kind = c.create_unicode_buffer(256), c.create_unicode_buffer(256)
    c.set_last_error(0)
    length = windows.caption(hwnd, caption, len(caption))
    title_error = 0 if length else c.get_last_error()
    c.set_last_error(0)
    class_length = desk.window_class(hwnd, kind, len(kind))
    class_error = 0 if class_length else c.get_last_error()
    c.set_last_error(0)
    thread_desktop = desk.thread_desktop(tid)
    desktop_name = desk.name(thread_desktop)
    row.update(desktop=desktop_name, threadDesktopHandleReturned=bool(thread_desktop),
               title=printable(caption.value), titleAtLimit=length == len(caption) - 1,
               titleError=title_error, windowClass=printable(kind.value), classError=class_error,
               classAtLimit=class_length == len(kind) - 1, visible=bool(windows.is_visible(hwnd)),
               minimized=bool(desk.iconic(hwnd)))
    final_tid = windows.owner(hwnd, c.byref(pid))
    if (pid.value, final_tid) != (expected_pid, tid):
        row["ownerChanged"] = dict(pid=pid.value, tid=final_tid)
    return row


class PrivateMembership:
    """Prove top-level HWND membership on the held private HDESK, bracketed by identity checks."""

    def __init__(self, desk, windows, name, desktop, witness, proc, initial_tid, creation, api, title, record):
        if (not desktop or not witness or windows.desktop != desktop or windows.pid != proc.pid
                or not initial_tid or not creation or not re.fullmatch(r"IfwQa_(?:Launcher|Tray)_[0-9a-f]{32}", name)):
            raise ValueError("Expected the owned named private desktop, witness and retained primary")
        self.desk, self.windows, self.name, self.desktop = desk, windows, name, desktop
        self.witness, self.observer_tid = witness, desk.thread()
        self.proc, self.initial_tid, self.creation, self.api = proc, initial_tid, creation, api
        self.title, self.record = title, record

    def process(self):
        return dict(pid=self.proc.pid, creation100ns=self.api.process_identity(int(self.proc._handle)),
                    exit=self.proc.poll())

    def verify(self, hwnd, stage, *, visible=None, tid=None, receiver=False):
        desk, windows = self.desk, self.windows
        row = self.record[stage] = dict(desktopHandle=self.desktop, desktop=desk.name(self.desktop),
                                        receivesInput=desk.receiving_input(self.desktop), qualified=False)
        if (row["desktop"] != self.name or row["receivesInput"] is not False or not hwnd or hwnd == self.witness
                or desk.thread() != self.observer_tid):
            raise ValueError("The private desktop, its witness or its observer thread changed")
        expected_process = dict(pid=windows.pid, creation100ns=self.creation, exit=None)
        target_tid = tid if receiver else self.initial_tid
        if not target_tid or (tid is not None and tid != target_tid):
            raise ValueError("The private HWND did not identify its expected thread")
        title, kind = (RECEIVER_CLASS, RECEIVER_CLASS) if receiver else (self.title, ROOT_CLASS)
        row["beforeProcess"] = self.process()
        if row["beforeProcess"] != expected_process:
            raise ValueError("The retained primary changed before private desktop enumeration")

        def identities():
            return {"witness": window_identity(desk, windows, self.witness, os.getpid()),
                    "target": window_identity(desk, windows, hwnd, windows.pid)}

        row["before"] = identities()
        counts = row["enumerated"] = dict(witness=0, target=0)

        @windows.enum_callback
        def visit(candidate, _):
            if candidate == self.witness:
                counts["witness"] += 1
            elif candidate == hwnd:
                counts["target"] += 1
            return True

        check(windows.enumerate(self.desktop, visit, 0), "EnumDesktopWindows(private HWND membership)")
        row["after"] = identities()
        row["afterProcess"] = self.process()
        row["desktopAfter"] = dict(name=desk.name(self.desktop), receivesInput=desk.receiving_input(self.desktop))
        if row["desktopAfter"]["name"] != self.name or row["desktopAfter"]["receivesInput"] is not False:
            raise ValueError("The selected desktop changed while checking private HWND membership")
        if row["afterProcess"] != expected_process:
            raise ValueError("The retained primary changed during private desktop enumeration")
        if counts != dict(witness=1, target=1):
            raise ValueError("The owned private desktop did not enumerate the unique witness and primary HWND")
        for phase in (row["before"], row["after"]):
            for key, pid, thread, caption, window_class, shown in (
                    ("witness", os.getpid(), self.observer_tid, self.name, "static", False),
                    ("target", windows.pid, target_tid, title, kind, visible)):
                obj = phase[key]
                actual_class = obj.get("windowClass", "")
                if key == "witness":
                    actual_class = actual_class.casefold()  # The predefined STATIC class is case-insensitive.
                desktop = obj.get("desktop")
                if ((obj["pid"], obj["tid"]) != (pid, thread) or "ownerChanged" in obj
                        or obj.get("title") != caption or actual_class != window_class
                        or obj["titleError"] or obj["classError"] or obj["titleAtLimit"] or obj["classAtLimit"]
                        or (shown is not None and obj["visible"] is not shown)
                        or not (desktop == self.name or (key == "target" and desktop == {"win32Error": 5}))):
                    raise ValueError(f"The private {key} HWND identity or thread desktop was inconsistent")
        row["qualified"] = True
        return row["after"]["target"]


def desktop_windows(desk, windows, desktop, witness):
    handles = []
    found_witness = None if witness is None else False
    count = 0

    @windows.enum_callback
    def visit(hwnd, _data):
        nonlocal found_witness, count
        if hwnd == witness:
            found_witness = True
        pid = w.DWORD()
        windows.owner(hwnd, c.byref(pid))
        if pid.value == windows.pid:
            count += 1
            if len(handles) < 32:
                handles.append(hwnd)
        return True

    check(windows.enumerate(desktop, visit, 0), "EnumDesktopWindows(launcher readback)")
    rows = []
    for hwnd in handles:
        row = window_identity(desk, windows, hwnd, windows.pid)
        if "desktop" in row and "ownerChanged" not in row:
            rows.append(row)
    return dict(desktop=desk.name(desktop), witnessSeen=found_witness, ownedCount=count, windows=rows)


def snapshot(desk, windows, desktop, witness, thread_id, creation):
    row = desktop_windows(desk, windows, desktop, witness)
    thread_desktop = desk.thread_desktop(thread_id)
    actual = desk.name(thread_desktop)
    row.update(primaryPid=windows.pid, primaryCreation100ns=creation, initialThread=thread_id, initialThreadDesktop=actual)
    if isinstance(actual, str) and isinstance(row["desktop"], str) and actual.casefold() != row["desktop"].casefold():
        # The initial GUI thread chose a different desktop. Read only HWNDs owned by the retained primary PID.
        try:
            row["initialThreadWindows"] = desktop_windows(desk, windows, thread_desktop, None)
        except OSError as exc:
            row["initialThreadWindowError"] = str(exc)
    return row


def check_private_snapshot(row, name):
    if (not row["witnessSeen"] or row["desktop"] != name
            or row["initialThreadDesktop"] not in (name, {"win32Error": 5})):
        raise ValueError("The private desktop witness or primary's initial thread desktop was inconsistent")
    for window in row["windows"]:
        reported = window["desktop"]
        if ((isinstance(reported, str) and reported != name)
                or (window["windowClass"] in (ROOT_CLASS, RECEIVER_CLASS)
                    and reported not in (name, {"win32Error": 5}))):
            raise ValueError("A window readback contradicted the selected private desktop")


def paint_control(user, desk, hwnd, desktop, name, record):
    """Ask only the hidden observer-owned STATIC window to paint and show on its non-input desktop."""
    redraw = bind(user, "RedrawWindow", w.BOOL, w.HWND, c.c_void_p, w.HANDLE, w.UINT)
    peek = bind(user, "PeekMessageW", w.BOOL, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT)
    dispatch = bind(user, "DispatchMessageW", w.LPARAM, c.POINTER(w.MSG))
    show = bind(user, "ShowWindow", w.BOOL, w.HWND, c.c_int)
    if desk.name(desk.thread_desktop(desk.thread())) != name or desk.receiving_input(desktop) is not False:
        raise ValueError("The paint control requires its original non-input desktop")
    wm_paint = 0x000F

    def request_paint():
        message = w.MSG()
        check(redraw(hwnd, None, None, 2), "RedrawWindow(private witness, RDW_INTERNALPAINT)")
        received = bool(peek(c.byref(message), hwnd, wm_paint, wm_paint, 1))
        if received:
            if message.hWnd != hwnd or message.message != wm_paint:
                raise ValueError("Unexpected private paint message")
            dispatch(c.byref(message))
        return received

    record["initiallyVisible"] = bool(desk.visible(hwnd))
    record["hiddenPaintMessage"] = request_paint()
    try:
        show(hwnd, 4)  # SW_SHOWNOACTIVATE on this control only.
        record["showVisible"] = bool(desk.visible(hwnd))
        record["shownPaintMessage"] = request_paint()
    finally:
        show(hwnd, 0)
        record["visibleAfterHide"] = bool(desk.visible(hwnd))
    if record["initiallyVisible"] or not record["showVisible"] or record["visibleAfterHide"]:
        raise ValueError("The private witness did not independently reproduce native show and hide")
