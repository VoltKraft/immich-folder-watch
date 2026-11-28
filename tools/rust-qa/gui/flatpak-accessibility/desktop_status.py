"""Observe an ordinary editor across on/off AT-SPI status changes on a private X11 desktop."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
WORK = Path("/qa")
NAMESPACES = ("user", "net", "pid", "mnt", "ipc")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
        window = wait_for(lambda: check_alive(app, log) or display.visible(), 15, "Original editor did not open")
        pid_property = subprocess.check_output(["xprop", "-id", str(window), "_NET_WM_PID"], text=True, timeout=3)
        if pid_property.strip() != f"_NET_WM_PID(CARDINAL) = {app.pid}":
            raise ValueError("The original window does not belong to the editor process")
        elf = digest(Path(f"/proc/{app.pid}/exe"))
        if elf != json.loads((WORK / "inputs.json").read_bytes())["binary"]:
            raise ValueError("The running editor differs from the verified executable")
        def registered_roots():
            roots, = call(peer, "org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root",
                          "org.a11y.atspi.Accessible", "GetChildren")
            return [tuple(root) for root in roots]
        def own_roots(roots):
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
        observed = set()
        report = {"server": server, "guiPid": app.pid, "window": window, "runningElfSha256": elf, "stages": []}
        for value in (False, True, False, True):
            set_status(value)
            def sample():
                check_alive(app, log)
                registry = registered_roots()
                roots = own_roots(registry)
                if len(roots) != int(value) or (not value and observed.intersection(registry)):
                    return None
                return {"enabled": enabled(), "roots": roots}
            stage = wait_for(sample, 8, "The original editor's accessibility root did not follow the private status change")
            if stage["enabled"] != value or display.visible() != report["window"]:
                raise ValueError("The private status or original editor window changed unexpectedly")
            report["stages"].append(stage)
            observed.update(tuple(root) for root in stage["roots"])
            (WORK / "status.json").write_text(json.dumps(report, indent=2) + "\n")
        action("quit")
        report["exit"] = app.wait(timeout=10)
        if report["exit"]:
            raise ValueError("The editor failed to exit cleanly after Quit")
        wait_for(lambda: not observed.intersection(registered_roots()) and display.visible() is None,
                 8, "The original window or its accessibility registration survived Quit")
        report["afterQuit"] = {"observedRootsStillRegistered": [], "window": None}
        (WORK / "status.json").write_text(json.dumps(report, indent=2) + "\n")


def launch(binary):
    qa = HERE.parents[1]
    root = qa.parents[1]
    area = root / "artifacts/rust"
    scope = area / "flatpak-accessibility"
    sys.path[:0] = [str(HERE.parent / "flatpak"), str(qa), str(qa / "performance")]
    from linux import namespace
    binary = binary.resolve(strict=True)
    inputs = {"binary": digest(binary), "observer": digest(Path(__file__))}
    build = area / "gui-build"
    if binary == build / "release/native-gui-assessment":
        from gui.compiler_inputs import linux_project_sources
        from ordinary_reader import corrected_build
        receipt = binary.with_suffix(".inputs.json").read_bytes()
        native = json.loads(receipt)
        sources = {p.relative_to(root).as_posix(): digest(p) for p in linux_project_sources(root)}
        if (native["binary_sha256"] != inputs["binary"] or native["sources"] != sources
                or native["target"] != f"{os.uname().machine}-unknown-linux-gnu"):
            raise ValueError("The ordinary native ELF or its first-party sources differ from the compiler receipt")
        inputs.update(compiler=corrected_build(build, native, root), compilerReceiptSha256=hashlib.sha256(receipt).hexdigest())
    elif binary.is_relative_to(scope):
        receipt = None
    else:
        raise ValueError("Use the ordinary gui-build release executable or the isolated private candidate")
    scope.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="desktop-status-", dir=scope))
    print(out, flush=True)
    (out / "namespaces.json").write_text(json.dumps({n: os.readlink("/proc/self/ns/" + n) for n in NAMESPACES}))
    if receipt is not None:
        (out / "compiler.json").write_bytes(receipt)
    (out / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
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
        raise SystemExit("Expected the native editor executable")
