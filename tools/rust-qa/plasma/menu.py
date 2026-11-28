"""Select three real Plasma menu entries on the fixture's private X server."""
import os
import json
from pathlib import Path
import re
import select
import subprocess

from gi.repository import Atspi, Gdk, GLib

from observe import (ITEM, WATCHER, WORK, call, capture, check_alive, checked_start, click_item, describe,
                     desktop_nodes, move_pointer, owner, press_button, properties, subject_window, wait_for)


INTERFACE = "com.canonical.dbusmenu"
GERMAN = ["GUI öffnen", "Neustart", "Beenden"]
ENGLISH = ["Open GUI", "Restart", "Quit"]


def layout(bus, app, path, labels):
    revision, (root, _, children) = call(bus, app["owner"], path, INTERFACE, "GetLayout",
                                        GLib.Variant("(iias)", (0, -1, [])))
    if root != 0 or [(row[0], row[1].get("label")) for row in children] != list(enumerate(labels, 1)):
        raise ValueError(f"Unexpected native menu layout {children}")
    return revision


def visible_rows(pid, labels):
    found = {}
    for node in desktop_nodes(pid):
        if node.get_role() != Atspi.Role.MENU_ITEM or not node.get_state_set().contains(Atspi.StateType.SHOWING):
            continue
        name = node.get_name()
        if name in labels:
            if name in found:
                return None
            entry = describe(node)
            x, y, w, h = entry["rect"]
            if x < 0 or y < 0 or w < 5 or h < 5 or x+w > 1280 or y+h > 900:
                return None
            found[name] = entry
    if set(found) == set(labels):
        rows = [found[label] for label in labels]
        if all(a["rect"][1] + a["rect"][3] <= b["rect"][1] for a, b in zip(rows, rows[1:])):
            return rows
    return None


def popup_rows(shell, labels):
    # Qt's popup is a native override-redirect window. Some Plasma builds
    # export the panel to AT-SPI without exporting QMenu's popup children.
    listing = subprocess.check_output(["xwininfo", "-root", "-tree"], text=True)
    candidates = []
    for line in listing.splitlines():
        row = re.search(r"^\s*(0x[0-9a-fA-F]+) .*? (\d+)x(\d+)[+-]\d+[+-]\d+\s+([+-]\d+)([+-]\d+)\s*$", line)
        if not row:
            continue
        xid, width, height, left, top = (int(row[1], 16), *map(int, row.groups()[1:]))
        if not (36 <= width <= 512 and 24 <= height <= 240 and
                0 <= left <= 1280-width and 0 <= top <= 900-height):
            continue
        props = properties(xid)
        if ("_NET_WM_WINDOW_TYPE_POPUP_MENU" in props and
                re.search(rf"_NET_WM_PID\(CARDINAL\) = {shell}$", props, re.M) and
                "Map State: IsViewable" in subprocess.check_output(["xwininfo", "-id", hex(xid)], text=True)):
            candidates.append((xid, left, top, width, height))
    if len(candidates) != 1:
        return None
    xid, left, top, width, height = candidates[0]
    pix = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), left, top, width, height)
    if not pix:
        return None
    data, stride, channels = pix.get_pixels(), pix.get_rowstride(), pix.get_n_channels()
    # Compare the text area to the unprinted trailing margin on the same scanline.
    bands = []
    for y in range(4, height-4):
        offset = y*stride
        bg = data[offset+(width-7)*channels:offset+(width-7)*channels+3]
        count = sum(max(abs(data[offset+x*channels+i]-bg[i]) for i in range(3)) >= 65
                    for x in range(8, width-9))
        if count < 2:
            continue
        if bands and y-bands[-1][-1] <= 3:
            bands[-1].append(y)
        else:
            bands.append([y])
    if len(bands) != len(labels) or any(len(b) < 5 for b in bands):
        return None
    rows = [dict(name=label, rect=[left+7, top+b[0], width-14, b[-1]-b[0]+1])
            for label, b in zip(labels, bands)]
    return dict(xid=xid, rows=rows, rect=[left, top, width, height])


def select_row(x, shell, labels, command):
    icon = click_item(x, shell, f"menu-{command}", button_number=3)
    try:
        popup = wait_for(lambda: popup_rows(shell, labels), 8, "No physical Plasma popup with three drawn rows")
        rows = popup["rows"]
    except TimeoutError:
        capture(f"unmatched-menu-{command}")
        nodes = [dict(describe(n), showing=n.get_state_set().contains(Atspi.StateType.SHOWING))
                 for n in desktop_nodes(shell)]
        (WORK / f"plasma-nodes-{command}.json").write_text(json.dumps(nodes, ensure_ascii=False, indent=2))
        raise
    left, top, width, height = rows[command-1]["rect"]
    px, py = left + width//2, top + height//2
    _, path = move_pointer(x, px, py)
    if (not any(re.search(rf"_NET_WM_PID\(CARDINAL\) = {shell}$", props, re.M)
                and "_NET_WM_WINDOW_TYPE_POPUP_MENU" in props for _, props in path)
            or not any(handle == popup["xid"] for handle, _ in path)):
        raise ValueError(f"The physical click location does not belong to the original menu: {path}")
    exposed = visible_rows(shell, labels)
    pixels = capture(f"selected-row-{command}", rows[command-1]["rect"])
    capture(f"popup-{command}", popup["rect"])
    press_button(x, 1)
    return dict(icon=icon, rows=rows, command=command, point=[px, py], selectedPixels=pixels,
                popupXid=hex(popup["xid"]), accessibleRows=exposed)


def worker(stack, primary, log, index):
    def spawned():
        pids = re.findall(r"^INVENTORY_WORKER pid=(\d+)$", log.read_text(), re.M)
        return int(pids[index]) if len(pids) > index else None

    pid = wait_for(lambda: check_alive(primary, log) or spawned(), 10, "No inventory worker was announced")
    fd = os.pidfd_open(pid)
    stack.callback(os.close, fd)
    path = Path(f"/proc/{pid}")
    fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
    if int(fields[1]) != primary.pid or not (path / "exe").samefile("/app/ifw-performance-worker"):
        raise ValueError("Inventory process lacks the expected parent or executable")
    watch = select.poll()
    watch.register(fd, select.POLLIN)
    if watch.poll(0):
        raise ValueError("The observed inventory process has already exited")
    return dict(pid=pid, parent=primary.pid, startTicks=int(fields[19])), watch


def restart_watcher(bus, app, report, trace):
    kded = report["services"]["org.kde.kded5"]
    arguments = GLib.Variant("(s)", ("statusnotifierwatcher",))
    before = owner(bus, WATCHER)
    if before["owner"] != kded["owner"]:
        raise ValueError("The original private KDED does not own the watcher")
    trace_start = len(trace.read_text())
    if call(bus, kded["owner"], "/kded", "org.kde.kded5", "unloadModule", arguments) != (True,):
        raise ValueError("The guest KDED declined to unload its watcher")
    wait_for(lambda: owner(bus, WATCHER) is None, 5, "The guest watcher did not release its bus name")
    if call(bus, kded["owner"], "/kded", "org.kde.kded5", "loadModule", arguments) != (True,):
        raise ValueError("The guest KDED declined to reload its watcher")
    after = wait_for(lambda: owner(bus, WATCHER), 5, "Reloaded watcher did not acquire its bus name")
    pattern = (rf"method call [^\n]*sender={re.escape(app['owner'])} -> destination={re.escape(after['owner'])} "
               rf"[^\n]*member=RegisterStatusNotifierItem\n\s+string \"{re.escape(ITEM)}\"")
    def recorded_reload():
        events = trace.read_text()[trace_start:]
        def transition(old, new):
            return re.search(r"signal [^\n]*sender=org\.freedesktop\.DBus [^\n]*member=NameOwnerChanged\n"
                             rf'\s+string "{re.escape(WATCHER)}"\n\s+string "{re.escape(old)}"\n\s+string "{re.escape(new)}"', events)
        released, acquired = transition(before["owner"], ""), transition("", after["owner"])
        registration = re.search(pattern, events)
        return released and acquired and registration and released.start() < acquired.start() < registration.start()
    wait_for(recorded_reload, 12, "Missing ordered watcher release, acquisition and fresh GUI registration")
    names, = call(bus, after["owner"], "/StatusNotifierWatcher", "org.freedesktop.DBus.Properties",
                  "Get", GLib.Variant("(ss)", (WATCHER, "RegisteredStatusNotifierItems")))
    if ITEM + "/StatusNotifierItem" not in names:
        raise ValueError("Reloaded watcher did not retain the registration")
    return dict(before=before, after=after, registered=names)


def exercise(stack, x, bus, primary, shell, app, item, report, reload_watcher):
    path = item["Menu"]
    if path != "/StatusNotifierItem/Menu" or item["ItemIsMenu"]:
        raise ValueError("Unexpected menu path or default icon action")
    log = WORK / "gui.log"
    trace = WORK / "menu-bus.log"
    recorder = checked_start(stack, ["dbus-monitor", "--session",
        f"type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='{WATCHER}'",
        f"type='method_call',path='{path}',interface='{INTERFACE}'",
        "type='method_call',path='/StatusNotifierItem',interface='org.kde.StatusNotifierItem'",
        f"type='signal',path='{path}',interface='{INTERFACE}',member='LayoutUpdated'",
        f"type='method_call',interface='{WATCHER}',member='RegisterStatusNotifierItem'"], trace)
    wait_for(lambda: check_alive(recorder, trace) or "member=NameAcquired" in trace.read_text(), 4, "Menu monitor unavailable")
    first, original = worker(stack, primary, log, 0)
    wait_for(lambda: "INVENTORY_COMPLETE files=1 changed=0 pass=1" in log.read_text(), 10, "First inventory did not finish")
    actions = report["nativeMenu"] = dict(original=first, selections=[], germanRevision=layout(bus, app, path, GERMAN))
    status = ("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties")
    call(bus, *status, "Set", GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", True))))
    wait_for(lambda: call(bus, *status, "Get", GLib.Variant("(ss)", ("org.a11y.Status", "IsEnabled"))) == (True,),
             3, "The private accessibility service did not enable the editor's native controls")
    if reload_watcher:
        actions["watcherReload"] = restart_watcher(bus, app, report, trace)
        if original.poll(0) or owner(bus, ITEM)["owner"] != app["owner"] or subject_window(x, primary.pid):
            raise ValueError("The watcher reload changed the hidden primary or its original worker")
    for command, labels in ((1, GERMAN), (2, ENGLISH), (3, ENGLISH)):
        receipt = select_row(x, shell, labels, command)
        actions["selections"].append(receipt)
        # Only a click emitted by this panel to this item qualifies as a selection.
        pattern = (r"method call [^\n]*sender=(:[\d.]+) -> destination=([^ ]+) [^\n]*member=Event\n"
                   rf"\s+int32 {command}\n\s+string \"clicked\"")
        hit = wait_for(lambda: re.search(pattern, trace.read_text()), 6, "Missing menu click on the private bus")
        sender, destination = hit.groups()
        if owner(bus, sender)["pid"] != shell or destination not in (app["owner"], item["Id"]):
            raise ValueError("The selected action did not come from this panel")
        receipt.update(sender=sender, destination=destination)
        if command == 1:
            window = wait_for(lambda: subject_window(x, primary.pid), 16, "Open did not map this GUI")
            wait_for(lambda: hex(window) in subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"], text=True).split(),
                     5, "The opened GUI did not receive focus")
            capture("opened-editor")
            receipt["focusedWindow"] = hex(window)
            if original.poll(0):
                raise ValueError("Open replaced the original worker")
            def language_button():
                return next((describe(n) for n in desktop_nodes(primary.pid) if n.get_role_name() in ("push button", "button")
                             and n.get_name() == "English" and n.get_component_iface()), None)
            try:
                button = wait_for(language_button, 8, "Expected language button on opened editor")
            except TimeoutError:
                (WORK / "editor-tree.json").write_text(json.dumps([describe(n) for n in desktop_nodes(primary.pid)],
                                                                 ensure_ascii=False, indent=2))
                raise
            left, top, width, height = button["rect"]
            if width < 2 or height < 2:
                raise ValueError("The editor's language button has no physical bounds")
            _, under_pointer = move_pointer(x, left+width//2, top+height//2)
            if not any(xid == window for xid, _ in under_pointer):
                raise ValueError("The language button lies outside the originally opened window")
            actions["languageButton"] = button
            press_button(x, 1)
            signal = rf"signal [^\n]*sender={re.escape(app['owner'])} [^\n]*member=LayoutUpdated"
            wait_for(lambda: re.search(signal, trace.read_text()), 5, "No live menu revision after language change")
            actions["englishRevision"] = layout(bus, app, path, ENGLISH)
            if actions["englishRevision"] <= actions["germanRevision"]:
                raise ValueError("The menu revision did not advance")
            (WORK / "files/second.jpg").touch()
        elif command == 2:
            second, replacement = worker(stack, primary, log, 1)
            actions["replacement"] = second
            if not original.poll(0) or second["pid"] == first["pid"]:
                raise ValueError("The original worker was still running after replacement")
            wait_for(lambda: check_alive(primary, log) or "INVENTORY_COMPLETE files=2 changed=2 pass=0" in log.read_text(),
                     10, "The replacement failed to read the changed corpus")
            if subject_window(x, primary.pid) != window:
                raise ValueError("Restart replaced or closed the original GUI")
        else:
            if primary.wait(10) or not replacement.poll(0):
                raise ValueError("Quit failed to drain the primary and its worker")
            lines = log.read_text().splitlines()
            order = [f"WORKER_EXIT pid={first['pid']} reason=restart success=true",
                     f"INVENTORY_WORKER pid={second['pid']}",
                     f"WORKER_EXIT pid={second['pid']} reason=quit success=true"]
            indices = [lines.index(entry) for entry in order]
            if indices != sorted(indices) or not lines[-1].startswith("DRAINED passes="):
                raise ValueError("The worker lifecycle or GUI exit was incomplete")
            actions["shutdown"] = dict(guiExitCode=primary.returncode, workerEvents=order, drained=lines[-1])
