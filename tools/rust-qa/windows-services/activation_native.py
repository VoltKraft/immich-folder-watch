"""Native handles, hit testing and input for the private Explorer fixture."""

import ctypes as c
from contextlib import contextmanager, ExitStack
from ctypes import wintypes as w
from pathlib import Path
import os
import subprocess
import sys
import time

from activation import DESKTOP, QA, module

sys.path.append(str(DESKTOP))
from job import Process, Startup
from win32 import Desktop, P, bind, check, ordinary_console, rect_values

OWNER_CLASS = "IFW RW02 synthetic tray receiver"
BAR = "Shell_TrayWnd"
OVERFLOW = ("NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")
ICON = 23


class Unavailable(Exception):
    """The native shell or input surface could not provide this observation."""


class Identifier(c.Structure):
    _fields_ = [("size", w.DWORD), ("owner", w.HWND), ("id", w.UINT), ("guid", c.c_uint32 * 4)]


class Mouse(c.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("data", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", c.c_size_t)]


class Input(c.Structure):
    _fields_ = [("kind", w.DWORD), ("mouse", Mouse)]


def expected_colors(token):
    first = [base + (int(token[i:i+2], 16) & 63) for i, base in ((0, 24), (2, 164), (4, 48))]
    return first, [255 - channel for channel in first]


def matches(sample, expected):
    return isinstance(sample, list) and len(sample) == 3 and all(abs(a - b) <= 8 for a, b in zip(sample, expected))


def center(rect):
    left, top, right, bottom = rect
    if not (2 <= right - left <= 256 and 2 <= bottom - top <= 256):
        raise Unavailable("The Shell did not return a bounded, nonempty icon rectangle")
    return [(left + right) // 2, (top + bottom) // 2]


def same_spot(a, b):
    return all(a[key] == b[key] for key in ("rect", "center", "hit", "root", "shellPid", "ownerHwnd", "iconId"))


def callback_ok(event, first_tick, last_tick):
    return (len(event) == 6 and event[0] >= 1 and event[1] in (0x400, 0x203) and event[2] == ICON
            and 0 <= event[3] <= 0xffffffff and 0 <= last_tick - first_tick < 10_000
            and first_tick <= event[5] <= last_tick)


class Native:
    def __init__(self, name):
        self.desk = Desktop()
        self.name = name
        self.owners = module("fixture_job_api", QA / "windows-performance/native.py")
        self.jobs = self.owners.Win32()
        self.k = self.jobs.kernel
        u, g = c.WinDLL("user32", use_last_error=True), c.WinDLL("gdi32", use_last_error=True)
        s = c.WinDLL("shell32", use_last_error=True)
        self.find = bind(u, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
        self.window_visitor = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.enumerate = bind(u, "EnumDesktopWindows", w.BOOL, w.HANDLE, self.window_visitor, w.LPARAM)
        self.getrect = bind(s, "Shell_NotifyIconGetRect", w.LONG, P(Identifier), P(w.RECT))
        self.dc = bind(u, "GetDC", w.HDC, w.HWND)
        self.release_dc = bind(u, "ReleaseDC", c.c_int, w.HWND, w.HDC)
        self.pixel = bind(g, "GetPixel", w.DWORD, w.HDC, c.c_int, c.c_int)
        self.cursor = bind(u, "GetPhysicalCursorPos", w.BOOL, P(w.POINT))
        self.move = bind(u, "SetPhysicalCursorPos", w.BOOL, c.c_int, c.c_int)
        self.send = bind(u, "SendInput", w.UINT, w.UINT, P(Input), c.c_int)
        self.key = bind(u, "GetAsyncKeyState", c.c_short, c.c_int)
        self.double_time = bind(u, "GetDoubleClickTime", w.UINT)
        self.tick = bind(self.k, "GetTickCount64", c.c_uint64)
        self.exit_code = bind(self.k, "GetExitCodeProcess", w.BOOL, w.HANDLE, P(w.DWORD))
        directory = bind(self.k, "GetSystemWindowsDirectoryW", w.UINT, w.LPWSTR, w.UINT)
        wide = c.create_unicode_buffer(32768)
        if not 0 < directory(wide, len(wide)) < len(wide):
            raise ValueError("The OS Windows directory could not be resolved")
        self.explorer = (Path(wide.value) / "explorer.exe").resolve(strict=True)
        if tuple(map(c.sizeof, (Identifier, Input, Startup, Process))) != (40, 40, 104, 24):
            raise ValueError("The observer requires the Windows x64 or ARM64 native ABI")

    def require_desktop(self):
        if not ordinary_console(self.desk.context(), self.name):
            raise Unavailable("The unique fixture desktop no longer owns the active unlocked console")

    def shell_path(self, process):
        capacity = w.DWORD(32768)
        wide = c.create_unicode_buffer(capacity.value)
        check(self.desk.image(process, 0, wide, c.byref(capacity)), "QueryFullProcessImageNameW")
        return Path(wide.value)

    def launch_child(self, command, **options):
        # Windows uses an explicitly inherited HDESK before consulting lpDesktop or Default.
        self.require_desktop()
        desktop = check(self.desk.open_named(self.name, 0, True, 0x02000000), "OpenDesktopW(private inheritance)")
        child = None
        try:
            if self.desk.name(desktop) != self.name:
                raise RuntimeError("The inheritable handle must identify the created fixture desktop")
            startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [desktop]})
            child = subprocess.Popen(command, startupinfo=startup, close_fds=True, **options)
        finally:
            if not self.desk.close(desktop):
                try:
                    check(False, "CloseDesktop(inheritable private handle)")
                finally:
                    if child is not None:
                        child.kill()
                        child.wait(timeout=5)
        return child

    @contextmanager
    def own_explorer(self, area, record):
        """Only launch the OS Explorer executable on the created desktop, already in an empty private job."""
        self.require_desktop()
        prior = self.find(BAR, None)
        record["taskbarBeforeLaunch"] = self.desk.window(prior)
        if prior:
            raise Unavailable("The new desktop already contained a taskbar before our process started")
        create = bind(self.k, "CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, w.LPVOID, w.LPVOID, w.BOOL,
                      w.DWORD, w.LPVOID, w.LPCWSTR, P(Startup), P(Process))
        resume = bind(self.k, "ResumeThread", w.DWORD, w.HANDLE)
        wait = bind(self.k, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        terminate = bind(self.k, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
        with ExitStack() as handles:
            job = self.jobs.new_job()
            handles.callback(lambda: check(self.jobs.close(job), "CloseHandle(own Explorer job)"))
            si, pi = Startup(), Process()
            si.size, si.desktop = c.sizeof(si), "WinSta0\\" + self.name
            cmd = c.create_unicode_buffer(subprocess.list2cmdline([str(self.explorer)]))
            check(create(str(self.explorer), cmd, None, None, False, 4, None, str(area), c.byref(si), c.byref(pi)),
                  "CreateProcessW(suspended Explorer on named desktop)")
            handles.callback(lambda: check(self.jobs.close(pi.process), "CloseHandle(Explorer)"))
            handles.callback(lambda: check(self.jobs.close(pi.thread), "CloseHandle(Explorer primary thread)"))
            assigned = False
            try:
                record.update(startupDesktop=si.desktop, processId=pi.pid, creationFileTime=self.jobs.process_identity(pi.process),
                              executable=str(self.explorer))
                self.jobs.assign_suspended(job, pi, self.explorer)
                assigned = True
                self.require_desktop()
                check(resume(pi.thread) == 1, "ResumeThread(own Explorer)")
                yield job
            finally:
                status = w.DWORD()
                check(self.exit_code(pi.process, c.byref(status)), "GetExitCodeProcess(own Explorer)")
                record["initialExplorerExitBeforeCleanup"] = status.value
                if not assigned:
                    check(terminate(pi.process, 1), "TerminateProcess(our suspended Explorer)")
                record["activeJobProcessesBeforeCleanup"] = self.jobs.active_job_processes(job)
                if record["activeJobProcessesBeforeCleanup"]:
                    check(self.jobs.terminate_job(job, 0), "TerminateJobObject(own Explorer only)")
                record["jobEmpty"] = self.jobs.wait_job_empty(job, 8)
                if not record["jobEmpty"] or wait(pi.process, 8000) != 0:
                    raise RuntimeError("The private Explorer processes did not complete cleanup")

    @contextmanager
    def shell_owner(self, job, record):
        until = time.monotonic() + 18
        while time.monotonic() < until:
            self.require_desktop()
            bar = self.find(BAR, None)
            if bar:
                break
            time.sleep(.12)
        else:
            record["shellWindowAfterAttempt"] = self.desk.window(self.desk.shell())
            raise Unavailable("Explorer did not create Shell_TrayWnd on the explicitly selected private desktop")
        window = self.desk.window(bar)
        pid = window["pid"]
        window.update(session=self.desk.pid_session(pid), threadDesktop=self.desk.name(self.desk.thread_desktop(window["tid"])))
        record["taskbar"] = window
        with ExitStack() as held:
            handle = check(self.jobs.open(0x1000, False, pid), "OpenProcess(query private taskbar)")
            held.callback(lambda: check(self.jobs.close(handle), "CloseHandle(taskbar process)"))
            belongs = w.BOOL()
            check(self.jobs.in_job(handle, job, c.byref(belongs)), "IsProcessInJob(private taskbar)")
            window.update(inOwnedExplorerJob=bool(belongs.value), creationFileTime=self.jobs.process_identity(handle))
            if (not belongs.value or self.shell_path(handle) != self.explorer or window["threadDesktop"] != self.name
                    or window["session"] != self.desk.pid_session(os.getpid())):
                raise Unavailable("The taskbar belongs to a different Explorer, desktop or session")
            yield bar, pid

    def validate_bar(self, bar, pid):
        self.require_desktop()
        d = self.desk
        actual = w.DWORD()
        tid = d.owner(bar, c.byref(actual))
        if (self.find(BAR, None) != bar or not d.visible(bar) or actual.value != pid
                or not tid or d.name(d.thread_desktop(tid)) != self.name):
            raise Unavailable("The pinned private Explorer no longer owns a visible taskbar")

    def visible_owners(self, job, subject, record):
        self.require_desktop()
        windows = []

        @self.window_visitor
        def visit(hwnd, _):
            if self.desk.visible(hwnd):
                pid = w.DWORD()
                self.desk.owner(hwnd, c.byref(pid))
                windows.append((hwnd, pid.value))
            return len(windows) <= 256

        # No window title, UI tree or unrelated desktop is read.
        desktop = check(self.desk.thread_desktop(self.desk.thread()), "GetThreadDesktop")
        if not self.enumerate(desktop, visit, 0) or not windows or subject.poll() is not None:
            raise Unavailable("The visible windows of the private input desktop could not be verified")
        record["visibleWindowCount"] = len(windows)
        for pid in {pid for _, pid in windows} - {subject.pid}:
            handle = self.jobs.open(0x1000, False, pid)
            if not handle:
                raise Unavailable("A visible window on the private desktop lacked a verifiable owner")
            try:
                member = w.BOOL()
                if not self.jobs.in_job(handle, job, c.byref(member)) or not member.value:
                    raise Unavailable("A visible window on the private input desktop belonged to another process tree")
            finally:
                check(self.jobs.close(handle), "CloseHandle(visible owner)")
        record["allVisibleWindowsInFixture"] = True

    def sample(self, proc, hwnd, bar, pid):
        self.validate_bar(bar, pid)
        d = self.desk
        receiver = d.window(hwnd)
        if (proc.poll() is not None or not receiver or receiver["pid"] != proc.pid or receiver["class"] != OWNER_CLASS
                or d.name(d.thread_desktop(receiver["tid"])) != self.name):
            raise Unavailable("The callback HWND is no longer owned by the original live Rust process and desktop")
        key = Identifier(size=c.sizeof(Identifier), owner=hwnd, id=ICON)
        rect = w.RECT()
        hr = self.getrect(c.byref(key), c.byref(rect))
        if hr != 0:
            raise Unavailable(f"Independent Shell_NotifyIconGetRect returned {hr:#x}")
        bounds = rect_values(rect)
        xy = center(bounds)
        hit = d.point_window(w.POINT(*xy))
        root = d.ancestor(hit, 2) if hit else None
        root_info, hit_info = d.window(root), d.window(hit)
        if (not root_info or not hit_info or root_info["pid"] != pid or hit_info["pid"] != pid
                or root_info["class"] not in (BAR, *OVERFLOW) or self.find(root_info["class"], None) != root
                or d.name(d.thread_desktop(root_info["tid"])) != self.name):
            raise Unavailable("The reported icon center did not hit this private Explorer notification area")
        handle = check(self.dc(None), "GetDC(one owned tray pixel)")
        try:
            color = self.pixel(handle, *xy)
        finally:
            check(self.release_dc(None, handle), "ReleaseDC")
        if color == 0xffffffff:
            raise Unavailable("The compositor did not expose the current fixture pixel")
        return {"rect": bounds, "center": xy, "hit": hex(hit), "root": hex(root), "rootClass": root_info["class"],
                "shellPid": pid, "ownerHwnd": hex(hwnd), "iconId": ICON, "rgb": [color >> n & 255 for n in (0, 8, 16)]}

    def input_pair(self, recheck, expected, receipt, label, deadline=None):
        live = recheck()
        if not same_spot(live, expected) or not matches(live["rgb"], expected_colors(self.name[6:])[1]):
            raise Unavailable("The second color or independently identified hit target changed before input")
        position = w.POINT()
        check(self.cursor(c.byref(position)), "GetPhysicalCursorPos")
        if ([position.x, position.y] != expected["center"] or
                any(self.key(vk) & 0x8000 for vk in (1, 2, 4, 16, 17, 18, 91, 92))):
            raise Unavailable("The cursor or keyboard/mouse state changed before the owned gesture")
        pair = (Input * 2)()
        pair[0].mouse.flags, pair[1].mouse.flags = 2, 4  # LEFTDOWN and LEFTUP queued together.
        self.require_desktop()
        now = self.tick()
        if deadline is not None and now >= deadline:
            receipt[label + "OutsideDoubleClickTime"] = True
            return
        receipt[label + "StartTick"] = now
        count = self.send(2, pair, c.sizeof(Input))
        receipt[label + "Sent"] = count
        if count == 1:
            self.require_desktop()
            if not same_spot(recheck(), expected):
                raise RuntimeError("The owned gesture was incomplete and its target changed")
            receipt[label + "CleanupUp"] = self.send(1, c.byref(pair[1]), c.sizeof(Input))
        if count != 2:
            raise RuntimeError("SendInput did not queue both events on the verified fixture center")
