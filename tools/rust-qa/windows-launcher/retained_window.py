"""Observe the lifetime, renderer and focus of the one retained Windows GUI root."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import re
import runpy
import time

from win32 import bind
from window_readback import visible_surface

LIFETIME = Path(__file__).resolve().parents[1] / "windows-warm-window/window_lifetime.py"
WindowLifetime = runpy.run_path(str(LIFETIME), run_name="ifw_launcher_window_lifetime")["WindowLifetime"]


class GuiThreadInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("flags", w.DWORD), ("active", w.HWND), ("focus", w.HWND),
                ("capture", w.HWND), ("menu", w.HWND), ("moveSize", w.HWND), ("caret", w.HWND), ("rect", w.RECT)]


def focus_sample(desk, windows, hwnd):
    """Query the owned GUI thread without activating or attaching to an input queue."""
    owner = w.DWORD()
    tid = windows.owner(hwnd, c.byref(owner))
    if not tid or owner.value != windows.pid:
        raise ValueError("The window for the passive focus observation changed owners")
    get = bind(c.WinDLL("user32", use_last_error=True), "GetGUIThreadInfo", w.BOOL, w.DWORD, c.POINTER(GuiThreadInfo))
    info = GuiThreadInfo(size=c.sizeof(GuiThreadInfo))
    foreground = desk.foreground() == hwnd
    if not get(tid, c.byref(info)):
        return dict(thread=tid, foreground=foreground, active=False, focused=False, queryError=c.get_last_error())
    child_pid = w.DWORD()
    own_focus = bool(info.focus and windows.owner(info.focus, c.byref(child_pid)) == tid
                     and child_pid.value == windows.pid and windows.ancestor(info.focus, 2) == hwnd)
    return dict(thread=tid, foreground=foreground and desk.foreground() == hwnd, active=info.active == hwnd,
                focused=own_focus, queryError=0)


def graphics(log, record, *, before_quit=True):
    rows = log.splitlines()
    fields = {name: [line for line in rows if line.startswith(name + " ")]
              for name in ("GRAPHICS_ATTEMPT", "GRAPHICS_MEMORY", "GRAPHICS_READY", "ADAPTER",
                           "GRAPHICS_SURFACE", "GRAPHICS_PRESENT")}
    record["renderer"] = fields
    if (fields["GRAPHICS_ATTEMPT"] != ["GRAPHICS_ATTEMPT generation=1 policy=preferred"]
            or fields["GRAPHICS_MEMORY"] != ["GRAPHICS_MEMORY generation=1 hint=MemoryUsage"]
            or fields["GRAPHICS_READY"] != ["GRAPHICS_READY generation=1"] or len(fields["ADAPTER"]) != 1
            or not fields["ADAPTER"][0].startswith("ADAPTER Dx12 ")
            or any(line.startswith(("DISPATCH", "WINDOW_WAKE ", "WINDOW_HIDDEN_PAINT ", "WGPU_ALLOCATOR ",
                                    "GRAPHICS_ERROR ", "GRAPHICS_LOST ", "GRAPHICS_RETRY ")) for line in rows)
            or before_quit and any(line.startswith("WINDOW_RELEASED ") for line in rows)):
        raise ValueError("The retained GUI must use exactly its first ordinary DX12 device")
    if not before_quit:
        releases = [line for line in rows if line.startswith("WINDOW_RELEASED ")]
        drained = [line for line in rows if line.startswith("DRAINED ")]
        if (len(releases) != 1 or not re.fullmatch(r"WINDOW_RELEASED passes=[1-9]\d*", releases[0])
                or drained != [releases[0].replace("WINDOW_RELEASED ", "DRAINED ", 1)]):
            raise ValueError("The single retained renderer must complete real UI passes and drain during quit")


class RetainedWindow:
    """Watch this primary before releasing its barrier and until the ordinary quit request."""

    def __init__(self, desk, windows, title, desktop_name, record):
        self.desk, self.windows, self.title, self.name = desk, windows, title, desktop_name
        self.record = record
        self.lifetime = WindowLifetime(windows.pid)
        self.hwnd = None
        self.start = 0

    def close(self):
        self.lifetime.close()

    def events(self, start=0):
        return [e for e in self.windows.events[start:] if e["hwnd"] == self.hwnd]

    def identity(self):
        owner = w.DWORD()
        caption = c.create_unicode_buffer(256)
        hwnd = self.hwnd
        tid = self.windows.owner(hwnd, c.byref(owner))
        if (not tid or owner.value != self.windows.pid or self.desk.name(self.desk.thread_desktop(tid)) != self.name
                or self.windows.ancestor(hwnd, 2) != hwnd
                or not self.windows.caption(hwnd, caption, len(caption)) or caption.value != self.title):
            raise ValueError("The retained root lost its native title, owner or desktop")
        lifetime = [list(row) for row in self.lifetime.events if row[0] == hwnd]
        self.record["lifetimeBeforeQuit"] = lifetime
        if [row[1] for row in lifetime] != ["create"]:
            raise ValueError("The retained root was created again or destroyed during its observed lifetime")
        return dict(hwnd=hwnd, pid=owner.value, tid=tid, title=caption.value, desktop=self.name)

    def first(self, hwnd, log, wait):
        self.hwnd = hwnd
        wait(lambda: self.events() and any(r[0] == hwnd for r in self.lifetime.events),
             "No native show and creation events for the first retained GUI window")
        if [e["event"] for e in self.events()] != ["show"] or self.windows.visible() != hwnd:
            raise ValueError("The first retained HWND did not have one visible startup")
        self.record["first"] = self.identity()
        self.record["first"]["showEvent"] = self.events()[0]
        visible_surface(self.desk, self.name, self.windows.pid, hwnd, self.record["first"], "surface")
        text = log()
        if "WINDOW_HIDDEN" in text.splitlines():
            raise ValueError("The retained GUI had already been closed before its first visible observation")
        graphics(text, self.record["first"])

    def close_window(self):
        self.windows.pump()
        self.start = len(self.windows.events)
        self.windows.close_window(self.hwnd)

    def hidden(self, log):
        if self.windows.visible() is not None or not self.events(self.start) or "WINDOW_HIDDEN" not in log.splitlines():
            return False
        if (self.windows.is_visible(self.hwnd) or [e["event"] for e in self.events(self.start)] != ["hide"]
                or log.splitlines().count("WINDOW_HIDDEN") != 1):
            raise ValueError("The retained HWND did not remain hidden after its genuine close")
        row = self.record["hidden"] = self.identity()
        row["hideEvent"] = self.events(self.start)[0]
        graphics(log, row)
        return True

    def opened(self, hwnd, log, wait):
        if hwnd != self.hwnd:
            raise ValueError("Opening the retained GUI replaced its HWND")
        wait(lambda: any(e["event"] == "show" for e in self.events(self.start)),
             "No native show of the retained HWND after activation")
        self.check_visible(log, "reopened")

    def check_visible(self, log, phase):
        if self.windows.visible() != self.hwnd:
            raise ValueError("The observed retained GUI is no longer visible")
        events = self.events(self.start)
        expected = ["hide", "show"] if "hidden" in self.record else ["show"]
        if [e["event"] for e in events] != expected:
            raise ValueError("Unexpected native visibility events for the retained root")
        row = self.record[phase] = {**self.identity(), "events": events}
        visible_surface(self.desk, self.name, self.windows.pid, self.hwnd, row, "surface")
        text = log()
        if text.splitlines().count("WINDOW_HIDDEN") != int("hidden" in self.record):
            raise ValueError("The retained GUI reported another close during activation")
        graphics(text, row)

    def activated_show(self, start, earliest, observed, field):
        shows = [e for e in self.events(start) if e["event"] == "show"]
        if len(shows) != 1:
            raise ValueError("Expected exactly one native show of the original GUI after activation")
        # WinEvent supplies a 32-bit uptime tick. Extend it inside the observed 64-bit interval.
        elapsed = (shows[0]["winEventTimeMs"] - earliest) & 0xffffffff
        if not 0 <= observed - earliest <= 35_000 or elapsed > observed - earliest:
            raise ValueError("The retained window show was outside its native activation interval")
        self.record[field] = dict(earliestMs=earliest, observedMs=observed, showEvent=shows[0])

    def focus(self, record):
        if self.name != "Default":
            record.update(applicable=False, reason="Private non-input desktop")
            return
        end = time.monotonic() + 2
        record.update(applicable=True, observed=False, samples=0)
        while True:
            record["sameWindowVisible"] = self.windows.visible() == self.hwnd
            if not record["sameWindowVisible"]:
                break
            sample = focus_sample(self.desk, self.windows, self.hwnd)
            record.update(samples=record["samples"] + 1, lastSample=sample)
            if sample["foreground"] and sample["active"] and sample["focused"]:
                record["observed"] = True
                return
            if time.monotonic() >= end:
                break
            time.sleep(.05)
        raise ValueError("The retained GUI did not acquire foreground and keyboard focus on its original input desktop")
