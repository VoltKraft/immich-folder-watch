"""Observe an ordinary editor across on/off AT-SPI status changes on a private X11 desktop."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
WORK = Path("/qa")
NAMESPACES = ("user", "net", "pid", "mnt", "ipc")


def inside():
    sys.path[:0] = ["/driver", "/gui"]
    from desktop_input import Gio, GLib, start_accessibility
    from native import action
    from session import check_alive, checked_start, private_session, wait_for
    if (Path.home() != Path("/tmp/home") or Path("/.flatpak-info").exists()
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or any(os.readlink("/proc/self/ns/" + k) == v for k, v in json.loads((WORK / "namespaces.json").read_bytes()).items())):
        raise ValueError("Use the private desktop observer outside Flatpak")
    Path.home().mkdir(mode=0o700)
    Path("/tmp/runtime").mkdir(mode=0o700)
    with ExitStack() as stack:
        display, server = private_session(stack)
        enabled = start_accessibility(stack)
        session = Gio.bus_get_sync(Gio.BusType.SESSION)
        def call(bus, name, path, interface, method, arguments=None):
            return bus.call_sync(name, path, interface, method, arguments, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
        def set_status(value):
            call(session, "org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
                 GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", value))))
            wait_for(lambda: enabled() == value, 4, "Private session did not report requested status")
        address, = call(session, "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress")
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        peer = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
        stack.callback(peer.close_sync, None)
        set_status(False)
        log = WORK / "gui.log"
        app = checked_start(stack, ["/app/native-gui-assessment"], log)
        wait_for(lambda: check_alive(app, log) or display.visible(), 15, "Original editor did not open")
        def own_roots():
            roots, = call(peer, "org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root",
                          "org.a11y.atspi.Accessible", "GetChildren")
            own = []
            for name, path in roots:
                try:
                    pid, = call(peer, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)))
                except GLib.Error:
                    continue
                if pid == app.pid:
                    own.append([name, path])
            return own
        report = {"server": server, "guiPid": app.pid, "window": display.visible(), "stages": []}
        for value in (False, True, False, True):
            set_status(value)
            def sample():
                check_alive(app, log)
                roots = own_roots()
                return {"enabled": enabled(), "roots": roots} if len(roots) == int(value) else None
            stage = wait_for(sample, 8, "The original editor's accessibility root did not follow the private status change")
            if stage["enabled"] != value or display.visible() != report["window"]:
                raise ValueError("The private status or original editor window changed unexpectedly")
            report["stages"].append(stage)
            (WORK / "status.json").write_text(json.dumps(report, indent=2) + "\n")
        action("quit")
        report["exit"] = app.wait(timeout=10)
        if report["exit"] or own_roots():
            raise ValueError("The editor or its accessibility registration survived Quit")
        (WORK / "status.json").write_text(json.dumps(report, indent=2) + "\n")


def launch(binary):
    from build import SCOPE, sha256
    sys.path.insert(0, str(HERE.parents[1] / "performance"))
    from linux import namespace
    binary = binary.resolve(strict=True)
    if not binary.is_relative_to(SCOPE):
        raise ValueError("Use an isolated candidate below artifacts/rust/flatpak-accessibility")
    out = Path(tempfile.mkdtemp(prefix="desktop-status-", dir=SCOPE))
    print(out, flush=True)
    (out / "namespaces.json").write_text(json.dumps({n: os.readlink("/proc/self/ns/" + n) for n in NAMESPACES}))
    (out / "inputs.json").write_text(json.dumps({"binary": sha256(binary), "observer": sha256(Path(__file__))}, indent=2) + "\n")
    cmd = namespace(out, binary.parent, None)
    index = cmd.index("/app")
    cmd[index - 2:index + 1] = ["--dir", "/app", "--ro-bind", str(binary), "/app/native-gui-assessment"]
    cmd[cmd.index("--chdir"):] = ["--ro-bind", str(HERE.parent), "/gui", "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime",
        "--setenv", "IFW_QA_ISOLATED", "1", "--setenv", "GSETTINGS_BACKEND", "memory", "--chdir", "/qa",
        "--", "/usr/bin/python3", "-B", "/gui/flatpak-accessibility/desktop_status.py", "--inside"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    elif len(sys.argv) == 2:
        launch(Path(sys.argv[1]))
    else:
        raise SystemExit("Expected the private native candidate executable")
