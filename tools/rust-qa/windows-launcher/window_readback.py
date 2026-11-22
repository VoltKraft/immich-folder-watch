"""Read the owned launcher's Win32 windows on the selected desktop."""
import ctypes as c
from ctypes import wintypes as w

from win32 import bind, check


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
