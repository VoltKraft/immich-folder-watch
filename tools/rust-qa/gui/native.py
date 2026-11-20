"""Build-independent native lifecycle observations on an isolated Linux desktop."""

import argparse
from contextlib import ExitStack
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
BUS_NAME = "org.example.IfwGuiProbe"
APP_PATH = "/org/example/IfwGuiProbe"
clock = time.monotonic


def call(service, path, method, *args):
    return subprocess.run(["gdbus", "call", "--session", "--timeout", "4", "--dest", service,
                           "--object-path", path, "--method", method, *args],
                          capture_output=True, check=True, text=True, timeout=6).stdout.strip()


def action(name):
    return call(BUS_NAME, APP_PATH, "org.freedesktop.Application.ActivateAction", name, "[]", "{}")


class X11Observer:
    class MapEvent(c.Structure):
        _fields_ = [("type", c.c_int), ("serial", c.c_ulong), ("sent", c.c_int),
                    ("display", c.c_void_p), ("event", c.c_ulong), ("window", c.c_ulong)]

    def __init__(self, display):
        from x11 import XEvent, bind
        self.display = display
        self.events = []
        self.event = XEvent()
        select = bind(c.CDLL("libX11.so.6"), "XSelectInput", c.c_int, c.c_void_p, c.c_ulong, c.c_long)
        select(display.display, display.root, 1 << 19)  # SubstructureNotifyMask
        self.poll()

    def poll(self):
        display = self.display
        display.sync(display.display, 0)
        while display.pending(display.display):
            display.next_event(display.display, c.byref(self.event))
            if self.event.type in (18, 19):
                entry = c.cast(c.byref(self.event), c.POINTER(self.MapEvent)).contents
                self.events.append({"time": clock(), "event": "map" if entry.type == 19 else "unmap",
                                    "window": entry.window})
        if display.error:
            raise RuntimeError(f"Private X11 protocol error {display.error}")
        return display.visible()

    def close(self):
        window = self.poll()
        if not window:
            raise RuntimeError("No private top-level window to close")
        self.display.request_close(window)
        return "WM_DELETE_WINDOW"

    def focus_for_input(self):
        from x11 import bind
        focus = bind(c.CDLL("libX11.so.6"), "XSetInputFocus", c.c_int,
                     c.c_void_p, c.c_ulong, c.c_int, c.c_ulong)
        focus(self.display.display, self.poll(), 2, 0)
        self.display.sync(self.display.display, 0)

    def key(self, keysym, down):
        from x11 import bind
        code = bind(c.CDLL("libX11.so.6"), "XKeysymToKeycode", c.c_uint8, c.c_void_p, c.c_ulong)
        fake = bind(c.CDLL("libXtst.so.6"), "XTestFakeKeyEvent", c.c_int, c.c_void_p, c.c_uint, c.c_int, c.c_ulong)
        keycode = code(self.display.display, keysym)
        if not keycode or not fake(self.display.display, keycode, int(down), 0):
            raise RuntimeError("X server rejected the synthetic keyboard input")
        self.display.sync(self.display.display, 0)

    def clipboard_owner(self):
        from x11 import bind
        library = c.CDLL("libX11.so.6")
        atom = bind(library, "XInternAtom", c.c_ulong, c.c_void_p, c.c_char_p, c.c_int)
        owner = bind(library, "XGetSelectionOwner", c.c_ulong, c.c_void_p, c.c_ulong)
        return owner(self.display.display, atom(self.display.display, b"CLIPBOARD", 0))


def run_case(stack, observer, name, background, tray, controls):
    from session import checked_start, check_alive, wait_for
    start = clock()
    observer.poll()
    before = len(observer.events)
    log = Path("/qa") / f"{name}.log"
    process = checked_start(stack, ["/app/native-gui-assessment", *(["--background"] if background else [])], log)
    steps = []

    def mark(label):
        steps.append({"time": clock(), "action": label})

    def alive():
        check_alive(process, log)
        return observer.poll()

    def quiet(seconds):
        end = clock() + seconds
        while clock() < end:
            if alive():
                raise RuntimeError(f"Unexpected visible window during {name}")
            time.sleep(.005)
        observer.poll()

    def show():
        return wait_for(alive, 10, f"No native window in {name}. See {log}")

    expected_intent = "BackgroundStartup" if background and tray else "Visible"
    expected_tray = "Available" if tray else "Unavailable"
    wait_for(lambda: (alive(), f"READY {expected_intent} {expected_tray}" in log.read_text())[1],
             8, f"Supervisor never reached {expected_intent} with tray {expected_tray}. See {log}")
    if tray and "REGISTERED org.example.IfwGuiProbe" not in Path("/qa/watcher.log").read_text():
        raise RuntimeError("Private watcher did not acknowledge this item")
    if expected_intent == "BackgroundStartup":
        quiet(1.0)
        if any(event["event"] == "map" for event in observer.events[before:]):
            raise RuntimeError("A window briefly mapped before activation")
    else:
        show()
    mark("observed startup")
    if controls:
        if expected_intent == "BackgroundStartup":
            mark("SNI Activate")
            call(BUS_NAME, "/StatusNotifierItem", "org.kde.StatusNotifierItem.Activate", "0", "0")
            show()
        previous_window = alive()
        is_x11 = isinstance(observer, X11Observer)

        def observed_transition(start, kind):
            return any(event['event'] == kind and (not is_x11 or event['window'] == previous_window)
                       for event in observer.events[start:])

        before_close = len(observer.events)
        mark(observer.close())
        expected = "WINDOW_HIDDEN" if is_x11 else "WINDOW_RELEASED"
        wait_for(lambda: not alive() and expected in log.read_text() and observed_transition(before_close, 'unmap'),
                 10, f"The closed native window did not reach {expected}. See {log}")
        after_close = len(observer.events)
        quiet(.25)
        if any(e["event"] == "map" for e in observer.events[after_close:]):
            raise RuntimeError("A hidden window briefly remapped after close")
        before_open = len(observer.events)
        mark("desktop Activate")
        call(BUS_NAME, APP_PATH, "org.freedesktop.Application.Activate", "{}")
        wait_for(lambda: alive() and observed_transition(before_open, 'map'), 10,
                 f"The desktop activation did not remap the application window. See {log}")
    mark("desktop Quit")
    action("quit")
    process.wait(timeout=10)
    observer.poll()
    messages = log.read_text().splitlines()
    if process.returncode != 0 or not any(line.startswith("DRAINED passes=") for line in messages):
        raise RuntimeError(f"Shutdown failed in {name}: {messages[-3:]}")
    if not controls and expected_intent == "BackgroundStartup":
        if "DRAINED passes=0" not in messages or any(e["event"] == "map" for e in observer.events[before:]):
            raise RuntimeError("The never-shown process created a window or rendered a frame")
    return {"case": name, "steps": [{**s, "time": round(s["time"] - start, 6)} for s in steps],
            "window_events": [{**e, "time": round(e["time"] - start, 6)} for e in observer.events[before:]],
            "application": messages, "exit": process.returncode}


def inside(backend, input_checks, ime, present_mode, capture):
    sys.path.insert(0, "/driver")
    from session import checked_start, check_alive, private_session, wait_for
    if (Path.home() != Path("/tmp/home") or os.environ["DISPLAY"] != ":93"
            or os.environ["DBUS_SESSION_BUS_ADDRESS"] != "unix:path=/tmp/session-bus"):
        raise RuntimeError("Use the isolated native GUI launcher")
    outer = json.loads(Path("/qa/namespace.json").read_text())
    if not all(os.readlink(f"/proc/self/ns/{k}") != v for k, v in outer.items()):
        raise RuntimeError("Private namespaces required")
    os.umask(0o077)
    Path.home().mkdir()
    Path("/tmp/runtime").mkdir()
    with ExitStack() as stack:
        display, server = private_session(stack)
        if backend == "wayland":
            from wayland import WaylandObserver
            observer = WaylandObserver(stack, capture)
            server = "Mutter headless virtual monitor"
        else:
            observer = X11Observer(display)
        with Path("/app/native-gui-assessment").open("rb") as app_file:
            digest = hashlib.file_digest(app_file, "sha256").hexdigest()
        evidence = {"backend": backend, "display_server": server, "arch": platform.machine(),
                    "binary_sha256": digest, "mesa_present_mode_override": present_mode,
                    "virtual_monitor_capture": capture, "runs": []}
        for label in ("build", "driver"):
            metadata = Path("/qa") / f"{label}.json"
            if metadata.is_file():
                evidence[label] = json.loads(metadata.read_text())
        if "build" in evidence and digest != evidence["build"]["binary_sha256"]:
            raise RuntimeError("Executable differs from the bound source record")

        def record(name, background, tray, controls):
            with ExitStack() as child:
                result = run_case(child, observer, name, background, tray, controls)
            evidence["runs"].append(result)
            Path("/qa/results.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(f"{name} passed", flush=True)

        record("absent-tray", True, False, True)
        watcher_log = Path("/qa/watcher.log")
        watcher = checked_start(stack, [sys.executable, "/gui/watcher.py"], watcher_log)
        wait_for(lambda: check_alive(watcher, watcher_log) or "WATCHER_READY" in watcher_log.read_text(),
                 5, "Private watcher did not obtain its bus name")
        record("background-quit", True, True, False)
        record("background-activate", True, True, True)
        record("foreground", False, True, True)
        if input_checks:
            from desktop_input import check_input
            evidence["input"] = check_input(stack, observer, backend, ime)
            Path("/qa/results.json").write_text(json.dumps(evidence, indent=2) + "\n")


def launch(args):
    root = HERE.parents[2]
    sys.path.insert(0, str(root / "tools/rust-qa/performance"))
    from linux import namespace
    parent = root / "artifacts/rust/gui-run"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"{args.backend}-", dir=parent))
    print("Native evidence directory", output, flush=True)
    (output / "namespace.json").write_text(json.dumps({
        key: os.readlink(f"/proc/self/ns/{key}") for key in ("net", "mnt", "pid", "ipc", "user")}))
    binary = (args.binary or root / "artifacts/rust/gui-build/release/native-gui-assessment").resolve(strict=True)
    inputs = binary.with_suffix(".inputs.json")
    if inputs.is_file():
        (output / "build.json").write_bytes(inputs.read_bytes())
    driver_sources = [*sorted(HERE.glob("*.py")), *((root / "tools/rust-qa/performance" / name)
                      for name in ("linux.py", "session.py", "x11.py"))]
    (output / "driver.json").write_text(json.dumps({p.relative_to(root).as_posix():
        hashlib.sha256(p.read_bytes()).hexdigest() for p in driver_sources}, indent=2) + "\n")
    command = namespace(output, binary.parent, None)
    app_mount = command.index("/app")
    command[app_mount - 2:app_mount + 1] = ["--dir", "/app", "--ro-bind", str(binary), "/app/native-gui-assessment"]
    boundary = command.index("--chdir")
    drivers = Path("/usr/share/vulkan/icd.d")
    software = next((p for name in (f"lvp_icd.{platform.machine()}.json", "lvp_icd.json")
                     if (p := drivers / name).is_file()), None)
    if software is None:
        raise RuntimeError(f"No native Mesa lavapipe Vulkan manifest in {drivers}")
    ime_mounts = []
    if args.ime:
        for name in ("anthy-unicode", "anthy"):
            dictionary = Path("/usr/share") / name / "anthy.dic"
            if dictionary.is_file():
                config = output / f"{name}.conf"
                config.write_text(f"prefix /usr\ndatadir /usr/share\nANTHYDIR {dictionary.parent}/\n"
                                  f"DIC_FILE {dictionary}\nZIPDICT_EUC {dictionary.parent}/zipcode.t\n")
                ime_mounts.extend(["--ro-bind", str(config), f"/etc/{name}.conf"])
    command[boundary:] = ["--ro-bind", str(HERE), "/gui", "--setenv", "IFW_QA_ISOLATED", "1",
        "--setenv", "VK_DRIVER_FILES", str(software), *ime_mounts,
        "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime",
        *(["--setenv", "MESA_VK_WSI_PRESENT_MODE", args.present_mode] if args.present_mode else []),
        "--chdir", "/qa", "--",
        "/usr/bin/python3", "/gui/native.py", "--inside", "--backend", args.backend,
        *(["--input"] if args.input else []), *(["--ime"] if args.ime else []),
        *(["--present-mode", args.present_mode] if args.present_mode else []), *(["--capture"] if args.capture else [])]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("x11", "wayland"), default="x11")
    parser.add_argument("--binary", type=Path, help="A native assessment executable from a release build")
    parser.add_argument("--input", action="store_true", help="Use the private AT-SPI registry and inject keyboard input")
    parser.add_argument("--ime", action="store_true", help="Exercise a private IBus XIM composition on X11")
    parser.add_argument("--present-mode", choices=("immediate", "mailbox", "fifo"),
                        help="Diagnostic Mesa Vulkan WSI override on this private software renderer")
    parser.add_argument("--capture", action="store_true", help="Attach a private PipeWire consumer to Mutter's virtual monitor")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.ime and (not args.input or args.backend != "x11"):
        parser.error("--ime requires --backend x11 --input")
    sys.exit(inside(args.backend, args.input, args.ime, args.present_mode, args.capture) if args.inside else launch(args))
