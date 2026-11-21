"""Observe renderer replacement, native input, status and inventory on the private desktop."""

import ctypes as c
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import time

from native import X11Observer, action, call
from observations import DirectoryReads
from session import checked_start, check_alive, wait_for
from x11 import bind


class WaylandCommits:
    """Count non-null buffer commits for the titled QA toplevel on the private compositor."""

    def __init__(self, stack, path):
        self.trace = stack.enter_context(path.open())
        self.xdg, self.toplevels = {}, {}
        self.titled, self.pending = set(), set()

    def drain(self):
        count = 0
        for line in self.trace:
            line = re.sub(r"\b((?:wl|xdg)_[a-z0-9_]+)@(?=\d+)", r"\1#", line)
            if match := re.search(r"get_xdg_surface\(new id xdg_surface#(\d+), wl_surface#(\d+)\)", line):
                self.xdg[match[1]] = match[2]
            elif match := re.search(r"xdg_surface#(\d+)\.get_toplevel\(new id xdg_toplevel#(\d+)\)", line):
                self.toplevels[match[2]] = self.xdg[match[1]]
            elif match := re.search(r'xdg_toplevel#(\d+)\.set_title\("Desktop input probe"\)', line):
                self.titled.add(self.toplevels[match[1]])
            elif match := re.search(r"wl_surface#(\d+)\.attach\(([^,]+),", line):
                sid = match[1]
                self.pending.discard(sid)
                if sid in self.titled and match[2].startswith("wl_buffer#"):
                    self.pending.add(sid)
            elif match := re.search(r"wl_surface#(\d+)\.commit\(", line):
                if match[1] in self.pending:
                    count += 1
                    self.pending.remove(match[1])
            elif match := re.search(r"wl_surface#(\d+)\.destroy\(", line):
                self.titled.discard(match[1])
                self.pending.discard(match[1])
        return count


def start_accessibility(stack):
    os.environ["GSETTINGS_BACKEND"] = "memory"
    executable = next(p for p in (Path("/usr/libexec/at-spi-bus-launcher"),
        Path("/usr/lib/at-spi2-core/at-spi-bus-launcher")) if p.is_file())
    log = Path("/qa/atspi.log")
    service = checked_start(stack, [str(executable), "--launch-immediately"], log)

    def available():
        check_alive(service, log)
        try:
            return call("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus.GetAddress")
        except subprocess.CalledProcessError:
            return None

    wait_for(available, 6, "The private accessibility bus did not start")
    call("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", "IsEnabled", "<true>")


class TrayStatus:
    def __init__(self, stack):
        from gi.repository import Gio, GLib
        self.gio, self.glib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.events = []
        subscription = self.bus.signal_subscribe("org.example.IfwGuiProbe", "org.kde.StatusNotifierItem",
            None, "/StatusNotifierItem", None, Gio.DBusSignalFlags.NONE,
            lambda _bus, _sender, _path, _interface, name, params: self.events.append([name, *params.unpack()]))
        stack.callback(self.bus.signal_unsubscribe, subscription)
        # Ensure the match rule has reached the private bus before launching the subject.
        self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetId", None, None, Gio.DBusCallFlags.NONE, 2000, None)

    def read(self, unavailable):
        expected = "NeedsAttention" if unavailable else "Active"
        context = self.glib.MainContext.default()
        while context.pending():
            context.iteration(False)
        properties = {}
        for name in ("Status", "Title"):
            result = self.bus.call_sync("org.example.IfwGuiProbe", "/StatusNotifierItem",
                "org.freedesktop.DBus.Properties", "Get", self.glib.Variant("(ss)", ("org.kde.StatusNotifierItem", name)),
                self.glib.VariantType.new("(v)"), self.gio.DBusCallFlags.NONE, 2000, None)
            properties[name], = result.unpack()
        title = "Graphics unavailable. Activate to retry. Background work continues." if unavailable else "Desktop input probe"
        if properties != {"Status": expected, "Title": title}:
            return None
        return dict(properties=properties, signals=list(self.events)) if (
            ["NewStatus", expected] in self.events and ["NewTitle"] in self.events) else None


def pixels(display, window):
    xlib = c.CDLL("libX11.so.6")
    capture = bind(xlib, "XGetImage", c.c_void_p, c.c_void_p, c.c_ulong, c.c_int, c.c_int,
                   c.c_uint, c.c_uint, c.c_ulong, c.c_int)
    pixel = bind(xlib, "XGetPixel", c.c_ulong, c.c_void_p, c.c_int, c.c_int)
    destroy = bind(xlib, "XDestroyImage", c.c_int, c.c_void_p)
    image = capture(display.display, window, 0, 0, 320, 160, c.c_ulong(-1).value, 2)
    if not image:
        return None
    try:
        values = [pixel(image, x, y) & 0xffffff for y in range(0, 160, 2) for x in range(0, 320, 3)]
        colors = len(set(values))
        if colors >= 4:
            raw = struct.pack(f"<{len(values)}I", *values)
            return dict(colors=colors, sampled_rgb_sha256=hashlib.sha256(raw).hexdigest())
        return None
    finally:
        destroy(image)


def worker_identity(pid):
    children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    result = []
    for child in children:
        proc = Path("/proc") / child
        if (proc / "exe").resolve().name == "ifw-performance-worker":
            start = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
            result.append(dict(pid=int(child), start_ticks=int(start)))
    if len(result) != 1:
        raise RuntimeError("Expected one live native comparison worker")
    return result[0]


def edit_draft(observer, process):
    from desktop_input import read_tree, shortcut, tap
    field = lambda: next((n for n in read_tree(process.pid) if n["name"] == "Dateiname" and n["role"] in ("entry", "text")), {})
    wait_for(lambda: field().get("text") == "Grüße – Sommer.jpg", 7, "Initial accessible draft missing")
    observer.focus_for_input()
    for _ in range(5):
        tap(observer, 0xff09)
        time.sleep(.1)
        if field().get("focused"):
            break
    if not field().get("focused"):
        raise RuntimeError("Could not focus the real filename editor")
    shortcut(observer, ord("a"), 0xffe3)
    tap(observer, 0xff08)
    wait_for(lambda: field().get("text") == "", 3, "Draft did not clear")
    for length, letter in enumerate("rw02", 1):
        tap(observer, ord(letter))
        wait_for(lambda: field().get("text") == "rw02"[:length], 3, "Keyboard edit did not reach native UI")
    return field


def exercise(stack, case, process, observer, damage, frames, log, media, tray, *, require_queue_completion):
    evidence = {}
    x11 = isinstance(observer, X11Observer)

    def has(marker):
        return marker in log.read_text()

    def took(callback, delay, why):
        return wait_for(lambda: check_alive(process, log) or callback(), delay, why)

    def presented():
        total = frames.read()
        return total if frames.ready else 0

    key = "window" if x11 else "surface"

    def drawn(generation, event_offset=0):
        def mapped_window():
            if not has(f"GRAPHICS_READY generation={generation}\n"):
                return None
            current = observer.poll()
            mapped = {current} if x11 else observer.mapped
            # The new surface can map before the compositor retires the old toplevel.
            return next((e[key] for e in reversed(observer.events[event_offset:])
                         if e["event"] == "map" and e[key] in mapped), None)

        window = took(mapped_window, 10, "Missing new window on the selected adapter")
        evidence = dict(generation=generation, native_window=window)
        if x11:
            evidence["frame_readback"] = took(lambda: pixels(observer.display, window), 5, "Missing native GUI pixels")
        evidence["draws_observed"] = took(damage.drain, 5, "No native drawing after engine initialization")
        evidence["total_present"] = took(presented, 5, "No successful native presentation") if frames else None
        return evidence

    worker = took(lambda: has("pass=1") and worker_identity(process.pid), 10, "Worker did not start")
    evidence["initial_worker"] = worker
    reads = DirectoryReads(stack, media)

    def background_change():
        start = time.monotonic()
        (media / "d0000/after-graphics-change.jpg").touch(exist_ok=False)
        took(lambda: has("INVENTORY_COMPLETE files=1 changed=1"), 12, "Worker did not reconcile after graphics fault")
        end = time.monotonic()
        _, _, observed = reads.scan_bounds(start, end)
        current = worker_identity(process.pid)
        if current != worker:
            raise RuntimeError("Worker identity changed after graphics fault")
        return dict(worker=current, directory_reads=observed, elapsed_seconds=round(end - start, 4))

    if case == "unavailable":
        took(lambda: has("GRAPHICS_UNAVAILABLE attempts=2"), 10, "Renderer initialization was not bounded")
        evidence["attention_without_window"] = took(lambda: tray.read(True), 5, "Missing actionable native status")
        evidence["background_after_failure"] = background_change()
        if observer.poll() or log.read_text().count("GRAPHICS_ATTEMPT") != 2 or (frames and frames.read()):
            raise RuntimeError("Failed initialization exposed a window, retried or submitted a frame")
        call("org.example.IfwGuiProbe", "/org/example/IfwGuiProbe", "org.freedesktop.Application.Activate", "{}")
        took(lambda: log.read_text().count("GRAPHICS_UNAVAILABLE attempts=2") == 2, 10, "Explicit retry did not finish")
        observer.poll()
        if (log.read_text().count("GRAPHICS_ATTEMPT") != 4
                or any(e["event"] == "map" for e in observer.events) or (frames and frames.read())):
            raise RuntimeError("Explicit activation exceeded its two-attempt budget")
        return evidence

    if case == "init-fallback":
        from desktop_input import read_tree
        evidence["working_fallback"] = drawn(2)
        if not has("GRAPHICS_RETRY generation=1") or has("GRAPHICS_READY generation=1"):
            raise RuntimeError("Fallback did not follow a real preferred-adapter failure")
        evidence["background_after_failure"] = background_change()
        notice = "Grafikstart fehlgeschlagen. Die Anzeige wurde wiederhergestellt."
        took(lambda: any(n["name"] == notice for n in read_tree(process.pid)), 5, "Missing recovered initialization status")
        evidence["accessible_status"] = notice
        return evidence

    first = drawn(1)
    evidence["initial_graphics"] = first
    field = edit_draft(observer, process)
    before = len(observer.events)
    damage.drain()
    if case == "driver-loss":
        (Path("/qa") / "fault-on-next-submit").touch(exist_ok=False)
        observer.key(0xffe1, True)
        observer.key(0xffe1, False)
    else:
        action("qa-destroy-graphics")
    if case == "unrelated-panic":
        exit_code = process.wait(timeout=8)
        if exit_code != 101 or not has("Unrelated UI test failure") or has("GRAPHICS_LOST") or has("GRAPHICS_RETRY"):
            raise RuntimeError("Unrelated UI panic entered graphics recovery")
        evidence["unrelated_error_propagated"] = True
        return evidence
    reason = "Unknown" if case == "driver-loss" else "Destroyed"
    wait_for(lambda: has(f"GRAPHICS_LOST generation=1 reason={reason}"), 5, "wgpu did not acknowledge the selected device loss")
    if case == "driver-loss" and not has("GRAPHICS_DRIVER_SIGNAL vkQueueSubmit returned VK_ERROR_DEVICE_LOST after VK_SUCCESS"):
        raise RuntimeError("No software-driver fault was observed at vkQueueSubmit")
    if case == "driver-loss" and require_queue_completion:
        lines = log.read_text().splitlines()
        completion = [(index, int(m[1])) for index, line in enumerate(lines)
                      if (m := re.fullmatch(r"GRAPHICS_DRIVER_QUEUE_IDLE result=0 elapsed_us=(\d+)", line))]
        signals = [i for i, line in enumerate(lines) if line.startswith("GRAPHICS_DRIVER_SIGNAL ")]
        losses = [i for i, line in enumerate(lines) if line == "GRAPHICS_LOST generation=1 reason=Unknown"]
        if len(completion) != 1 or len(signals) != 1 or len(losses) != 1 or not completion[0][0] < signals[0] < losses[0]:
            raise RuntimeError("Expected the real software queue to finish before the single injected result and loss callback")
        evidence["controlled_submit"] = dict(queue_submit="VK_SUCCESS", queue_wait_idle="VK_SUCCESS",
                                             wait_us=completion[0][1], reported="VK_ERROR_DEVICE_LOST")
    if case == "raw-loss":
        # The raw control continues through the original eframe draw after destruction.
        until = time.monotonic() + 2
        while process.poll() is None and time.monotonic() < until:
            observer.poll()
            time.sleep(.02)
        evidence["raw_exit_after_loss"] = process.poll()
        evidence["raw_mapped_after_loss"] = observer.poll()
        return evidence

    second = drawn(2, before)
    def retired():
        observer.poll()
        return any(e["event"] == "unmap" and e[key] == first["native_window"] for e in observer.events[before:])
    took(retired, 6, "The compositor did not retire the old native window")
    evidence["replacement_events"] = [{key: e[key], "event": e["event"]} for e in observer.events[before:]
                                      if e["event"] in ("map", "unmap")]
    if frames and second["total_present"] <= first["total_present"]:
        raise RuntimeError("Replacement device did not present")
    evidence["recovered_graphics"] = second
    evidence["retained_draft"] = took(lambda: field().get("text") == "rw02" and "rw02", 6, "Edited draft lost after recreation")
    from desktop_input import read_tree, tap
    restored = "Grafikgerät verloren. Die Anzeige wurde wiederhergestellt."
    took(lambda: any(n["name"] == restored for n in read_tree(process.pid)), 6, "Restored UI lacked the graphics status")
    evidence["accessible_status"] = restored
    observer.focus_for_input()
    took(lambda: field().get("focused"), 6, "The recovered window did not restore the focused editor")
    evidence["restored_editor_focus"] = True
    tap(observer, 0xff57)
    damage.drain()
    previous_presents = frames.read() if frames else None
    tap(observer, ord("x"))
    took(lambda: field().get("text") == "rw02x", 5, "Recovered editor did not accept another real key")
    evidence["post_recovery_edit_damage"] = took(damage.drain, 5, "No damage on recovery editor input")
    if frames:
        evidence["post_recovery_edit_presents"] = took(lambda: frames.read() - previous_presents, 5, "No native present on recovery editor input")
    tap(observer, 0xff08)
    took(lambda: field().get("text") == "rw02", 3, "Recovery editor could not restore the draft")
    if case == "during-paint" and not (has("GRAPHICS_IN_PAINT generation=1") and has("GRAPHICS_RENDER_INTERRUPTED")):
        raise RuntimeError("The real rendering operation did not exercise the confirmed staging-buffer unwind")
    if case == "repeated-loss":
        action("qa-destroy-graphics")
        took(lambda: has("GRAPHICS_UNAVAILABLE attempts=2") and not observer.poll(), 10, "Second loss did not stop automatic recreation")
        if not has("GRAPHICS_LOST generation=2 reason=Destroyed"):
            raise RuntimeError("Missing second independent device-loss callback")
        evidence["attention_without_window"] = took(lambda: tray.read(True), 5, "Missing actionable native status")
    evidence["background_after_failure"] = background_change()
    if case == "repeated-loss":
        if observer.poll() or log.read_text().count("GRAPHICS_ATTEMPT") != 2:
            raise RuntimeError("Exhausted renderer retried without a user request")
        before = len(observer.events)
        call("org.example.IfwGuiProbe", "/org/example/IfwGuiProbe", "org.freedesktop.Application.Activate", "{}")
        evidence["explicit_retry"] = drawn(3, before)
        took(lambda: field().get("text") == "rw02", 5, "Explicit retry lost the edited draft")
        evidence["attention_cleared"] = took(lambda: tray.read(False), 5, "Native status did not clear")
    return evidence
