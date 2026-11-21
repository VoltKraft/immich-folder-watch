"""Observe one owned native GUI on the runner desktop or the newly created input desktop."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import traceback

from win32 import Desktop, GWL_EXSTYLE, WS_EX_TOPMOST, check, ordinary_console, same_name

HERE = Path(__file__).resolve().parent
QA = HERE.parent
sys.path.insert(0, str(QA))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hosted():
    return (os.name == "nt" and os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("RUNNER_OS") == "Windows" and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted")


def named_desktop(name):
    return re.fullmatch(r"IfwQa_[a-f0-9]{32}", name) is not None


def field_center(record, pid, hwnd):
    values = record["center"]
    if (record["processId"] != pid or record["hwnd"] != hwnd or record["name"] != "Dateiname"
            or len(values) != 2 or any(type(value) is not int for value in values)):
        raise ValueError("UIA field geometry does not match the current native window")
    return values


def input_passed(record, pid):
    return (record.get("processId") == pid and record.get("status") == "passed"
            and record.get("onInputDesktop") is True and record.get("foreground") is True
            and record.get("passwordProperty") is True and record.get("passwordCharactersTyped") == 3
            and record.get("englishLabels") == ["Filename", "Password"]
            and record.get("unicodeClipboardRoundTrip") is True)


def shared_windows():
    spec = importlib.util.spec_from_file_location("ifw_shared_windows_gui", QA / "observe-windows-gui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Windows


def powershell(program, script, args, private, cwd, logfile, timeout):
    cmd = [program, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
           "-File", str(script), *map(str, args)]
    with logfile.open("wb") as log:
        return subprocess.run(cmd, cwd=cwd, env=private, stdin=subprocess.DEVNULL, stdout=log,
                              stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
                              timeout=timeout, check=False).returncode


def observe(api, args, result, subject, host, observer, private, profile):
    result["subjectPid"] = subject.pid
    subject.stdin.write(b"T")
    subject.stdin.flush()
    log = args.output / "subject.log"
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if subject.poll() is not None:
            raise RuntimeError("Fixture exited before its DX12 window appeared")
        hwnd = observer.visible()
        if hwnd and "ADAPTER Dx12 " in log.read_text(encoding="utf-8", errors="replace"):
            break
        time.sleep(.04)
    else:
        raise TimeoutError("Waiting for the owned DX12 window")
    snap = api.observed(hwnd, subject.pid)
    result["opened"] = snap
    if (not same_name(snap["subject"]["threadDesktop"], args.desktop)
            or snap["subject"]["session"] != result["context"]["session"]):
        raise RuntimeError("The subject did not inherit the requested native desktop/session")
    field = args.output / "field.json"
    owner_args = ["-SubjectId", subject.pid, "-WindowHandle", hwnd]
    code = powershell(host, HERE / "field.ps1", [*owner_args, "-OutputFile", field], private,
                      profile, args.output / "field.log", 55)
    if code:
        raise RuntimeError(f"UIA geometry observer exited {code}")
    center = field_center(json.loads(field.read_text(encoding="utf-8")), subject.pid, hwnd)
    result["before"] = api.observed(hwnd, subject.pid, center)
    if args.desktop == "Default":
        # Never click or type on Default. This reproduces only the earlier nonactivating raise.
        if ordinary_console(api.context(), args.desktop) and not (api.style(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST):
            result["raisedOwnWindow"] = api.order_subject(hwnd, subject.pid, True)
            if result["raisedOwnWindow"] is True:
                try:
                    time.sleep(.18)
                    result["raised"] = api.observed(hwnd, subject.pid, center)
                finally:
                    result["restoredZOrder"] = api.order_subject(hwnd, subject.pid, False)
                    if result["restoredZOrder"] is not True:
                        raise RuntimeError("Could not restore the subject's own Z order")
        result["status"] = "observed"
        return
    result["beforeInputContext"] = api.context()
    if not ordinary_console(result["beforeInputContext"], args.desktop):
        raise RuntimeError("The named desktop no longer owns the unlocked runner console")
    inp = args.output / "input.json"
    code = powershell(host, QA / "observe-windows-input.ps1",
                      [*owner_args, "-SubjectLog", log, "-OutputFile", inp], private,
                      profile, args.output / "input.log", 100)
    result["inputExit"] = code
    result["afterInputContext"] = api.context()
    result["after"] = api.observed(hwnd, subject.pid, center)
    if code or not inp.is_file() or not input_passed(json.loads(inp.read_text(encoding="utf-8-sig")), subject.pid):
        raise RuntimeError("The guarded native keyboard and UIA checks did not pass")
    if not ordinary_console(result["afterInputContext"], args.desktop):
        raise RuntimeError("The runner console changed during the named input trial")
    result["status"] = "passed"


def trial(api, args, result):
    result["context"] = api.context()
    result["initialWindows"] = api.surroundings()
    if (not same_name(result["context"]["threadDesktop"], args.desktop)
            or not same_name(result["context"]["windowStation"], "WinSta0")):
        raise RuntimeError("Worker was assigned a different native desktop")
    if args.desktop != "Default" and not ordinary_console(result["context"], args.desktop):
        raise RuntimeError("Named worker is outside the active unlocked console")
    # UIA reports physical screen coordinates. Match that coordinate system for all hit tests.
    check(api.awareness(-4), "SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)")
    observer_type = shared_windows()
    with tempfile.TemporaryDirectory(prefix="profile-", dir=args.output) as scratch:
        profile = Path(scratch)
        private = {**os.environ, "HOME": scratch, "USERPROFILE": scratch, "TMP": scratch, "TEMP": scratch,
                   "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc"}
        for key in ("APPDATA", "LOCALAPPDATA"):
            folder = profile / key
            folder.mkdir()
            private[key] = str(folder)
        # Select in the supervisor before switching desktops so host capability probes cannot steal focus.
        # A fully qualified selected system host is passed to both read-only and input observers.
        host = args.powershell
        with (args.output / "subject.log").open("wb") as stream, subprocess.Popen(
                [args.binary], cwd=profile, env=private, stdin=subprocess.PIPE, stdout=stream,
                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW) as subject:
            observer = None
            try:
                observer = observer_type(subject.pid)
                observe(api, args, result, subject, host, observer, private, profile)
            finally:
                try:
                    if subject.poll() is None:
                        try:
                            subject.stdin.write(b"Q")
                            subject.stdin.flush()
                            subject.wait(timeout=8)
                        except (OSError, subprocess.TimeoutExpired):
                            subject.kill()
                            subject.wait(timeout=5)
                    result["subjectExit"] = subject.returncode
                finally:
                    if observer:
                        observer.close()
        if result["subjectExit"] != 0 or "DRAINED passes=" not in (args.output / "subject.log").read_text(
                encoding="utf-8", errors="replace"):
            raise RuntimeError("Subject did not drain cleanly")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("desktop")
    parser.add_argument("powershell", type=Path)
    args = parser.parse_args()
    if not hosted() or not (args.desktop == "Default" or named_desktop(args.desktop)):
        parser.error("Use the disposable GitHub-hosted desktop launcher")
    if args.powershell.name.lower() not in ("powershell.exe", "pwsh.exe"):
        parser.error("A system PowerShell observer is required")
    result = {"requestedDesktop": args.desktop}
    try:
        trial(Desktop(), args, result)
    except Exception:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
    finally:
        write(args.output / "observation.json", result)
    return 0 if result["status"] in ("observed", "passed") else 1


if __name__ == "__main__":
    sys.exit(main())
