"""Observe the ordinary Rust window while a private Linux desktop changes its appearance."""
import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
PORTAL = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
SETTINGS = "org.freedesktop.portal.Settings"
APPEARANCE = "org.freedesktop.appearance"
CONTROL_REVISION = "45dc03bc05d71766b19f4d0b56f37dbc92951ef9"
SERVICES = {
    "org.freedesktop.impl.portal.PermissionStore": "xdg-permission-store",
    "org.freedesktop.impl.portal.desktop.gtk": "xdg-desktop-portal-gtk",
    PORTAL: "xdg-desktop-portal",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def matches(rgb, scheme, high):
    if len(set(rgb)) != 1:
        return False
    level = rgb[0]
    if high:
        return level == (0 if scheme == "prefer-dark" else 255)
    return 0 < level <= 80 if scheme == "prefer-dark" else 175 <= level < 255


def sample(display, window, subject):
    from x11 import bind
    prop = subprocess.check_output(["xprop", "-id", str(window), "_NET_WM_PID", "_NET_WM_NAME"], text=True)
    if not re.search(rf"^_NET_WM_PID\(CARDINAL\) = {subject.pid}$", prop, re.M) or '"Desktop input probe"' not in prop:
        raise ValueError("The visible X11 window does not belong to the synthetic Rust GUI")
    x11 = c.CDLL("libX11.so.6")
    grab = bind(x11, "XGetImage", c.c_void_p, c.c_void_p, c.c_ulong, c.c_int, c.c_int,
                c.c_uint, c.c_uint, c.c_ulong, c.c_int)
    color = bind(x11, "XGetPixel", c.c_ulong, c.c_void_p, c.c_int, c.c_int)
    release = bind(x11, "XDestroyImage", c.c_int, c.c_void_p)
    def region(left, top, width, height):
        image = grab(display.display, window, left, top, width, height, c.c_ulong(-1).value, 2)
        if not image:
            raise RuntimeError("The GUI's client area could not be captured")
        try:
            return Counter(color(image, x, y) & 0xFFFFFF for y in range(height) for x in range(width))
        finally:
            release(image)

    # The lower right is empty. The first static label is at the top left.
    panel = region(430, 240, 16, 16)
    if len(panel) != 1:
        raise ValueError("The measured panel did not have a uniform color")
    rgb = next(iter(panel))
    label = region(7, 7, 64, 16)
    def channels(pixel):
        return [(pixel >> offset) & 0xFF for offset in (16, 8, 0)]
    return {"panelRgb": channels(rgb), "darkInkPixels": sum(n for p, n in label.items() if max(channels(p)) <= 16),
            "lightInkPixels": sum(n for p, n in label.items() if min(channels(p)) >= 239)}


def inside(control):
    from gi.repository import Gio, GLib
    sys.path.insert(0, "/driver")
    from session import checked_start, check_alive, private_session, wait_for
    out = Path("/qa")
    inputs = json.loads((out / "inputs.json").read_text())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or not all(os.readlink("/proc/self/ns/" + k) != v for k, v in inputs["outerNamespaces"].items())
            or any(sha(Path(p)) != v for p, v in inputs["systemBinaries"].items())):
        raise RuntimeError("The test requires its own desktop and system inputs")
    os.umask(0o077)
    config = Path.home() / ".config/xdg-desktop-portal"
    config.mkdir(parents=True)
    (config / "portals.conf").write_text("[preferred]\ndefault=gtk\n")
    Path("/run/user/0").chmod(0o700)
    report = {"mode": "original-control" if control else "candidate", "passed": False, "settings": []}
    try:
        with ExitStack() as stack:
            display, report["xserver"] = private_session(stack)
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)

            def pid(name):
                try:
                    reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                          "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)), None,
                                          Gio.DBusCallFlags.NONE, 500, None)
                    return reply.unpack()[0]
                except GLib.Error:
                    return None

            processes = {}
            for name, command in SERVICES.items():
                log = out / (command + ".log")
                process = checked_start(stack, ["/usr/libexec/" + command], log)
                wait_for(lambda: check_alive(process, log) or pid(name) == process.pid, 9, "Private service unavailable: " + name)
                processes[name] = process.pid
                if name == PORTAL:
                    frontend = process
            report["desktopServices"] = processes

            def settings():
                reply = bus.call_sync(PORTAL, OBJECT, SETTINGS, "ReadAll", GLib.Variant("(as)", ([APPEARANCE],)),
                                      None, Gio.DBusCallFlags.NONE, 1500, None)
                return reply.unpack()[0].get(APPEARANCE, {})

            # Only read capabilities actually exported by this distribution's portal.
            initial = settings()
            if "color-scheme" not in initial:
                raise RuntimeError("The desktop's Settings portal did not export its color scheme")
            contrast_capable = "contrast" in initial
            report["initialPortal"] = initial
            colors = Gio.Settings.new("org.gnome.desktop.interface")
            contrast = Gio.Settings.new("org.gnome.desktop.a11y.interface")

            def change(scheme, high):
                if not colors.set_string("color-scheme", scheme) or not contrast.set_boolean("high-contrast", high):
                    raise RuntimeError("The private GNOME settings backend refused the requested state")
                Gio.Settings.sync()
                expected = {"color-scheme": {"prefer-dark": 1, "prefer-light": 2}[scheme]}
                if contrast_capable:
                    expected["contrast"] = int(high)
                def value():
                    observed = settings()
                    return observed if all(observed.get(k) == v for k, v in expected.items()) else None
                return wait_for(value, 5, "The portal did not report " + str(expected))

            established = change("prefer-light", False)
            log = out / "application.log"
            subject = checked_start(stack, ["/app/native-gui-assessment"], log)
            wait_for(lambda: check_alive(subject, log) or pid("org.example.IfwGuiProbe") == subject.pid,
                     8, "The Rust application did not acquire its own desktop address")
            window = wait_for(lambda: check_alive(subject, log) or display.visible(), 12, "No application window")
            wait_for(lambda: "ADAPTER " in log.read_text() and check_alive(subject, log) is None, 10, "No native renderer")
            report["application"] = {"pid": subject.pid, "xid": window}
            cases = [("prefer-light", False), ("prefer-dark", False)]
            if contrast_capable:
                cases.extend([("prefer-dark", True), ("prefer-light", True)])
            cases.append(("prefer-light", False))
            for index, (scheme, high) in enumerate(cases):
                # Observe the final return to the normal palette across a native hide and reopen.
                reopen = index == len(cases) - 1
                if reopen:
                    display.request_close(window)
                    wait_for(lambda: check_alive(subject, log) or display.visible() is None, 5, "Window stayed visible")
                portal = established if index == 0 else change(scheme, high)
                if reopen:
                    bus.call_sync("org.example.IfwGuiProbe", "/org/example/IfwGuiProbe", "org.freedesktop.Application",
                                  "Activate", GLib.Variant("(a{sv})", ({},)), None, Gio.DBusCallFlags.NONE, 2000, None)
                    window = wait_for(lambda: check_alive(subject, log) or display.visible(), 5, "Activation did not reopen the window")
                deadline = time.monotonic() + 2
                while True:
                    check_alive(subject, log)
                    pixels = sample(display, window, subject)
                    ink = pixels["lightInkPixels" if scheme == "prefer-dark" else "darkInkPixels"]
                    suited = matches(pixels["panelRgb"], scheme, high) and (not high or ink >= 4)
                    if suited or time.monotonic() >= deadline:
                        break
                    time.sleep(.05)
                time.sleep(.12)
                stable = pixels == sample(display, window, subject)
                report["settings"].append({"scheme": scheme, "highContrast": high, "portal": portal,
                                           **pixels, "stable": stable, "afterReopen": reopen, "xid": window,
                                           "matches": stable and suited})
            if not control:
                # Restart only this session's frontend. The GTK backend retains the private settings.
                frontend.terminate()
                frontend.wait(timeout=5)
                wait_for(lambda: pid(PORTAL) is None, 5, "Previous frontend still owns the portal")
                if not colors.set_string("color-scheme", "prefer-dark"):
                    raise RuntimeError("Private dark setting rejected while the frontend was down")
                Gio.Settings.sync()
                restart_log = out / "portal-restart.log"
                replacement = checked_start(stack, ["/usr/libexec/xdg-desktop-portal"], restart_log)
                wait_for(lambda: check_alive(replacement, restart_log) or pid(PORTAL) == replacement.pid,
                         8, "Replacement frontend did not acquire the private address")
                states = []
                for scheme in ("prefer-dark", "prefer-light"):
                    values = change(scheme, False)
                    def painted():
                        check_alive(subject, log)
                        screen = sample(display, window, subject)
                        return screen if matches(screen["panelRgb"], scheme, False) else None
                    states.append({"scheme": scheme, "portal": values, **wait_for(painted, 4, "Stale appearance after portal restart")})
                report["portalRestart"] = {"oldPid": frontend.pid, "newPid": replacement.pid, "states": states}
            bus.call_sync("org.example.IfwGuiProbe", "/org/example/IfwGuiProbe", "org.freedesktop.Application",
                          "ActivateAction", GLib.Variant("(sava{sv})", ("quit", [], {})), None,
                          Gio.DBusCallFlags.NONE, 2000, None)
            if subject.wait(timeout=8) != 0 or "DRAINED passes=" not in log.read_text():
                raise ValueError("The synthetic application did not drain on Quit")
            cases = report["settings"]
            report["normalPaletteRestored"] = cases[-1]["panelRgb"] == cases[0]["panelRgb"]
            report["allSettingsMatched"] = all(case["matches"] for case in cases) and report["normalPaletteRestored"]
            if control:
                report["passed"] = all(case["stable"] and case["panelRgb"] == [27, 27, 27] for case in cases)
            else:
                report["passed"] = report["allSettingsMatched"]
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


def launch(binary, control):
    root = HERE.parents[2]
    sys.path.insert(0, str(HERE.parent / "performance"))
    from linux import namespace
    binary = binary.resolve(strict=True)
    receipt = binary.with_suffix(".inputs.json")
    if not receipt.exists():
        receipt = root / "artifacts/rust/gui-native" / (platform.machine() + "-unknown-linux-gnu") / "build.json"
    build = json.loads(receipt.read_text())
    if sha(binary) != (build.get("binary_sha256") or build.get("binarySha256")):
        raise ValueError("The Rust image differs from its build receipt")
    sources = build.get("sources") or build["compilerSources"]
    needed = {"tools/rust-qa/gui/Cargo.toml", "tools/rust-qa/gui/src/main.rs", "tools/rust-qa/gui/src/linux.rs",
              "rust/crates/desktop-lifecycle/src/lib.rs"}
    if not control:
        needed.update({"tools/rust-qa/gui/src/linux_appearance.rs", "tools/rust-qa/gui/src/appearance_style.rs"})
    if not needed.issubset(sources) or build["target"] != platform.machine() + "-unknown-linux-gnu":
        raise ValueError("Missing source or native target evidence")
    for name, expected in sources.items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Build receipt contains a non-repository path")
        if control:
            blob = subprocess.check_output(["git", "show", f"{CONTROL_REVISION}:{name}"], cwd=root)
            digest = hashlib.sha256(blob).hexdigest()
        else:
            digest = sha(root / name)
        if digest != expected:
            raise ValueError("Source differs from the GUI build: " + name)
    runs = root / "artifacts/rust/appearance/runs"
    runs.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(dir=runs, prefix=platform.machine() + "-"))
    print(out, flush=True)
    paths = [Path("/usr/libexec") / name for name in SERVICES.values()]
    drivers = [HERE / "linux.py", *(HERE.parent / "performance" / p for p in ("linux.py", "session.py", "x11.py"))]
    (out / "inputs.json").write_text(json.dumps({"binarySha256": sha(binary), "build": build,
        "controlRevision": CONTROL_REVISION if control else None, "os": platform.freedesktop_os_release(),
        "drivers": {p.relative_to(root).as_posix(): sha(p) for p in drivers},
        "systemBinaries": {str(p): sha(p) for p in paths},
        "outerNamespaces": {k: os.readlink("/proc/self/ns/" + k) for k in ("net", "mnt", "pid", "ipc", "user")}},
        indent=2) + "\n")
    command = namespace(out, binary.parent, None)
    (out / "etc/passwd").write_text("root:x:0:0:Appearance fixture:/tmp/home:/bin/false\n")
    (out / "etc/group").write_text("root:x:0:\n")
    at = command.index("/app")
    command[at - 2:at + 1] = ["--dir", "/app", "--ro-bind", str(binary), "/app/native-gui-assessment"]
    drivers = Path("/usr/share/vulkan/icd.d")
    software = next(p for name in (f"lvp_icd.{platform.machine()}.json", "lvp_icd.json") if (p := drivers / name).is_file())
    command[command.index("--chdir"):] = [
        "--uid", "0", "--gid", "0", "--dir", "/run/user/0",
        "--ro-bind", str(HERE), "/appearance", "--setenv", "XDG_RUNTIME_DIR", "/run/user/0",
        "--setenv", "GSETTINGS_BACKEND", "keyfile", "--setenv", "XDG_CURRENT_DESKTOP", "IFWQA",
        "--setenv", "GDK_BACKEND", "x11", "--setenv", "NO_AT_BRIDGE", "1", "--setenv", "GTK_A11Y", "none",
        "--setenv", "GTK_USE_PORTAL", "0", "--setenv", "IFW_QA_ISOLATED", "1", "--setenv", "VK_DRIVER_FILES", str(software),
        "--chdir", "/qa", "--", "/usr/bin/python3", "/appearance/linux.py", "--inside",
        *(["--original-control"] if control else [])]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--original-control", action="store_true", help="Observe the original unadapted Linux GUI")
    args = parser.parse_args()
    if not args.inside and args.binary is None:
        parser.error("Choose the audited native GUI executable with --binary")
    raise SystemExit(inside(args.original_control) if args.inside else launch(args.binary, args.original_control))
