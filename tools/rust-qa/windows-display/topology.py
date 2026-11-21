"""Read active display paths, per-monitor window DPI and the current WTS transport."""

from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w

from win32 import bind, check, rect_values, same_name

U32, I32, P = c.c_uint32, c.c_int32, c.POINTER


class Luid(c.Structure):
    _fields_ = [("low", U32), ("high", I32)]


class Source(c.Structure):
    _fields_ = [("adapter", Luid), ("id", U32), ("mode", U32), ("flags", U32)]


class Target(c.Structure):
    _fields_ = [("adapter", Luid), ("id", U32), ("mode", U32), ("technology", U32), ("rotation", U32),
                ("scaling", U32), ("refreshNumerator", U32), ("refreshDenominator", U32), ("scanline", U32),
                ("available", I32), ("flags", U32)]


class DisplayPath(c.Structure):
    _fields_ = [("source", Source), ("target", Target), ("flags", U32)]


class SourceMode(c.Structure):
    _fields_ = [("width", U32), ("height", U32), ("format", U32), ("x", I32), ("y", I32)]


class ModeData(c.Union):
    # The largest SDK variant is the 48-byte DISPLAYCONFIG_TARGET_MODE, aligned to UINT64.
    _fields_ = [("source", SourceMode), ("targetStorage", c.c_uint64 * 6)]


class Mode(c.Structure):
    _fields_ = [("type", U32), ("id", U32), ("adapter", Luid), ("data", ModeData)]


class SourceName(c.Structure):
    _fields_ = [("type", U32), ("size", U32), ("adapter", Luid), ("id", U32), ("device", c.c_wchar * 32)]


class MonitorInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("bounds", w.RECT), ("work", w.RECT), ("flags", w.DWORD), ("device", c.c_wchar * 32)]


@contextmanager
def physical_coordinates(api):
    previous = check(api.awareness(-4), "SetThreadDpiAwarenessContext(per-monitor v2)")
    try:
        yield
    finally:
        check(api.awareness(previous), "Restore the observer thread DPI context")


def protocol(api, session):
    if type(session) is not int or session <= 0:
        return {"status": "unavailable", "reason": "No interactive process session"}
    address, size = c.c_void_p(), w.DWORD()
    if not api.query_session(None, session, 16, c.byref(address), c.byref(size)):  # WTSClientProtocolType
        return {"status": "unavailable", "win32": c.get_last_error()}
    try:
        if not address or size.value != c.sizeof(w.USHORT):
            raise ValueError("Unexpected WTSClientProtocolType response")
        code = c.cast(address, P(w.USHORT)).contents.value
        return {"status": "observed", "code": code, "transport": {0: "console", 2: "RDP"}.get(code, "other")}
    finally:
        api.free_session(address)


def active_input(context, transport):
    session = context["session"]
    return (transport.get("status") == "observed" and same_name(context["windowStation"], "WinSta0")
            and context["stationVisible"] is True and same_name(context["threadDesktop"], "Default")
            and same_name(context["inputDesktop"], "Default") and context["threadReceivesInput"] is True
            and context["inputObjectReceivesInput"] is True and type(session) is int and session > 0
            and context["wts"].get("session") == session and context["wts"].get("connectionState") == 0
            and context["wts"].get("lockFlags") == 1 and (transport["code"] == 2 or
            (transport["code"] == 0 and context["activeConsoleSession"] == session)))


def rect_area(rect):
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def contains(outer, inner):
    return rect_area(inner) > 0 and outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


class Topology:
    def __init__(self):
        user = c.WinDLL("user32", use_last_error=True)
        self.callback = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, P(w.RECT), w.LPARAM)
        self.enum = bind(user, "EnumDisplayMonitors", w.BOOL, w.HDC, P(w.RECT), self.callback, w.LPARAM)
        self.metric = bind(user, "GetSystemMetrics", c.c_int, c.c_int)
        self.info = bind(user, "GetMonitorInfoW", w.BOOL, w.HANDLE, P(MonitorInfo))
        self.from_window = bind(user, "MonitorFromWindow", w.HANDLE, w.HWND, w.DWORD)
        self.create = bind(user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                           c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
        self.destroy = bind(user, "DestroyWindow", w.BOOL, w.HWND)
        self.get_context = bind(user, "GetWindowDpiAwarenessContext", w.HANDLE, w.HWND)
        self.get_awareness = bind(user, "GetAwarenessFromDpiAwarenessContext", c.c_int, w.HANDLE)
        self.equal_context = bind(user, "AreDpiAwarenessContextsEqual", w.BOOL, w.HANDLE, w.HANDLE)
        self.buffer_sizes = bind(user, "GetDisplayConfigBufferSizes", I32, U32, P(U32), P(U32))
        self.query = bind(user, "QueryDisplayConfig", I32, U32, P(U32), P(DisplayPath), P(U32), P(Mode), c.c_void_p)
        self.source_name = bind(user, "DisplayConfigGetDeviceInfo", I32, P(SourceName))

    def awareness(self, hwnd):
        return self.get_awareness(check(self.get_context(hwnd), "GetWindowDpiAwarenessContext"))

    def active_paths(self, by_device):
        def failure(api, status):
            return {"status": "unavailable" if status in (5, 50) else "failed", "api": api, "win32": status}
        for _ in range(5):
            num_paths, num_modes = U32(), U32()
            status = self.buffer_sizes(2, c.byref(num_paths), c.byref(num_modes))
            if status:
                return failure("GetDisplayConfigBufferSizes", status)
            if not 0 < num_paths.value <= 512 or not 0 < num_modes.value <= 2048:
                raise RuntimeError("Unexpected active display configuration size")
            paths, modes = (DisplayPath * num_paths.value)(), (Mode * num_modes.value)()
            status = self.query(2, c.byref(num_paths), paths, c.byref(num_modes), modes, None)  # QDC_ONLY_ACTIVE_PATHS
            if status == 122:  # ERROR_INSUFFICIENT_BUFFER if the topology changed between the two calls.
                continue
            if status:
                return failure("QueryDisplayConfig", status)
            rows = []
            for path in paths[:num_paths.value]:
                source, target = path.source, path.target
                name = SourceName(type=1, size=c.sizeof(SourceName), adapter=source.adapter, id=source.id)
                error = self.source_name(c.byref(name))
                row = {"sourceId": source.id, "targetId": target.id, "active": bool(path.flags & 1),
                       "available": bool(target.available), "outputTechnology": target.technology,
                       "rotation": target.rotation, "scaling": target.scaling,
                       "refresh": [target.refreshNumerator, target.refreshDenominator]}
                if not error:
                    row["monitor"] = by_device.get(name.device.casefold())
                else:
                    row["sourceNameError"] = error
                if source.mode < num_modes.value:
                    mode = modes[source.mode]
                    if (mode.type, mode.id, mode.adapter.high, mode.adapter.low) != (1, source.id, source.adapter.high, source.adapter.low):
                        raise RuntimeError("DisplayConfig source mode does not belong to its path")
                    s = mode.data.source
                    row["sourceMode"] = [s.x, s.y, s.width, s.height]
                rows.append(row)
            return {"status": "observed", "paths": rows}
        raise RuntimeError("The display configuration kept changing")

    def inventory(self, api):
        handles = []
        @self.callback
        def collect(handle, _dc, _bounds, _param):
            handles.append(handle)
            return True
        check(self.enum(None, None, collect, 0), "EnumDisplayMonitors")
        if not handles or len(handles) != len(set(handles)):
            raise RuntimeError("Expected distinct active monitor handles")
        devices, monitors, nonaddressable = {}, [], []
        for index, handle in enumerate(handles):
            info = MonitorInfo(size=c.sizeof(MonitorInfo))
            check(self.info(handle, c.byref(info)), "GetMonitorInfoW")
            bounds, work = rect_values(info.bounds), rect_values(info.work)
            if not contains(bounds, work):
                nonaddressable.append({"index": index, "reason": "No active work area"})
                continue
            # A hidden, nonactivating 2-pixel owned window reads real per-monitor DPI in its creation context.
            probe = check(self.create(0x08000080, "STATIC", "IFW display assessment", 0x80000000,
                                      (work[0] + work[2]) // 2, (work[1] + work[3]) // 2,
                                      2, 2, None, None, None, None), "CreateWindowExW(hidden DPI probe)")
            try:
                dpi = api.dpi(probe)
                if self.from_window(probe, 0) != handle:
                    nonaddressable.append({"index": index, "reason": "Its center belongs to another HMONITOR"})
                    continue
                if self.awareness(probe) != 2 or api.visible(probe) or not dpi:
                    raise RuntimeError("The hidden DPI witness did not belong to its monitor")
            finally:
                check(self.destroy(probe), "DestroyWindow(hidden DPI probe)")
            if info.device.casefold() in devices:
                raise RuntimeError("An addressable monitor has a duplicate GDI source identity")
            devices[info.device.casefold()] = index
            monitors.append({"index": index, "handle": hex(handle), "primary": bool(info.flags & 1),
                             "bounds": bounds, "work": work, "dpi": dpi})
        if not monitors:
            raise RuntimeError("No monitor accepted a private per-monitor DPI witness")
        return {"monitorCountMetric": self.metric(80), "nonaddressable": nonaddressable,
                "monitors": monitors, "displayConfig": self.active_paths(devices)}
