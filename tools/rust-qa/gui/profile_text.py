"""Check the maintained Linux application's real filename editor through AT-SPI and XTEST."""
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


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def clip(text):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    print("CLIPBOARD_READY", flush=True)
    Gtk.main()


def ink(display, window, bounds):
    from collections import Counter
    from x11 import bind
    x, y, width, height = bounds
    if not (0 <= x < 640 and 0 <= y < 400 and 0 < width <= 64 and 0 < height <= 100):
        raise ValueError(f"Invalid native character rectangle {bounds}")
    x11 = c.CDLL("libX11.so.6")
    get = bind(x11, "XGetImage", c.c_void_p, c.c_void_p, c.c_ulong, c.c_int, c.c_int,
               c.c_uint, c.c_uint, c.c_ulong, c.c_int)
    pixel = bind(x11, "XGetPixel", c.c_ulong, c.c_void_p, c.c_int, c.c_int)
    destroy = bind(x11, "XDestroyImage", c.c_int, c.c_void_p)
    img = get(display.display, window, x, y, width, height, 0xffffffff, 2)
    if not img:
        raise ValueError("Failed to read native text field pixels")
    try:
        values = {(ix, iy): pixel(img, ix, iy) & 0xff for iy in range(height) for ix in range(width)}
    finally:
        destroy(img)
    background = Counter(values.values()).most_common(1)[0][0]
    diff = {pos: abs(v - background) for pos, v in values.items()}
    points = {pos for pos, val in diff.items() if val >= max(24, max(diff.values()) / 2)}
    if not points:
        raise ValueError("Empty glyph rectangle")
    x0, y0 = map(min, zip(*points))
    normalized = sorted((px - x0, py - y0) for px, py in points)
    return {"inkPixels": len(points), "maskSha256": hashlib.sha256(json.dumps(normalized).encode()).hexdigest()}


def inside():
    sys.path[:0] = ["/gui", "/driver", "/coverage"]
    from desktop_input import Atspi, nodes, shortcut, start_accessibility, tap
    from native import X11Observer, action
    from observe import X11Input
    from session import checked_start, check_alive, private_session, stop, wait_for
    work = Path("/qa")
    namespaces = json.loads((work / "namespaces.json").read_text())
    if Path.home() != Path("/tmp/home") or not all(os.readlink("/proc/self/ns/" + n) != v for n, v in namespaces.items()):
        raise RuntimeError("A synthetic home and private user, IPC, PID, mount and network namespaces are required")
    os.umask(0o077)
    Path.home().mkdir()
    Path("/tmp/runtime").mkdir()
    os.environ["GSETTINGS_BACKEND"] = "memory"
    with ExitStack() as stack:
        display, server = private_session(stack)
        enabled = start_accessibility(stack)
        observer = X11Observer(display)
        controls = X11Input(observer)
        log = work / "application.log"
        app = checked_start(stack, ["/app/native-gui-assessment"], log)
        wait_for(lambda: check_alive(app, log) or observer.poll(), 15, "No native application window")
        observer.focus_for_input()
        def field():
            return next((n for n in nodes(app.pid) if n.get_name() == "Dateiname" and n.get_role_name() in ("text", "entry") and n.get_text_iface()), None)
        wait_for(lambda: enabled() and field(), 10, "Private filename missing from AT-SPI")
        def focused(n):
            return n.get_state_set().contains(Atspi.StateType.FOCUSED)
        def value():
            return Atspi.Text.get_text(field(), 0, -1)
        def input_text(text):
            n = field()
            if not focused(n):
                bounds = Atspi.Component.get_extents(n, Atspi.CoordType.WINDOW)
                controls.click(bounds.x + bounds.width // 2, bounds.y + bounds.height // 2)
                wait_for(lambda: focused(field()), 3, "Filename focus not reported")
            shortcut(observer, ord("a"), 0xffe3)
            clip_log = work / "clipboard.log"
            with ExitStack() as child:
                owner = checked_start(child, [sys.executable, "/gui/profile_text.py", "--clipboard", text], clip_log)
                wait_for(lambda: check_alive(owner, clip_log) or "CLIPBOARD_READY" in clip_log.read_text(),
                         6, "No private clipboard owner")
                shortcut(observer, ord("v"), 0xffe3)
                wait_for(lambda: value() == text, 6, f"Actual editor did not receive {text!r}")
                stop(owner)
        def rect(i):
            box = Atspi.Text.get_character_extents(field(), i, Atspi.CoordType.WINDOW)
            return [box.x, box.y, box.width, box.height]
        def caret():
            return Atspi.Text.get_caret_offset(field())
        def selected():
            node = field()
            if not Atspi.Text.get_n_selections(node):
                return ""
            marks = Atspi.Text.get_selection(node, 0)
            return Atspi.Text.get_text(node, marks.start_offset, marks.end_offset)
        report = dict(display=server, executableSha256=sha(Path("/app/native-gui-assessment")),
                      buildReceiptSha256=sha(work / "build.json"), drivers=json.loads((work / "drivers.json").read_text()), cases=[])
        sample = "A | あ | 界 | ⬟ | ب | ت | ث | " + chr(0x10fffd)
        input_text(sample)
        boxes = {ch: rect(sample.index(ch)) for ch in ("A", "あ", "界", "⬟", "ب", "ت", "ث", chr(0x10fffd))}
        tap(observer, 0xff09)
        wait_for(lambda: not focused(field()), 4, "The filename caret is still visible in the sample")
        time.sleep(.15)
        samples = {f"U+{ord(ch):04X}": ink(display, observer.poll(), box) for ch, box in boxes.items()}
        if len({v["maskSha256"] for v in samples.values()}) != len(samples):
            raise ValueError(f"Canonical GUI rendered duplicate glyph masks: {samples}")
        report["windowReadback"] = samples
        for text, target, arrows, fraction, anchor in (("あ界⬟.jpg", "界", [0, 1, 0], .12, "あ"),
                ("L-بتث-R.jpg", "ث", [4, 3, 4], .88, "ث"), ("L-ب12ت-R.jpg", "ت", [3, 4, 3], .12, "1")):
            input_text(text)
            first = rect(text.index(anchor))
            x, y, w, h = first
            controls.click(round(x + w * fraction), round(y + h * .5))
            observed = [caret()]
            for key in ("Right", "Left"):
                controls.key(key)
                observed.append(caret())
            if observed != arrows:
                raise ValueError(f"Incorrect native arrow movement for {text}: {observed}, expected {arrows}")
            time.sleep(.7)
            x, y, w, h = rect(text.index(target))
            controls.drag(round(x + w * .1), round(x + w * .9), round(y + h * .5))
            wait_for(lambda: selected() == target, 4, f"Wrong native pointer selection in {text}")
            order = []
            if text == "L-ب12ت-R.jpg":
                order = sorted(range(2, 6), key=lambda index: rect(index)[0])
                if order != [5, 3, 4, 2]:
                    raise ValueError(f"Wrong native character order around European digits: {order}")
            controls.key("Delete")
            after = text.replace(target, "")
            wait_for(lambda: value() == after, 4, f"Unexpected native Delete result for {text}")
            case = dict(text=text, selected=target, arrowIndices=observed, after=after)
            if order:
                case["visualRunIndices"] = order
            report["cases"].append(case)
        action("quit")
        if app.wait(timeout=10) != 0:
            raise RuntimeError("Application failed to drain")
        (work / "observations.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main():
    root = HERE.parents[2]
    sys.path.insert(0, str(HERE.parent / "performance"))
    from linux import namespace
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=root / "artifacts/rust/gui-build/release/native-gui-assessment")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    subject = json.loads(binary.with_suffix(".inputs.json").read_text(encoding="utf-8"))
    if sha(binary) != subject["binary_sha256"] or "sourceTrees" not in subject:
        raise ValueError("Use the source-bound maintained GUI build")
    if any(sha(root / name) != digest for name, digest in subject["sources"].items()):
        raise ValueError("Rebuild the maintained GUI after changing its compiler inputs")
    import source_profile
    source_profile.validate()
    if sha(source_profile.REVIEW) != subject["sourceProfileSha256"]:
        raise ValueError("Rebuild the GUI with the current reviewed font and text inputs")
    records = root / "artifacts/rust/gui-run"
    records.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="profile-text-", dir=records))
    print(work, flush=True)
    (work / "namespaces.json").write_text(json.dumps({k: os.readlink("/proc/self/ns/" + k)
                                                    for k in ("user", "ipc", "pid", "mnt", "net")}))
    (work / "build.json").write_text(json.dumps(subject, indent=2) + "\n")
    drivers = ["gui/profile_text.py", "gui/native.py", "gui/desktop_input.py", "performance/linux.py",
               "performance/session.py", "performance/x11.py", "font-coverage/observe.py", "font-coverage/text_observations.py"]
    (work / "drivers.json").write_text(json.dumps({n: sha(HERE.parent / n) for n in drivers}, indent=2) + "\n")
    cmd = namespace(work, binary.parent, None)
    app = cmd.index("/app")
    cmd[app - 2:app + 1] = ["--dir", "/app", "--ro-bind", str(binary), "/app/native-gui-assessment"]
    icds = Path("/usr/share/vulkan/icd.d")
    icd = next(p for p in [icds / f"lvp_icd.{platform.machine()}.json", icds / "lvp_icd.json"] if p.is_file())
    cmd[cmd.index("--chdir"):] = ["--ro-bind", str(HERE), "/gui", "--ro-bind", str(HERE.parent / "font-coverage"),
        "/coverage", "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime", "--setenv", "VK_DRIVER_FILES", str(icd),
        "--setenv", "IFW_QA_ISOLATED", "1", "--chdir", "/qa", "--", "/usr/bin/python3", "/gui/profile_text.py", "--inside"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    elif len(sys.argv) == 3 and sys.argv[1] == "--clipboard":
        clip(sys.argv[2])
    else:
        main()
