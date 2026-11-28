"""Observe KWin, the Plasma panel and the GUI only inside the private namespace."""

from contextlib import ExitStack
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import gi
gi.require_version("Atspi", "2.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Atspi, Gdk, Gio, GLib

sys.path.insert(0, "/app/performance")
from session import checked_start, check_alive, wait_for
from x11 import Display, WindowAttributes, bind
from audit import native_architecture, sha, verify_elf
from brand import SIZES, render

WORK = Path("/qa")
ITEM = "org.example.IfwGuiProbe"
WATCHER = "org.kde.StatusNotifierWatcher"
DBUS = "org.freedesktop.DBus"


def call(bus, dest, path, interface, method, arguments=None):
    return bus.call_sync(dest, path, interface, method, arguments, None,
                         Gio.DBusCallFlags.NO_AUTO_START, 4500, None).unpack()


def owner(bus, name):
    try:
        unique, = call(bus, DBUS, "/org/freedesktop/DBus", DBUS, "GetNameOwner", GLib.Variant("(s)", (name,)))
    except GLib.Error:
        return None
    pid, = call(bus, DBUS, "/org/freedesktop/DBus", DBUS, "GetConnectionUnixProcessID", GLib.Variant("(s)", (unique,)))
    return {"owner": unique, "pid": pid, "executable": os.readlink(f"/proc/{pid}/exe")}


def session(stack):
    # Package service files are visible only inside this guest and both buses use private Unix sockets.
    for kind, services in (("system", ""), ("session", "<servicedir>/usr/share/dbus-1/services</servicedir>")):
        config = Path(f"/tmp/{kind}.conf")
        config.write_text(f"""<busconfig><type>{kind}</type><listen>unix:path=/tmp/{kind}-bus</listen>
            <auth>EXTERNAL</auth>{services}<policy context="default"><allow send_destination="*"/>
            <allow receive_sender="*"/><allow own="*"/><allow eavesdrop="true"/></policy></busconfig>""")
        log = WORK / f"{kind}-bus.log"
        proc = checked_start(stack, ["dbus-daemon", "--nofork", "--nopidfile", "--config-file", str(config)], log)
        wait_for(lambda: check_alive(proc, log) or Path(f"/tmp/{kind}-bus").is_socket(), 8, "Private bus missing")
    log = WORK / "xvfb.log"
    server = checked_start(stack, ["Xvfb", ":93", "-screen", "0", "1280x900x24", "-nolisten", "tcp", "-noreset"], log)
    wait_for(lambda: check_alive(server, log) or Path("/tmp/.X11-unix/X93").is_socket(), 10, "Private X server missing")
    return Gio.bus_get_sync(Gio.BusType.SESSION)


def desktop_nodes(pid):
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)
    desktop = Atspi.get_desktop(0)
    apps = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
    queue = [app for app in apps if app and app.get_process_id() == pid]
    nodes = []
    while queue and len(nodes) < 500:
        node = queue.pop(0)
        if not node:
            continue
        node.clear_cache()
        nodes.append(node)
        queue += [node.get_child_at_index(i) for i in range(min(node.get_child_count(), 64))]
    return nodes


def describe(node):
    result = {"name": node.get_name(), "role": node.get_role_name()}
    if node.get_component_iface():
        r = node.get_extents(Atspi.CoordType.SCREEN)
        result["rect"] = [r.x, r.y, r.width, r.height]
    return result


def properties(window):
    return subprocess.check_output(["xprop", "-id", str(window), "_NET_WM_PID", "_NET_WM_NAME",
                                    "_NET_WM_WINDOW_TYPE"], text=True)


def subject_window(x, pid):
    listing = subprocess.check_output(["xprop", "-root", "_NET_CLIENT_LIST"], text=True)
    for xid in re.findall(r"0x[0-9a-fA-F]+", listing):
        window = int(xid, 16)
        props = properties(window)
        attrs = WindowAttributes()
        if (re.search(rf"_NET_WM_PID\(CARDINAL\) = {pid}$", props, re.MULTILINE)
                and '_NET_WM_NAME(UTF8_STRING) = "Desktop input probe"' in props
                and x.attributes(x.display, window, c.byref(attrs)) and attrs.map_state == 2):
            return window
    return None


def capture(name, rect=None):
    window = Gdk.get_default_root_window()
    region = rect or [0, 0, window.get_width(), window.get_height()]
    pixels = Gdk.pixbuf_get_from_window(window, *region)
    if not pixels or not pixels.savev(str(WORK / (name + ".png")), "png", [], []):
        raise RuntimeError("Private X11 capture failed")
    if rect:
        stride, channels, data = pixels.get_rowstride(), pixels.get_n_channels(), pixels.get_pixels()
        colors = [data[y*stride+x*channels:y*stride+x*channels+3] for y in range(rect[3]) for x in range(rect[2])]
        return {"rgbColors": len(set(colors)), "goldPixels": sum(r > 175 and g > 90 and b+55 < min(r, g) for r, g, b in colors),
                "pngSha256": hashlib.sha256((WORK / (name + ".png")).read_bytes()).hexdigest()}


def move_pointer(x, px, py):
    xtest, xlib = c.CDLL("libXtst.so.6"), c.CDLL("libX11.so.6")
    motion = bind(xtest, "XTestFakeMotionEvent", c.c_int, c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong)
    window, integer = c.c_ulong, c.c_int
    query = bind(xlib, "XQueryPointer", integer, c.c_void_p, window, c.POINTER(window), c.POINTER(window),
                 *([c.POINTER(integer)] * 4), c.POINTER(c.c_uint))
    if not motion(x.display, 0, px, py, 0):
        raise RuntimeError("Synthetic pointer motion failed")
    x.sync(x.display, 0)
    target, path = x.root, []
    for _ in range(16):
        root, child, rx, ry, wx, wy, mask = window(), window(), integer(), integer(), integer(), integer(), c.c_uint()
        if (not query(x.display, target, *(c.byref(v) for v in (root, child, rx, ry, wx, wy, mask)))
                or (rx.value, ry.value) != (px, py) or mask.value & 0x1f00):
            raise RuntimeError("Pointer did not reach the released, private panel location")
        if not child.value:
            break
        target = child.value
        path.append((target, properties(target)))
    return target, path


def press_button(x, button_number):
    xtest = c.CDLL("libXtst.so.6")
    press = bind(xtest, "XTestFakeButtonEvent", c.c_int, c.c_void_p, c.c_uint, c.c_int, c.c_ulong)
    if not press(x.display, button_number, 1, 0) or not press(x.display, button_number, 0, 0):
        raise RuntimeError("Native tray click failed")
    x.sync(x.display, 0)


def click_item(x, shell_pid, number, button_number=1):
    def button(name="Desktop input probe"):
        found = [describe(n) for n in desktop_nodes(shell_pid) if n.get_name() == name
                 and n.get_role() == Atspi.Role.PUSH_BUTTON and n.get_state_set().contains(Atspi.StateType.SHOWING)]
        bounded = [n for n in found if 0 <= n["rect"][0] < 1280 and 0 <= n["rect"][1] < 900
                   and 8 <= n["rect"][2] <= 180 and 8 <= n["rect"][3] <= 128]
        return bounded[0] if len(bounded) == 1 else None
    def stable_target():
        item = button()
        neighbour = button("Expand System Tray")
        if not item or not neighbour:
            return None
        left, top, width, height = item["rect"]
        px, py = left + width // 2, top + height // 2
        target, path = move_pointer(x, px, py)
        docks = [w for w, p in path if re.search(rf"_NET_WM_PID\(CARDINAL\) = {shell_pid}$", p, re.MULTILINE)
                 and "_NET_WM_WINDOW_TYPE_DOCK" in p]
        if docks != [target] or button() != item:
            return None
        icon = capture(f"tray-item-{number}", item["rect"])
        control_pixels = capture(f"tray-control-{number}", neighbour["rect"])
        if control_pixels["rgbColors"] < 2:
            return None
        if button_number == 3 and (icon["goldPixels"] < 12 or icon["rgbColors"] < 8):
            return None
        if button() != item or move_pointer(x, px, py)[0] != target:
            return None
        return {**item, "point": [px, py], "panelXid": hex(target), "pixels": icon, "neighbour": control_pixels}

    # The panel can still be arranging its items after a watcher reload.
    item = wait_for(stable_target, 10, "No stable drawn subject icon on the original Plasma panel")
    press_button(x, button_number)
    return item


def run(stack, report, blank, menu):
    bus = session(stack)
    arch = native_architecture()
    if report["target"] != os.uname().machine + "-unknown-linux-gnu":
        raise ValueError("The GUI target and the native observer kernel differ")
    def start(label, cmd):
        return checked_start(stack, cmd, WORK / f"{label}.log")
    def wait_owner(name):
        result = wait_for(lambda: owner(bus, name), 24, f"No owned {name}")
        result["elfMachine"] = verify_elf(Path(f"/proc/{result['pid']}/exe"), arch)
        report.setdefault("services", {})[name] = result
        return result
    start("atspi", ["/usr/libexec/at-spi-bus-launcher", "--launch-immediately"])
    wait_owner("org.a11y.Bus")
    kwin = start("kwin", ["/usr/bin/kwin_x11", "--replace"])
    if wait_owner("org.kde.KWin")["pid"] != kwin.pid:
        raise ValueError("KWin's bus owner does not match the started window manager")
    start("kded", ["/usr/bin/kded5"])
    kded = wait_owner("org.kde.kded5")
    call(bus, "org.kde.kded5", "/kded", "org.kde.kded5", "loadModule", GLib.Variant("(s)", ("statusnotifierwatcher",)))
    watcher = wait_owner(WATCHER)
    if watcher["pid"] != kded["pid"]:
        raise ValueError("Watcher does not run in KDED")
    shell = start("plasma", ["/usr/bin/plasmashell"])
    shell_bus = wait_owner("org.kde.plasmashell")
    if shell_bus["pid"] != shell.pid:
        raise ValueError("Unexpected Plasma shell process")
    def script(code):
        return call(bus, "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript", GLib.Variant("(s)", (code,)))[0]
    report["panel"] = script("""var p=panels()[0]; if (!p) { p=new Panel; p.location='bottom'; p.height=48; }
        if (p.widgetIds.filter(function(id){return p.widgetById(id).type=='org.kde.plasma.systemtray';}).length===0) {
            p.addWidget('org.kde.plasma.systemtray'); }
        print(p.id + ' ' + p.widgetIds.map(function(id){return p.widgetById(id).type;}).join(' '));""")
    def items():
        return call(bus, watcher["owner"], "/StatusNotifierWatcher", "org.freedesktop.DBus.Properties", "Get",
                    GLib.Variant("(ss)", (WATCHER, "RegisteredStatusNotifierItems")))[0]
    report["itemsBefore"] = items()
    command = ["/app/native-gui-assessment", "--background"]
    if menu:
        from session import fresh_profile
        media = WORK / "files"
        media.mkdir()
        (media / "first.jpg").touch()
        profile = fresh_profile(WORK / "profile", media)
        command = ["/usr/bin/env", "XDG_CONFIG_HOME=" + profile["XDG_CONFIG_HOME"], "IFW_QA_BENCHMARK=1", *command]
    subject = start("gui", command)
    app = wait_owner(ITEM)
    if app["pid"] != subject.pid:
        raise ValueError("Unexpected GUI service owner")
    item, = call(bus, app["owner"], "/StatusNotifierItem", "org.freedesktop.DBus.Properties", "GetAll",
                 GLib.Variant("(s)", ("org.kde.StatusNotifierItem",)))
    if item.get("Id") != ITEM or item.get("Title") != "Desktop input probe" or item.get("Status") != "Active":
        raise ValueError("Unexpected exported item identity or state")
    frames = item.get("IconPixmap", [])
    report["iconFrames"] = [(w,h,hashlib.sha256(bytes(data)).hexdigest()) for w,h,data in frames]
    if blank:
        if frames or item.get("IconName"):
            raise ValueError("The frozen blank control unexpectedly exported an icon")
    elif ([(w,h,len(data)) for w,h,data in frames] != [(s,s,s*s*4) for s in SIZES] or
          b"".join(bytes(data) for _,_,data in frames) != Path("/app/tray-icon.argb").read_bytes()):
        raise ValueError("The native SNI property differs from the approved network-order ARGB frames")
    else:
        prop = bus.call_sync(app["owner"], "/StatusNotifierItem", "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", ("org.kde.StatusNotifierItem", "IconPixmap")), None, Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
        report["iconSignature"] = prop.get_child_value(0).get_variant().get_type_string()
        if report["iconSignature"] != "a(iiay)":
            raise ValueError("Unexpected D-Bus IconPixmap signature")
    canonical = ITEM + "/StatusNotifierItem"
    report["items"] = wait_for(lambda: value if canonical in (value := items()) else None, 8,
                               "The KDE watcher never registered the application's real item")
    x = Display()
    stack.callback(x.close, x.display)
    if not Gdk.Display.get_default():
        Gdk.DisplayManager.get().set_default_display(Gdk.Display.open(":93"))
    monitor = start("activation", ["dbus-monitor", "--session",
        "type='method_call',path='/StatusNotifierItem',interface='org.kde.StatusNotifierItem',member='Activate'"])
    trace = WORK / "activation.log"
    wait_for(lambda: check_alive(monitor, trace) or "member=NameAcquired" in trace.read_text(), 4, "Monitor was not ready")
    gui_log = WORK / "gui.log"
    wait_for(lambda: check_alive(subject, gui_log) or "READY BackgroundStartup Available" in gui_log.read_text(),
             10, "GUI did not acknowledge hidden startup")
    def hidden():
        if subject_window(x, subject.pid):
            raise RuntimeError("The subject unexpectedly mapped a window")
    for _ in range(5):
        hidden()
        time.sleep(.12)
    capture("panel-hidden")
    if menu:
        from menu import exercise
        exercise(stack, x, bus, subject, shell.pid, app, item, report, menu["restartWatcher"])
        wait_for(lambda: canonical not in items(), 5, "The menu Quit left the item registered")
        report["itemsAfterQuit"] = items()
        return
    report["activations"] = []
    for number in (1, 2):
        interaction = click_item(x, shell.pid, number)
        report["activations"].append(interaction)
        icon = interaction["pixels"]
        if (blank and (icon["rgbColors"] != 1 or icon["goldPixels"] != 0)
                or not blank and (icon["rgbColors"] < 8 or icon["goldPixels"] < 12)):
            raise ValueError(f"The received SNI and actually painted project artwork disagree: {icon}")
        def seen():
            hits = re.findall(r"method call [^\n]*sender=(:[\d.]+) -> destination=([^ ]+) [^\n]*member=Activate\n"
                              r"\s+int32 (\d+)\n\s+int32 (\d+)", trace.read_text())
            return hits[number-1] if len(hits) == number else None
        sender, destination, px, py = wait_for(seen, 6, "Missing Plasma-to-item activation")
        if (owner(bus, sender)["pid"] != shell.pid or destination not in (app["owner"], ITEM)
                or [int(px), int(py)] != interaction["point"]):
            raise ValueError("The observed SNI call did not travel from Plasma to this GUI")
        window = wait_for(lambda: subject_window(x, subject.pid), 16, "KWin did not map the Rust GUI window")
        interaction.update(sender=sender, destination=destination, guiXid=hex(window))
        wait_for(lambda: "ADAPTER Vulkan Cpu llvmpipe" in gui_log.read_text(), 8, "The GUI did not confirm its software renderer")
        time.sleep(.25)
        capture(f"visible-{number}")
        x.request_close(window)
        wait_for(lambda: not subject_window(x, subject.pid) and gui_log.read_text().count("WINDOW_HIDDEN") == number,
                 10, "The native close request did not hide the GUI")
        hidden()
    # Check the actual Qt platform and watcher serving these two clicks.
    lib = Path("/usr/lib") / (os.uname().machine + "-linux-gnu")
    report["loadedLibraries"] = {}
    for pid, relatives in ((shell.pid, ("libQt5Core.so.5", "libQt5Quick.so.5", "qt5/plugins/platforms/libqxcb.so")),
                           (kded["pid"], ("qt5/plugins/kf5/kded/statusnotifierwatcher.so",))):
        mappings = {line.split(maxsplit=5)[5] for line in Path(f"/proc/{pid}/maps").read_text().splitlines()
                    if len(line.split(maxsplit=5)) == 6}
        for relative in relatives:
            path = (lib / relative).resolve(strict=True)
            if str(path) not in mappings:
                raise ValueError(f"Missing native Plasma library in the observed process: {path.name}")
            report["loadedLibraries"][relative] = dict(pid=pid, file=str(path), elfMachine=verify_elf(path, arch), sha256=sha(path))
    call(bus, app["owner"], "/org/example/IfwGuiProbe", "org.freedesktop.Application", "ActivateAction",
         GLib.Variant("(sava{sv})", ("quit", [], {})))
    if subject.wait(timeout=8) or "DRAINED" not in gui_log.read_text():
        raise RuntimeError("Rust GUI did not drain on Quit")
    wait_for(lambda: canonical not in items(), 5, "KDE retained the exited item's registration")
    report["itemsAfterQuit"] = items()


def main():
    inputs = json.loads((WORK / "inputs.json").read_text())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DISPLAY") != ":93"
            or any(os.readlink(f"/proc/self/ns/{k}") == v for k, v in inputs["namespaces"].items())):
        raise RuntimeError("Use the private Plasma launcher")
    if render(Path("/app/logo.svg")) != Path("/app/tray-icon.argb").read_bytes():
        raise ValueError("The checked Ubuntu SVG renderer did not reproduce the embedded artwork")
    os.umask(0o077)
    for path in (Path.home(), Path("/tmp/runtime")):
        path.mkdir(mode=0o700)
    Path("/tmp/.X11-unix").mkdir(mode=0o700)
    report = {"passed": False, "target": inputs["target"], "guiSha256": inputs["binary"], "blankControl": inputs["blankControl"]}
    try:
        with ExitStack() as stack:
            run(stack, report, inputs["blankControl"], inputs.get("menu"))
            report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (WORK / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
