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

from text_observations import CASES, check_case

HERE = Path(__file__).resolve().parent


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
    def __init__(self, observer):
        self.observer = observer

    def send(self, msg, key, pos):
        hwnd = self.observer.visible()
        if not hwnd or not self.observer.post(hwnd, msg, key, pos):
            raise RuntimeError("Could not deliver a native input message to the synthetic window")
        time.sleep(.09)

    def mouse(self, msg, down, x, y):
        self.send(msg, int(down), (y << 16) | x)

    def click(self, x, y):
        self.mouse(0x200, False, x, y)
        self.mouse(0x201, True, x, y)
        self.mouse(0x202, False, x, y)

    def drag(self, x0, x1, y):
        self.mouse(0x200, False, x0, y)
        self.mouse(0x201, True, x0, y)
        self.mouse(0x200, True, x1, y)
        self.mouse(0x202, False, x1, y)

    def key(self, name):
        vk, scan = {"Right": (0x27, 0x4d), "Left": (0x25, 0x4b), "Delete": (0x2e, 0x53)}[name]
        bits = 1 | (scan << 16) | (1 << 24)
        self.send(0x100, vk, bits)
        self.send(0x101, vk, bits | (3 << 30))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(binary, work, observer=None, display="Windows test desktop"):
    windows = os.name == "nt"
    subject = json.loads((binary.parent / "subject.json").read_text(encoding="utf-8"))
    if digest(binary) != subject["binarySha256"]:
        raise ValueError("Executable differs from its source-bound build")
    report = {"target": subject["target"], "binarySha256": subject["binarySha256"],
              "subjectSha256": digest(binary.parent / "subject.json"), "observerSha256": digest(Path(__file__)),
              "assessmentSha256": digest(HERE / "text_observations.py"), "display": display, "runs": []}
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
    for profile, name in (("latin", "glyphs"), ("fallback", "glyphs"), ("fallback", "mixed"), ("fallback", "numbers")):
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
                controls = WindowsInput(target)
                process.stdin.write(b"N")
                process.stdin.flush()
            else:
                controls = X11Input(observer)
            result = check_case(profile, name, controls, process, log, directory)
            if windows:
                process.stdin.write(b"Q")
                process.stdin.close()
            else:
                action("quit")
            if process.wait(timeout=15) != 0 or "DRAINED" not in log.read_text(encoding="utf-8", errors="replace"):
                raise RuntimeError("Native supervisor did not drain")
        output = log.read_text(encoding="utf-8", errors="replace")
        adapter = next(line.removeprefix("ADAPTER ") for line in output.splitlines() if line.startswith("ADAPTER "))
        result.update(frameSha256=digest(directory / "observed.ppm"), nativeLogSha256=digest(log), adapter=adapter)
        report["runs"].append(result)
        print(profile, name, result["renderedCoverageMatches"], result["observedVisual"], result.get("selected"),
              flush=True)
        (work / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if not all(row["renderedCoverageMatches"] for row in result["runs"]):
        raise SystemExit("Unexpected font raster or fallback control")
    glyphs = result["runs"][1]
    if not glyphs["editMatches"] or glyphs["caretAfterRightFromStart"] != 1:
        raise SystemExit("Native CJK caret and selection criteria failed")
    if args.require_bidi and not all(row["visualOrderMatches"] and row["editMatches"]
                                     and row["keyboardMatches"] and row.get("fieldPixelOrderMatchesOracle", True) for row in result["runs"][2:]):
        raise SystemExit("Native bidirectional acceptance criteria failed")


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        main()
