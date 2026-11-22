"""Run the same source-bound text cases on a private X11 server or a Windows test desktop."""
import argparse
from contextlib import ExitStack
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from text_observations import CASES, MissingObservation, check_case, last_field_pointer, wait_value

HERE = Path(__file__).resolve().parent
TRIALS = (("latin", "glyphs"), ("fallback", "glyphs"), ("fallback", "mixed"), ("fallback", "numbers"))


class X11Input:
    def __init__(self, observer):
        from x11 import bind
        self.observer = observer
        self.display = observer.display
        test = c.CDLL("libXtst.so.6")
        self.motion = bind(test, "XTestFakeMotionEvent", c.c_int, c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong)
        self.button = bind(test, "XTestFakeButtonEvent", c.c_int, c.c_void_p, c.c_uint, c.c_int, c.c_ulong)
        self.translate = bind(c.CDLL("libX11.so.6"), "XTranslateCoordinates", c.c_int,
                              c.c_void_p, c.c_ulong, c.c_ulong, c.c_int, c.c_int,
                              c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_ulong))

    def move(self, x, y):
        window = self.observer.poll()
        rx, ry, child = c.c_int(), c.c_int(), c.c_ulong()
        if not window or not self.translate(self.display.display, window, self.display.root, x, y,
                                            c.byref(rx), c.byref(ry), c.byref(child)):
            raise RuntimeError("No observed private top-level client")
        if not self.motion(self.display.display, -1, rx.value, ry.value, 0):
            raise RuntimeError("Could not move private X11 pointer")
        self.sync()

    def sync(self):
        self.display.sync(self.display.display, 0)
        time.sleep(.06)

    def press(self, down):
        if not self.button(self.display.display, 1, int(down), 0):
            raise RuntimeError("Could not send private X11 button")
        self.sync()

    def click(self, x, y):
        self.move(x, y)
        self.press(True)
        self.press(False)

    def drag(self, x0, x1, y):
        self.move(x0, y)
        self.press(True)
        self.move(x1, y)
        self.press(False)

    def key(self, name):
        self.observer.focus_for_input()
        self.sync()
        key = {"Right": 0xff53, "Left": 0xff51, "Delete": 0xffff}[name]
        self.observer.key(key, True)
        self.observer.key(key, False)
        self.sync()


class WindowsInput:
    """Send window-targeted messages only to the synthetic child's verified top-level HWND."""
    def __init__(self, observer, process, log):
        self.observer = observer
        self.process, self.log = process, log
        self.first_gesture = True
        self.pointer_positions = {"ownedDesktopPoint": 0, "windowMessagesOnly": 0}
        self.pointer_events = []
        from ctypes import wintypes as w
        user = c.WinDLL("user32", use_last_error=True)
        self.client_to_screen = user.ClientToScreen
        self.client_to_screen.argtypes = [w.HWND, c.POINTER(w.POINT)]
        self.at_point = user.WindowFromPoint
        self.at_point.argtypes = [w.POINT]
        self.at_point.restype = w.HWND
        self.set_position = user.SetCursorPos
        self.set_position.argtypes = [c.c_int, c.c_int]
        self.cursor = user.GetCursorPos
        self.cursor.argtypes = [c.POINTER(w.POINT)]
        self.foreground = user.GetForegroundWindow
        self.foreground.argtypes = []
        self.foreground.restype = w.HWND
        self.activate = user.SetForegroundWindow
        self.activate.argtypes = [w.HWND]
        self.activate.restype = w.BOOL
        self.point = w.POINT
        self.disposable = (os.getenv("RUNNER_ENVIRONMENT") == "github-hosted"
                           and os.getenv("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch"
                           and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust")

    def missing(self, phase):
        messages = self.log.read_text(encoding="utf-8", errors="replace")
        raise MissingObservation(phase, self.process.poll(), messages, 0)

    def await_pointer(self, phase, predicate):
        def match(messages):
            state = last_field_pointer(messages)
            return state if state and predicate(state) else None
        return wait_value(match, self.process, self.log, phase, seconds=8)

    def target_point(self, hwnd, x, y, event, *, check_cursor):
        event["foregroundOwned"] = self.observer.visible() == hwnd and self.foreground() == hwnd
        if not event["foregroundOwned"]:
            self.missing("owned foreground window for the pointer")
        position = self.point(x, y)
        if not self.client_to_screen(hwnd, c.byref(position)):
            self.missing("owned window client coordinates")
        event["screenPixel"] = [position.x, position.y]
        event["pointOwned"] = self.observer.ancestor(self.at_point(position), 2) == hwnd
        if not event["pointOwned"]:
            self.missing("uncovered point on the owned window")
        if self.disposable and check_cursor:
            actual = self.point()
            event["cursorMatched"] = bool(self.cursor(c.byref(actual))) and (position.x, position.y) == (actual.x, actual.y)
            event["cursorOnSubject"] = event["cursorMatched"] and self.observer.ancestor(self.at_point(actual), 2) == hwnd
            if not event["cursorOnSubject"]:
                self.missing("cursor readback at the owned window point")
        return position

    def move(self, hwnd, x, y, held, previous_pass):
        event = {"action": "move", "hwnd": hex(hwnd), "clientPixel": [x, y], "moveHeld": held}
        self.pointer_events.append(event)
        position = self.target_point(hwnd, x, y, event, check_cursor=False)
        if self.disposable:
            event["cursorMoved"] = bool(self.set_position(position.x, position.y))
            if not event["cursorMoved"]:
                self.missing("native pointer motion on the disposable desktop")
            self.pointer_positions["ownedDesktopPoint"] += 1
        else:
            event["movePosted"] = bool(self.observer.post(hwnd, 0x200, int(held), (y << 16) | x))
            if not event["movePosted"]:
                self.missing("pointer motion addressed to the owned window")
            self.pointer_positions["windowMessagesOnly"] += 1
        state = self.await_pointer(f"field pointer at ({x}, {y})",
                                  lambda p: p["pass"] > previous_pass and p["clientPixel"] == [x, y]
                                  and p["viewportFocused"] and p["fieldHit"] and p["primaryDown"] == held)
        self.target_point(hwnd, x, y, event, check_cursor=True)
        event["fieldPass"] = state["pass"]
        return state["pass"]

    def button(self, hwnd, x, y, pressed):
        message = 0x201 if pressed else 0x202
        event = {"action": "button", "hwnd": hex(hwnd), "clientPixel": [x, y], "button": message}
        self.pointer_events.append(event)
        self.target_point(hwnd, x, y, event, check_cursor=True)
        event["buttonPosted"] = bool(self.observer.post(hwnd, message, int(pressed), (y << 16) | x))
        if not event["buttonPosted"]:
            self.missing("button addressed to the owned window")
        time.sleep(.09)

    def gesture(self, x0, x1, y):
        hwnd = self.observer.visible()
        if not hwnd:
            self.missing("visible owned window for the pointer")
        if self.first_gesture and self.disposable and self.foreground() != hwnd:
            self.pointer_events.append({"action": "activate", "hwnd": hex(hwnd), "accepted": bool(self.activate(hwnd))})
        self.first_gesture = False
        start = self.await_pointer("active owned viewport before pointer motion",
                                   lambda p: p["viewportFocused"] and not p["primaryDown"]
                                   and self.observer.visible() == hwnd and self.foreground() == hwnd)
        # Winit filters duplicate coordinates. Approach from a distinct in-field pixel,
        # then witness the resolved field at the actual hit point before pressing once.
        approach = x0 + (2 if start["clientPixel"] == [x0 + 1, y] else 1)
        pass_no = self.move(hwnd, approach, y, False, start["pass"])
        pass_no = self.move(hwnd, x0, y, False, pass_no)
        self.button(hwnd, x0, y, True)
        if x0 != x1:
            self.move(hwnd, x1, y, True, pass_no)
        self.button(hwnd, x1, y, False)

    def click(self, x, y):
        self.gesture(x, x, y)

    def drag(self, x0, x1, y):
        self.gesture(x0, x1, y)

    def key(self, name):
        vk, scan = {"Right": (0x27, 0x4d), "Left": (0x25, 0x4b), "Delete": (0x2e, 0x53)}[name]
        bits = 1 | (scan << 16) | (1 << 24)
        hwnd = self.observer.visible()
        for message, lparam in ((0x100, bits), (0x101, bits | (3 << 30))):
            if not hwnd or self.observer.visible() != hwnd or self.foreground() != hwnd:
                self.missing("focused owned window for the keyboard")
            if not self.observer.post(hwnd, message, vk, lparam):
                self.missing("key addressed to the owned window")
            time.sleep(.09)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_report(work, report):
    pending = work / "result.json.pending"
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(work / "result.json")


def run(binary, work, observer=None, display="Windows test desktop"):
    windows = os.name == "nt"
    subject = json.loads((binary.parent / "subject.json").read_text(encoding="utf-8"))
    if digest(binary) != subject["binarySha256"]:
        raise ValueError("Executable differs from its source-bound build")
    report = {"target": subject["target"], "binarySha256": subject["binarySha256"],
              "subjectSha256": digest(binary.parent / "subject.json"), "observerSha256": digest(Path(__file__)),
              "assessmentSha256": digest(HERE / "text_observations.py"), "display": display, "runs": [], "failures": []}
    if windows:
        sys.path.insert(0, str(HERE.parent))
        spec = importlib.util.spec_from_file_location("font_fixture_windows", HERE.parent / "observe-windows-gui.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        from native import action
        version = subprocess.check_output(["fribidi", "--version"], text=True).splitlines()[:3]
        report["bidiOracle"] = version
        for name in ("mixed", "numbers"):
            text, expected = CASES[name]
            lines = subprocess.check_output(["fribidi", "--charset", "UTF-8", "--ltr", "--nopad", "--nobreak", "--vtol"],
                                           input=text + "\n", encoding="utf-8").splitlines()
            if list(map(int, lines[1].split())) != expected:
                raise ValueError("Independent Unicode bidi reference changed")
    for profile, name in TRIALS:
        directory = work / (profile + "-" + name)
        directory.mkdir()
        log = directory / "native.log"
        env = dict(os.environ, IFW_QA_ISOLATED="1", IFW_FONT_PROFILE=profile, IFW_FONT_CASE=name)
        if windows:
            for key in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
                scratch = directory / key.lower()
                scratch.mkdir()
                env[key] = str(scratch)
            env["WGPU_DX12_COMPILER"] = "Fxc"
        with log.open("wb") as output, ExitStack() as cleanup:
            process = subprocess.Popen([str(binary)], env=env, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.PIPE if windows else subprocess.DEVNULL)
            def stop():
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
            cleanup.callback(stop)
            if windows:
                target = module.Windows(process.pid)
                cleanup.callback(target.close)
                controls = WindowsInput(target, process, log)
                process.stdin.write(b"N")
                process.stdin.flush()
            else:
                controls = X11Input(observer)
            failure = None
            try:
                result = check_case(profile, name, controls, process, log, directory)
            except MissingObservation as error:
                failure = {"profile": profile, "name": name, "drained": False, **error.detail}
                report["failures"].append(failure)
                save_report(work, report)
                if process.poll() is not None:
                    raise
            finally:
                if windows:
                    pointer = {**controls.pointer_positions, "events": controls.pointer_events}
                    (directory / "pointer.json").write_text(json.dumps(pointer) + "\n", encoding="utf-8")
            if windows:
                process.stdin.write(b"Q")
                process.stdin.close()
            else:
                action("quit")
            if process.wait(timeout=15) != 0 or "DRAINED" not in log.read_text(encoding="utf-8", errors="replace"):
                raise RuntimeError("Native supervisor did not drain")
        output = log.read_text(encoding="utf-8", errors="replace")
        if failure is not None:
            failure.update(drained=True, nativeLogSha256=digest(log))
            if (directory / "observed.ppm").is_file():
                failure["frameSha256"] = digest(directory / "observed.ppm")
            if windows:
                failure["pointerSha256"] = digest(directory / "pointer.json")
            save_report(work, report)
            print(profile, name, "failed at", failure["phase"], flush=True)
            continue
        adapter = next(line.removeprefix("ADAPTER ") for line in output.splitlines() if line.startswith("ADAPTER "))
        result.update(frameSha256=digest(directory / "observed.ppm"), nativeLogSha256=digest(log), adapter=adapter)
        if windows:
            result["pointerSha256"] = digest(directory / "pointer.json")
        report["runs"].append(result)
        save_report(work, report)
        print(profile, name, result["renderedCoverageMatches"], ascii(result["observedVisual"]),
              ascii(result.get("selected")), flush=True)
    return report


def inside():
    sys.path[:0] = ["/gui", "/driver"]
    from native import X11Observer
    from session import private_session
    work = Path("/qa")
    outer = json.loads((work / "namespace.json").read_text())
    if Path.home() != Path("/tmp/home") or not all(os.readlink("/proc/self/ns/" + n) != ident for n, ident in outer.items()):
        raise RuntimeError("Private user, IPC, PID, mount and network namespaces required")
    os.umask(0o077)
    Path.home().mkdir()
    Path("/tmp/runtime").mkdir()
    with ExitStack() as stack:
        display, server = private_session(stack)
        run(Path("/app/native-gui-assessment"), work, X11Observer(display), server)


def main():
    from inputs import ART, ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    triples = json.loads((ROOT / "rust/toolchain-inputs.json").read_text(encoding="utf-8"))["targets"]
    parser.add_argument("target", choices=sorted(triples))
    parser.add_argument("--require-bidi", action="store_true")
    parser.add_argument("--bidi-candidate", action="store_true")
    args = parser.parse_args()
    variant = "-bidi" if args.bidi_candidate else ""
    subject = ART / "subjects" / (args.target + variant)
    work = Path(tempfile.mkdtemp(prefix=args.target + "-", dir=ART))
    if os.name == "nt":
        spec = importlib.util.spec_from_file_location("qa_platform", HERE.parent / "check-toolchain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if args.target != module.native_architecture() + "-pc-windows-msvc":
            raise ValueError("Native observation requires this host architecture")
        run(subject / "native-gui-assessment.exe", work)
    else:
        sys.path.insert(0, str(HERE.parent / "performance"))
        from linux import namespace
        if args.target != platform.machine() + "-unknown-linux-gnu":
            raise ValueError("Native observation requires this host architecture")
        outer = {n: os.readlink("/proc/self/ns/" + n) for n in ("user", "ipc", "pid", "mnt", "net")}
        (work / "namespace.json").write_text(json.dumps(outer))
        cmd = namespace(work, subject, None)
        cmd = cmd[:cmd.index("--chdir")]
        drivers = Path("/usr/share/vulkan/icd.d")
        icd = next(p for p in [drivers / f"lvp_icd.{platform.machine()}.json", drivers / "lvp_icd.json"] if p.is_file())
        cmd += ["--ro-bind", str(HERE), "/suite", "--ro-bind", str(HERE.parent / "gui"), "/gui",
                "--setenv", "XDG_RUNTIME_DIR", "/tmp/runtime", "--setenv", "VK_DRIVER_FILES", str(icd),
                "--chdir", "/qa", "--", "/usr/bin/python3", "/suite/observe.py", "--inside"]
        subprocess.run(cmd, check=True)
    result = json.loads((work / "result.json").read_text(encoding="utf-8"))
    print(work / "result.json")
    verify_result(result, args.require_bidi)


def verify_result(result, require_bidi):
    if result.get("failures"):
        missing = ", ".join(f"{row['profile']}/{row['name']} at {row['phase']}" for row in result["failures"])
        raise SystemExit("Missing native observations: " + missing)
    if [(row["profile"], row["name"]) for row in result["runs"]] != list(TRIALS):
        raise SystemExit("The four source-bound native font trials did not all complete")
    if not all(row["renderedCoverageMatches"] for row in result["runs"]):
        raise SystemExit("Unexpected font raster or fallback control")
    glyphs = result["runs"][1]
    if not glyphs["editMatches"] or glyphs["caretAfterRightFromStart"] != 1:
        raise SystemExit("Native CJK caret and selection criteria failed")
    if require_bidi and not all(row["visualOrderMatches"] and row["editMatches"] and row["keyboardMatches"]
                                and (row["name"] != "numbers" or row.get("fieldPixelOrderMatchesOracle") is True)
                                for row in result["runs"][2:]):
        raise SystemExit("Native bidirectional acceptance criteria failed")


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        main()
