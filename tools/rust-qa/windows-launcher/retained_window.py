"""Observe the lifetime, renderer and focus of the one retained Windows GUI root."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import re
import runpy
import time

from win32 import bind
from window_readback import desktop_windows, visible_surface

LIFETIME = Path(__file__).resolve().parents[1] / "windows-warm-window/window_lifetime.py"
WindowLifetime = runpy.run_path(str(LIFETIME), run_name="ifw_launcher_window_lifetime")["WindowLifetime"]


class ShowOrderUnavailable(Exception):
    """The two Windows uptime samples do not establish the order of activation and SHOW."""


def event_uptime(tick, near):
    # The observation is bounded to 35 seconds. Use the closest DWORD epoch, including a preceding tick.
    if not 0 <= tick <= 0xffffffff:
        return None
    delta = ((tick - near + 0x80000000) & 0xffffffff) - 0x80000000
    return near + delta


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

    def __init__(self, desk, windows, title, desktop_name, record, private=None):
        self.desk, self.windows, self.title, self.name = desk, windows, title, desktop_name
        self.record, self.private = record, private
        self.lifetime = WindowLifetime(windows.pid)
        self.hwnd = None
        self.start = 0

    def close(self):
        self.lifetime.close()

    def events(self, start=0):
        return [e for e in self.windows.events[start:] if e["hwnd"] == self.hwnd]

    def surface(self, row, phase):
        options = {"private": self.private, "membership_stage": "retained." + phase + ".surface"} if self.private else {}
        visible_surface(self.desk, self.name, self.windows.pid, self.hwnd, row, "surface", **options)

    def identity(self, phase, visible=None):
        owner = w.DWORD()
        caption = c.create_unicode_buffer(256)
        hwnd = self.hwnd
        tid = self.windows.owner(hwnd, c.byref(owner))
        if self.private is not None:
            self.private.verify(hwnd, "retained." + phase, visible=visible, tid=tid)
        if (not tid or owner.value != self.windows.pid
                or (self.private is None and self.desk.name(self.desk.thread_desktop(tid)) != self.name)
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
        self.record["first"] = self.identity("first", True)
        self.record["first"]["showEvent"] = self.events()[0]
        self.surface(self.record["first"], "first")
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
        row = self.record["hidden"] = self.identity("hidden", False)
        row["hideEvent"] = self.events(self.start)[0]
        # An ordinary HWND can legitimately use winit's original path. Attribute the
        # shortcut only when the compiled library identifies this same externally observed HWND.
        markers = [line for line in log.splitlines() if line.startswith("RETAINED_VISIBILITY ")]
        row["winitVisibilityShortcut"] = markers == [f"RETAINED_VISIBILITY first=hide hwnd={self.hwnd}"]
        if markers and not row["winitVisibilityShortcut"]:
            raise ValueError("The retained visibility marker does not identify this single observed root")
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
        row = self.record[phase] = {**self.identity(phase, True), "events": events}
        self.surface(row, phase)
        text = log()
        if text.splitlines().count("WINDOW_HIDDEN") != int("hidden" in self.record):
            raise ValueError("The retained GUI reported another close during activation")
        graphics(text, row)

    def sample_after_trigger(self, field, trigger, clock):
        """Query the owned GUI state only after its exact launcher or Shell Open was acknowledged."""
        row = self.record["afterTrigger"] = dict(field=field, trigger=trigger, pid=self.windows.pid, state="unconfirmed")
        if self.windows.visible() is not None:
            row["state"] = "visible"
            return
        if self.hwnd is not None:
            row["root"] = self.identity("afterTrigger")
            row["queryBeganMs"] = clock()
            if self.windows.is_visible(self.hwnd):
                row["state"] = "visible"
                return
            row["state"] = "retainedRootHidden"
        else:
            # Background startup has no known root yet. Verify the complete set of owned top-level windows.
            try:
                row["queryBeganMs"] = clock()
                scan = desktop_windows(self.desk, self.windows, self.windows.desktop, None)
            except OSError as exc:
                row["readError"] = str(exc)
                return
            row["desktopWindows"] = scan
            if (scan["desktop"] != self.name or len(scan["windows"]) != scan["ownedCount"]
                    or any(w["pid"] != self.windows.pid or w["desktop"] != self.name or w["titleAtLimit"]
                           or w["titleError"] or w["title"] == self.title for w in scan["windows"])):
                return
            row["state"] = "noGuiRoot"
            row["lifetimeCursor"] = len(self.lifetime.events)
        row["eventCursor"] = len(self.windows.events)

    def confirm_probe(self, probe, row, start):
        """An out-of-context hook may deliver an old event after a newer native window query."""
        trigger_observed = (probe["trigger"].get("observedMs") if probe["field"] == "callbackShow"
                            else row["releasedByMs"])
        query = probe.get("queryBeganMs")
        cursor = probe["eventCursor"]
        if (not isinstance(query, int) or not isinstance(trigger_observed, int)
                or not row["releasedByMs"] <= trigger_observed <= query <= row["observedMs"]):
            return "The native window query was outside the confirmed trigger interval"
        if row["showMs"] < query:
            return "The native SHOW was generated before the post-trigger window query"
        if cursor < start or [e for e in self.events(cursor) if e["event"] == "show"] != [row["showEvent"]]:
            return "The expected native SHOW was not delivered after the post-trigger window query"
        if probe["state"] == "noGuiRoot":
            life = [(kind, tick) for hwnd, kind, tick in self.lifetime.events[probe["lifetimeCursor"]:] if hwnd == self.hwnd]
            row["lifetimeAfterQuery"] = life
            if len(life) != 1 or life[0][0] != "create":
                return "The expected native CREATE was not delivered after the root-free window query"
            created = row["createMs"] = event_uptime(life[0][1], query)
            if created is None or not query <= created <= row["showMs"]:
                return "The native CREATE was not generated between the root-free query and SHOW"
        return None

    def activated_show(self, start, earliest, observed, field, *, released_by=None):
        """Return False when the native observations cannot establish strict causal order."""
        shows = [e for e in self.events(start) if e["event"] == "show"]
        if len(shows) != 1:
            raise ValueError("Expected exactly one native show of the original GUI after activation")
        latest = earliest if released_by is None else released_by
        event = shows[0]
        tick = event["winEventTimeMs"]
        row = self.record[field] = dict(earliestMs=earliest, releasedByMs=latest, observedMs=observed,
                                        showEvent=event, status="outsideInterval")
        # The event was already received when the observer sampled the upper endpoint.
        # A 32-bit event tick equal to a GetTickCount64 lower endpoint cannot establish which came first.
        show = row["showMs"] = event_uptime(tick, earliest)
        if (show is None or show > observed or not 0 <= earliest <= latest <= observed
                or observed - earliest > 35_000):
            raise ValueError("The retained window show was outside its native activation interval")
        row["distinctTicks"] = show > latest
        probe = self.record.get("afterTrigger", {})
        own_root = probe.get("state") == "retainedRootHidden" and probe["root"]["hwnd"] == self.hwnd
        if probe.get("state") == "noGuiRoot":
            own_root = all(w["hwnd"] != self.hwnd for w in probe["desktopWindows"]["windows"])
        if own_root and probe["field"] == field and probe["pid"] == self.windows.pid:
            contradiction = self.confirm_probe(probe, row, start)
            if contradiction is not None:
                row.update(status="inconclusive", reason=contradiction)
                return False
            row.update(status="ordered", basis="observedHiddenAfterTrigger")
            return True
        if show < earliest:
            raise ValueError("The retained window show was outside its native activation interval")
        if row["distinctTicks"]:
            row.update(status="ordered", basis="distinctTicks")
            return True
        row.update(status="inconclusive", reason="The SHOW and activation could not be ordered within the Windows timer tick")
        return False

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
