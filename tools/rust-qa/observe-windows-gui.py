"""Observe the synthetic Rust window on a disposable native Windows desktop."""

import argparse
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

from windows_observer import select_powershell


TITLE = "Desktop input probe"
SHOW, HIDE = 0x8002, 0x8003
WM_CLOSE = 0x0010


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


class Windows:
    def __init__(self, pid):
        user = ctypes.WinDLL("user32", use_last_error=True)
        self.pid = pid
        self.events = []
        self.enum_callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        event_proc = ctypes.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)
        self.enumerate = bind(user, "EnumWindows", w.BOOL, self.enum_callback, w.LPARAM)
        self.owner = bind(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
        self.caption = bind(user, "GetWindowTextW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
        self.is_visible = bind(user, "IsWindowVisible", w.BOOL, w.HWND)
        self.ancestor = bind(user, "GetAncestor", w.HWND, w.HWND, w.UINT)
        self.post = bind(user, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.peek = bind(user, "PeekMessageW", w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT)
        self.dispatch = bind(user, "DispatchMessageW", w.LPARAM, ctypes.POINTER(w.MSG))
        hook = bind(user, "SetWinEventHook", w.HANDLE, w.DWORD, w.DWORD, w.HMODULE, event_proc,
                    w.DWORD, w.DWORD, w.DWORD)
        self.unhook = bind(user, "UnhookWinEvent", w.BOOL, w.HANDLE)

        @event_proc
        def callback(_hook, event, hwnd, object_id, child, _thread, timestamp):
            if hwnd and object_id == 0 and child == 0:
                self.events.append({"event": "show" if event == SHOW else "hide", "hwnd": hwnd,
                                    "root": self.ancestor(hwnd, 2) == hwnd,
                                    "winEventTimeMs": timestamp})

        self.callback = callback
        # Install on the single child before its inherited start pipe is released.
        self.hook = hook(SHOW, HIDE, None, self.callback, pid, 0, 0)
        if not self.hook:
            raise ctypes.WinError(ctypes.get_last_error())

    def pump(self):
        message = w.MSG()
        while self.peek(ctypes.byref(message), None, 0, 0, 1):
            self.dispatch(ctypes.byref(message))

    def visible(self):
        self.pump()
        matching = []

        @self.enum_callback
        def visit(hwnd, _data):
            owner = w.DWORD()
            self.owner(hwnd, ctypes.byref(owner))
            if owner.value == self.pid and self.is_visible(hwnd):
                caption = ctypes.create_unicode_buffer(256)
                self.caption(hwnd, caption, len(caption))
                if caption.value == TITLE:
                    matching.append(hwnd)
            return True

        if not self.enumerate(visit, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if len(matching) > 1:
            raise RuntimeError("Multiple visible assessment windows")
        return next(iter(matching), None)

    def close_window(self, hwnd):
        if self.visible() != hwnd or not self.post(hwnd, WM_CLOSE, 0, 0):
            raise RuntimeError("Could not deliver WM_CLOSE to the observed assessment window")

    def close(self):
        if not self.unhook(self.hook):
            raise ctypes.WinError(ctypes.get_last_error())


def run_case(binary, output, name, background, tray, reopen, speech_cues=None):
    log = output / (name + ".log")
    actions = []
    with tempfile.TemporaryDirectory(prefix="gui-profile-", dir=output) as scratch:
        profile = Path(scratch)
        env = {**os.environ, "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc",
               "USERPROFILE": scratch, "HOME": scratch, "TEMP": scratch, "TMP": scratch}
        if name == "dx12-recovery":
            env["IFW_QA_GRAPHICS"] = "recover"
        for key in ("APPDATA", "LOCALAPPDATA"):
            folder = profile / key
            folder.mkdir()
            env[key] = str(folder)
        with log.open("wb") as stream, subprocess.Popen(
            [str(binary), *(["--background"] if background else [])], stdin=subprocess.PIPE,
            stdout=stream, stderr=subprocess.STDOUT, cwd=profile, env=env,
        ) as process:
            observer = None
            try:
                observer = Windows(process.pid)

                def command(value):
                    process.stdin.write(value)
                    process.stdin.flush()

                def wait_for(condition, label):
                    start = time.monotonic()
                    while time.monotonic() - start < 35:
                        hwnd = observer.visible()
                        if process.poll() is not None:
                            raise RuntimeError(f"{name} exited before {label}, see {log}")
                        if condition(hwnd, log.read_text(encoding="utf-8", errors="replace")):
                            actions.append(label)
                            return hwnd
                        time.sleep(.01)
                    raise TimeoutError(f"{name} timed out during {label}, see {log}")

                def quiet(duration, allow_child_events):
                    until = time.monotonic() + duration
                    before = len(observer.events)
                    while time.monotonic() < until:
                        if observer.visible() or process.poll() is not None:
                            raise RuntimeError(f"Unexpected window or exit in {name}")
                        time.sleep(.005)
                    observer.pump()
                    if any(e["event"] == "show" and (e["root"] or not allow_child_events)
                           for e in observer.events[before:]):
                        raise RuntimeError(f"Transient visible window in {name}")

                command(b"T" if tray else b"N")
                hidden = background and tray
                intent = "BackgroundStartup" if hidden else "Visible"
                tray_state = "Available" if tray else "Unavailable"
                wait_for(lambda _, text: f"READY {intent} {tray_state}" in text, "supervisor ready")
                if hidden:
                    quiet(1, allow_child_events=False)
                    if any(e["event"] == "show" for e in observer.events):
                        raise RuntimeError("Window show event occurred before activation")
                    actions.append("hidden start without show events")
                if reopen:
                    if hidden:
                        command(b"O")
                    hwnd = wait_for(lambda window, text: window and "ADAPTER Dx12 " in text, "DX12 window visible")
                    wait_for(lambda _, text: any(e["event"] == "show" and e["hwnd"] == hwnd
                                                 for e in observer.events), "native show event observed")
                    if name in ("keyboard-accessibility", "dx12-recovery"):
                        driver = Path(__file__).with_name("observe-windows-input.ps1").resolve()
                        program, attempts = select_powershell(profile, "accessibility")
                        (output / "observer-hosts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
                        if not program:
                            raise RuntimeError("The Windows desktop observer did not start on this host")

                        def check_input(window, record_name, extra):
                            evidence = output / (record_name + ".json")
                            with (output / (record_name + "-observer.log")).open("wb") as observed:
                                subprocess.run([program, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta",
                                                "-ExecutionPolicy", "Bypass", "-File", str(driver),
                                                "-SubjectId", str(process.pid), "-WindowHandle", str(window),
                                                "-SubjectLog", str(log), "-OutputFile", str(evidence), *extra],
                                               env=env, cwd=profile, stdin=subprocess.DEVNULL, stdout=observed,
                                               stderr=subprocess.STDOUT, timeout=130 if speech_cues else 80, check=True)
                            record = json.loads(evidence.read_text(encoding="utf-8"))
                            if record.get("status") != "passed" or record["processId"] != process.pid:
                                raise ValueError("UI Automation observation did not verify the tested process")

                        if name == "dx12-recovery":
                            check_input(hwnd, "before", ["-RecoveryPhase", "before"])
                            previous = hwnd
                            command(b"G")
                            hwnd = wait_for(lambda window, text: window and window != previous
                                            and text.count("ADAPTER Dx12 ") >= 2
                                            and "GRAPHICS_LOST generation=1 reason=Destroyed" in text
                                            and "GRAPHICS_ATTEMPT generation=2 policy=cpu" in text
                                            and any(e["event"] == "show" and e["hwnd"] == window for e in observer.events),
                                            "new DX12 generation and native HWND after process-local device destruction")
                            check_input(hwnd, "after", ["-RecoveryPhase", "after"])
                            actions.append("edited and captured the restored focused field after recovery")
                        else:
                            check_input(hwnd, "input", ["-SpeechCues", str(speech_cues)] if speech_cues else [])
                            actions.append("UI Automation and keyboard input passed")
                    trace = log.read_text(encoding="utf-8", errors="replace")
                    releases = trace.count("WINDOW_RELEASED passes=")
                    adapters = trace.count("ADAPTER Dx12 ")
                    observer.close_window(hwnd)
                    wait_for(lambda window, text: window is None and text.count("WINDOW_RELEASED passes=") > releases,
                             "WM_CLOSE returned to supervisor")
                    quiet(.25, allow_child_events=True)
                    command(b"O")
                    wait_for(lambda window, text: window and text.count("ADAPTER Dx12 ") > adapters, "window reopened")
                command(b"Q")
                process.wait(timeout=20)
                observer.pump()
                messages = log.read_text(encoding="utf-8", errors="replace").splitlines()
                if process.returncode or not any(line.startswith("DRAINED passes=") for line in messages):
                    raise RuntimeError(f"Supervisor did not drain in {name}")
                if hidden and not reopen and ("DRAINED passes=0" not in messages
                        or any(e["event"] == "show" for e in observer.events)):
                    raise RuntimeError("The never-shown process created a window or rendered a frame")
                return {"case": name, "steps": actions, "events": observer.events, "application": messages}
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                if observer is not None:
                    observer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path, help="new evidence directory on the disposable host")
    parser.add_argument("--isolated-vm", action="store_true", help="confirm a dedicated synthetic desktop")
    parser.add_argument("--input-only", action="store_true", help="exercise UI Automation and foreground keyboard input")
    parser.add_argument("--speech-cues", type=Path, help="wait for observed NVDA announcements in a private fixture")
    parser.add_argument("--device-recovery", action="store_true", help="exercise the fixture's own DX12 device and replacement")
    args = parser.parse_args()
    if os.name != "nt" or not (args.isolated_vm or os.getenv("RUNNER_ENVIRONMENT") == "github-hosted"):
        parser.error("A disposable native Windows GUI test host is required")
    binary = args.binary.resolve(strict=True)
    if args.speech_cues and (not args.input_only or not args.speech_cues.is_dir()):
        parser.error("the private speech observer requires the keyboard scenario")
    if args.device_recovery and args.input_only:
        parser.error("choose the keyboard or rendering scenario")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"source": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "host": platform.platform(), "machine": platform.machine(),
              "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "trayInput": "synthetic inherited pipe", "compilerRequested": "Fxc",
              "cases": []}
    cases = [("absent-tray", True, False, True), ("background-quit", True, True, False),
             ("background-activate", True, True, True), ("foreground", False, True, True)]
    if args.input_only or args.device_recovery:
        case_name = "keyboard-accessibility" if args.input_only else "dx12-recovery"
        cases = [(case_name, False, True, True)]
        driver = Path(__file__).with_name("observe-windows-input.ps1")
        report["inputObserverSha256"] = hashlib.sha256(driver.read_bytes()).hexdigest()
        selector = Path(__file__).with_name("windows_observer.py")
        report["observerHostSelectorSha256"] = hashlib.sha256(selector.read_bytes()).hexdigest()
    for case in cases:
        try:
            report["cases"].append(run_case(binary, output, *case, speech_cues=args.speech_cues))
        finally:
            (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{case[0]} passed", flush=True)


if __name__ == "__main__":
    main()
