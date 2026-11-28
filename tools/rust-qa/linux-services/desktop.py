"""Drive watcher loss, stale acknowledgement, replacement and fallback against a real native GUI peer."""

import json
import os
from pathlib import Path
import sys
import time
from gi.repository import Gio, GLib
from session import checked_start, check_alive, stop, wait_for


WATCHER = "org.kde.StatusNotifierWatcher"
APP = "org.example.IfwServices"
OBJECT = "/org/example/IfwServices"
APPLICATION = "org.freedesktop.Application"


def probe(stack, display):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    result = {"display": os.environ["DISPLAY"], "transport": "private session D-Bus",
              "watcher": "synthetic protocol peer", "window": "native eframe wgpu process", "steps": []}
    def save(name, **fields):
        result["steps"].append({"step": name, **fields})
        Path("/qa/tray.json").write_text(json.dumps(result, indent=2) + "\n")
    def call(service, path, interface, method, arguments=None):
        return bus.call_sync(service, path, interface, method, arguments, None, Gio.DBusCallFlags.NONE, 3500, None).unpack()
    def observer(intent, availability, owner):
        expected = (intent, availability, owner)
        def check():
            try:
                observed = call(APP, OBJECT, APP + ".Observation", "State")
                return observed if observed == expected else None
            except GLib.Error:
                return None
        return wait_for(check, 5, f"Expected native service state {expected}")
    def peer(name, mode):
        log = Path("/qa") / f"watcher-{name}.log"
        process = checked_start(stack, [sys.executable, "/app/watcher.py", mode], log)
        wait_for(lambda: check_alive(process, log) or "READY " in log.read_text(), 5, "Watcher did not obtain its name")
        unique = next(line.split()[1] for line in log.read_text().splitlines() if line.startswith("READY "))
        return process, log, unique
    def native_apps(label, ready):
        gui_log = Path("/qa") / f"gui-{label}.log"
        gui = checked_start(stack, ["/probe/native-gui-assessment", "--background"], gui_log)
        wait_for(lambda: check_alive(gui, gui_log) or f"READY {ready}" in gui_log.read_text(),
                 8, "Native GUI did not reach its expected initial state")
        log = Path("/qa") / f"service-{label}.log"
        service = checked_start(stack, ["/probe/tray"], log)
        return gui, gui_log, service, log
    def action(name):
        call(APP, OBJECT, APPLICATION, "ActivateAction", GLib.Variant("(sava{sv})", (name, [], {})))
    def visible(expected):
        wait_for(lambda: bool(display.visible()) == expected, 10, f"Unexpected native X11 window state {expected}")
    def end(apps):
        gui, gui_log, service, log = apps
        action("quit")
        if gui.wait(timeout=8) or service.wait(timeout=8):
            raise RuntimeError("Native service or GUI failed to exit")
        if "DRAINED" not in log.read_text() or "DRAINED" not in gui_log.read_text():
            raise RuntimeError("Native shutdown acknowledgement missing")
        visible(False)
    def panel(method, service=WATCHER):
        return call(service, "/StatusNotifierWatcher", "org.example.WatcherControl", method)

    watcher, _, owner = peer("first", "accept")
    apps = native_apps("first", "BackgroundStartup Available")
    save("initial registration", state=observer("BackgroundStartup", "Available", owner))
    visible(False)
    panel("Activate")
    visible(True)
    action("close")
    visible(False)
    stop(watcher)
    save("watcher loss after user closes", state=observer("HiddenByUser", "Unavailable", ""))
    call(APP, OBJECT, APPLICATION, "Activate", GLib.Variant("(a{sv})", ({},)))
    visible(True)
    action("close")
    visible(False)
    save("desktop activation with no watcher", reopened=True, closed=True)
    delayed, delayed_log, old_owner = peer("delayed", "delay")
    wait_for(lambda: f"REGISTER {APP} " in delayed_log.read_text(), 4, "Stalled watcher never received registration")
    panel("Release", old_owner)
    refused, refused_log, _ = peer("refused", "refuse")
    wait_for(lambda: f"REGISTER {APP} " in refused_log.read_text(), 4, "Refusing watcher never received registration")
    save("replacement refused registration", state=observer("HiddenByUser", "Unavailable", ""))
    stop(refused)
    replacement, _, new_owner = peer("replacement", "accept")
    save("replacement acknowledged registration", state=observer("HiddenByUser", "Available", new_owner))
    panel("Acknowledge", old_owner)
    wait_for(lambda: "LATE_REPLIES 1" in delayed_log.read_text(), 3, "Old watcher did not complete its saved request")
    save("late previous acknowledgement", old=old_owner, current=observer("HiddenByUser", "Available", new_owner))
    visible(False)
    panel("Activate")
    visible(True)
    stop(delayed)
    stop(replacement)
    observer("Visible", "Unavailable", "")
    end(apps)
    save("last watcher lost while visible", reopened_from_replacement=True, quit_without_watcher=True)
    initial_refusal, _, _ = peer("initial-refusal", "refuse")
    apps = native_apps("refusal", "Visible Unavailable")
    visible(True)
    save("initial refusal reveals GUI", state=observer("Visible", "Unavailable", ""))
    end(apps)
    stop(initial_refusal)
