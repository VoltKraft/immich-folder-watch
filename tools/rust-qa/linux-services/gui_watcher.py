"""Replay watcher changes and a delayed registration reply against the original Rust GUI."""
import argparse
from contextlib import ExitStack
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
APP = "org.example.IfwGuiProbe"
WATCHER = "org.kde.StatusNotifierWatcher"
APP_PATH = "/org/example/IfwGuiProbe"
PANEL = "/StatusNotifierWatcher"


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def run(gui, output):
    driver = HERE.parent / "performance"
    sys.path.insert(0, str(driver))
    from linux import namespace
    gui = gui.resolve(strict=True)
    output = output.resolve()
    output.mkdir(exist_ok=False, parents=True)
    inputs = dict(executable=sha(gui), observers={p.name: sha(p) for p in
                  (Path(__file__), HERE / "watcher.py", driver / "linux.py", driver / "session.py")})
    receipt = json.loads(gui.with_suffix(".inputs.json").read_bytes())
    if receipt["binary_sha256"] != inputs["executable"]:
        raise ValueError("Executable differs from the native compiler receipt")
    source_dir = HERE.parent / "gui/src"
    for filename in ("main.rs", "linux.rs", "linux_tray_menu.rs", "linux_tray_watcher.rs"):
        source = source_dir / filename
        if sha(source) != receipt["sources"].get(source.relative_to(HERE.parents[2]).as_posix()):
            raise ValueError(f"Rebuild the native GUI after changing {source}")
    inputs["compilerReceipt"] = receipt
    (output / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    command = namespace(output, HERE, None)
    pos = command.index("--chdir")
    command[pos:pos] = ["--dir", "/probe", "--ro-bind", str(gui), "/probe/gui",
                        "--setenv", "IFW_QA_ISOLATED", "1", "--setenv", "PYTHONPATH", "/driver"]
    command[command.index("--") + 1:] = ["/usr/bin/python3", "-B", "/app/gui_watcher.py", "--inside"]
    subprocess.run(command, check=True, timeout=55)
    print("Verified the GUI's private watcher handover:", output)


def registrations(lines, gui, owners):
    """Resolve each registration response to the sender and call serial captured by D-Bus."""
    records = {}
    for owner, expected in owners:
        call = re.compile(rf"^method call .*sender={re.escape(gui)} -> destination={re.escape(owner)} "
                          rf"serial=(\d+) path={PANEL}; interface={WATCHER}; member=RegisterStatusNotifierItem$")
        calls = [(n, m[1]) for n, line in enumerate(lines) if (m := call.fullmatch(line))]
        if len(calls) != 1:
            raise ValueError(f"Expected one original GUI registration addressed to {owner}, got {calls}")
        start, serial = calls[0]
        response = re.compile(rf"^{expected} .*sender={re.escape(owner)} -> destination={re.escape(gui)} .*"
                              rf"\breply_serial={serial}(?:\s|$)")
        replies = [n for n in range(start + 1, len(lines)) if response.match(lines[n])]
        if len(replies) != 1:
            raise ValueError(f"Expected one {expected} matching {owner} request {serial}, got {replies}")
        records[owner] = dict(callLine=start + 1, serial=int(serial), replyLine=replies[0] + 1, kind=expected)
    return records


def inside():
    if (os.environ.get("HOME") != "/tmp/home"
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or sha(Path("/probe/gui")) != json.loads(Path("/qa/inputs.json").read_bytes())["executable"]):
        raise ValueError("Expected the declared GUI and private session namespace")
    from gi.repository import Gio, GLib
    from session import checked_start, check_alive, private_session, stop, wait_for

    def call(destination, path, interface, method, args=None):
        return bus.call_sync(destination, path, interface, method, args, None,
                             Gio.DBusCallFlags.NO_AUTO_START, 3000, None).unpack()

    def owner(name):
        return call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                    "GetNameOwner", GLib.Variant("(s)", (name,)))[0]

    def start_watcher(label, mode, ownership="exclusive"):
        log = Path("/qa", label + ".log")
        process = checked_start(stack, [sys.executable, "-B", "/app/watcher.py", mode, APP, ownership], log)
        wait_for(lambda: check_alive(process, log) or "READY :" in log.read_text(), 5, f"Missing {label} watcher")
        unique = next(line.split()[1] for line in log.read_text().splitlines() if line.startswith("READY "))
        if owner(WATCHER) != unique:
            raise ValueError(f"The running {label} peer does not own the watcher name")
        return unique, log

    def panel(peer, method):
        return call(peer, PANEL, "org.example.WatcherControl", method)

    def check_log(log, text):
        wait_for(lambda: check_alive(gui, gui_log) or text in log.read_text(), 5, f"Missing {text} in {log.name}")

    with ExitStack() as stack:
        Path("/tmp/home").mkdir(mode=0o700)
        display, _ = private_session(stack)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        trace = Path("/qa/bus.log")
        monitor = checked_start(stack, ["stdbuf", "-oL", "dbus-monitor", "--session",
                                        f"type='method_call',interface='{WATCHER}'", "type='method_return'", "type='error'",
                                        f"type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged',arg0='{WATCHER}'"], trace)
        def monitor_ready():
            check_alive(monitor, trace)
            call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetId")
            return "method return" in trace.read_text()
        wait_for(monitor_ready, 5, "Private monitor did not see bus traffic")
        early, early_log = start_watcher("bootstrap-delayed", "delay", "replaceable")
        gui_log = Path("/qa/gui.log")
        gui = checked_start(stack, ["/probe/gui", "--background"], gui_log)
        check_log(early_log, f"REGISTER {APP} ")
        primary = owner(APP)
        if "READY " in gui_log.read_text() or display.visible():
            raise ValueError("GUI completed startup with a pending registration")
        first, first_log = start_watcher("first", "accept", "replace")
        check_log(gui_log, "READY BackgroundStartup Available")
        panel(early, "Acknowledge")
        check_log(early_log, "LATE_REPLIES 1")
        check_log(first_log, f"REGISTER {APP} {primary} accept")
        if display.visible():
            raise ValueError("The hidden-start GUI mapped a window")
        panel(first, "Release")
        delayed, delayed_log = start_watcher("delayed", "delay")
        check_log(delayed_log, f"REGISTER {APP} {primary} delay")
        panel(delayed, "Release")
        refused, refused_log = start_watcher("refused", "refuse")
        check_log(refused_log, f"REGISTER {APP} {primary} refuse")
        check_log(gui_log, f"TRAY_REGISTRATION owner={refused} confirmed={refused} available=false")
        panel(delayed, "Acknowledge")
        check_log(delayed_log, "LATE_REPLIES 1")
        if owner(WATCHER) != refused:
            raise ValueError("Late acknowledgement did not arrive during the refusing watcher's ownership")
        panel(refused, "Release")
        last, last_log = start_watcher("last", "accept")
        check_log(last_log, f"REGISTER {APP} {primary} accept")
        check_log(gui_log, f"TRAY_REGISTRATION owner={last} confirmed={last} available=true")
        if owner(APP) != primary or owner(WATCHER) != last or display.visible():
            raise ValueError("The watcher transition changed the primary or showed its background window")
        call(primary, APP_PATH, "org.freedesktop.Application", "ActivateAction", GLib.Variant("(sava{sv})", ("quit", [], {})))
        if gui.wait(timeout=8) != 0 or "DRAINED passes=0" not in gui_log.read_text():
            raise ValueError("The hidden primary did not drain and exit")
        stop(monitor)
        owners = [(early, "method return"), (first, "method return"), (delayed, "method return"), (refused, "error"), (last, "method return")]
        captured = registrations(trace.read_text().splitlines(), primary, owners)
        if captured[early]["replyLine"] <= captured[first]["replyLine"]:
            raise ValueError("The initial owner's stale reply preceded its replacement's successful acknowledgement")
        if not (captured[refused]["replyLine"] < captured[delayed]["replyLine"] < captured[last]["callLine"]):
            raise ValueError("The reply to the old call did not arrive between refusal and final registration")
        positive = re.findall(r"^TRAY_REGISTRATION owner=(:[\d.]+) confirmed=\1 available=true$", gui_log.read_text(), re.M)
        if positive != [first, last] or len(set(peer for peer, _ in owners)) != 5:
            raise ValueError(f"Unexpected GUI registration acknowledgements: {positive}")
        result = dict(gui=primary, guiPid=gui.pid, initialPending=early, initial=first, delayed=delayed, refused=refused,
                      replacement=last, nativeAcknowledgements=positive, busRegistrations=captured,
                      executable=sha(Path("/probe/gui")), guiLog=sha(gui_log), trace=sha(trace))
        Path("/qa/result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--gui", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args()
        run(args.gui, args.output)
