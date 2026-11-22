"""Read the owned launcher's Win32 windows on the selected desktop."""
import ctypes as c
from ctypes import wintypes as w

from win32 import bind, check


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
                    unavailable=ValueError):
    window = desk.window(hwnd)
    cloaked = w.DWORD()
    if not window or window["pid"] != pid or desk.name(desk.thread_desktop(window["tid"])) != desktop_name:
        raise ValueError("The visible GUI window did not belong to the original primary on its desktop")
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
        pid = w.DWORD()
        tid = windows.owner(hwnd, c.byref(pid))
        if not tid or pid.value != windows.pid:
            continue  # An already-destroyed or reused HWND cannot identify the primary.
        caption, kind = c.create_unicode_buffer(256), c.create_unicode_buffer(256)
        c.set_last_error(0)
        length = windows.caption(hwnd, caption, len(caption))
        title_error = 0 if length else c.get_last_error()
        c.set_last_error(0)
        class_error = 0 if desk.window_class(hwnd, kind, len(kind)) else c.get_last_error()
        visible = bool(windows.is_visible(hwnd))
        minimized = bool(desk.iconic(hwnd))
        if windows.owner(hwnd, c.byref(pid)) != tid or pid.value != windows.pid:
            continue
        rows.append(dict(hwnd=hwnd, pid=pid.value, tid=tid, desktop=desk.name(desk.thread_desktop(tid)),
                         title=printable(caption.value), titleAtLimit=length == len(caption) - 1,
                         titleError=title_error, windowClass=printable(kind.value), classError=class_error,
                         visible=visible, minimized=minimized))
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
