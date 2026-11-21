"""Qualify foreground keyboard input on a fresh desktop of a disposable GitHub Windows runner."""

import argparse
from contextlib import contextmanager
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile
import time
import traceback
import uuid

from job import run_worker
from win32 import Desktop, READ_OBJECTS, SWITCH_DESKTOP, check, ordinary_console, same_name, unlocked_console
from worker import HERE, QA, hosted, write
from windows_observer import select_powershell

ROOT = QA.parents[1]
GUI_BINARY = ROOT / "artifacts/rust/gui-build/release/native-gui-assessment.exe"
TARGET = {"ARM64": ("aarch64-pc-windows-msvc", 0xaa64), "X64": ("x86_64-pc-windows-msvc", 0x8664)}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pe_machine(path):
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Expected a PE executable")
        stream.seek(60)
        offset, = struct.unpack("<I", stream.read(4))
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise ValueError("Invalid PE signature")
        return struct.unpack("<H", stream.read(2))[0]


def trial(report, api, binary, directory, name, host):
    directory.mkdir()
    record = {"requestedDesktop": name}
    report[directory.name] = record
    try:
        run_worker(HERE / "worker.py", [binary, directory, name, host], name, ROOT, record)
        observation = json.loads((directory / "observation.json").read_text(encoding="utf-8"))
        record["status"] = observation["status"]
        if "error" in observation:
            record["error"] = observation["error"].splitlines()[-1]
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        record["status"], record["error"] = "failed", str(error)
    record["inputAfterWorker"] = api.input_name()


def switch_back(api, saved, name, evidence):
    state = api.context()
    evidence["beforeRestore"] = state
    current = state["inputDesktop"]
    evidence["inputBeforeRestore"] = current
    if same_name(current, name):
        if not unlocked_console(state) or not same_name(state["threadDesktop"], "Default"):
            raise RuntimeError("The runner session changed before restoration")
        c.set_last_error(0)
        check(api.switch(saved), "SwitchDesktop(original)")
        evidence["switchBack"] = True
    elif not same_name(current, "Default"):
        raise RuntimeError("The active desktop changed independently and could not be identified as the fixture")
    evidence["inputAfterRestore"] = api.input_name()
    if not same_name(evidence["inputAfterRestore"], "Default"):
        raise RuntimeError("Restoring the original input desktop could not be verified")


@contextmanager
def named_input_desktop(api, report):
    report["beforeSwitch"] = api.context()
    if not ordinary_console(report["beforeSwitch"], "Default"):
        raise RuntimeError("The runner did not report an active unlocked WinSta0 Default input desktop")
    saved = check(api.open_named("Default", 0, False, READ_OBJECTS | SWITCH_DESKTOP), "OpenDesktopW(Default)")
    name = "IfwQa_" + uuid.uuid4().hex
    cleanup = report["cleanup"] = {}
    try:
        named = api.create_detached(name)
        try:
            report["created"] = {"requested": name, "actual": api.name(named),
                                 "supervisorDesktop": api.name(api.thread_desktop(api.thread()))}
            if (not same_name(report["created"]["actual"], name)
                    or not ordinary_console(api.context(), "Default")):
                raise RuntimeError("Desktop assignment or original console changed before the switch")
            try:
                c.set_last_error(0)
                check(api.switch(named), "SwitchDesktop(new fixture)")
                report["switchToFixture"] = True
                # A switched supervisor stays on Default; the named child independently checks its own thread.
                until = time.monotonic() + 5
                while not same_name(api.input_name(), name) and time.monotonic() < until:
                    time.sleep(.05)
                report["afterSwitch"] = api.context()
                if not same_name(report["afterSwitch"]["inputDesktop"], name):
                    raise RuntimeError("The new input desktop was not selected")
                yield name
            finally:
                switch_back(api, saved, name, cleanup)
        finally:
            cleanup["namedClosed"] = bool(api.close(named))
            if not cleanup["namedClosed"]:
                check(False, "CloseDesktop(named)")
    finally:
        cleanup["originalHandleClosed"] = bool(api.close(saved))
        if not cleanup["originalHandleClosed"]:
            check(False, "CloseDesktop(original)")


def desktop_trial(api, binary, output, host, report):
    with named_input_desktop(api, report) as name:
        trial(report, api, binary, output / "named", name, host)


def execute(args, target, report):
    api = Desktop()
    report["runner"] = api.context()
    report["initialWindows"] = api.surroundings()
    report["launcherParent"] = {"pid": os.getppid(), "executable": api.process_name(os.getppid())}
    report["fixtureMachine"] = hex(pe_machine(args.binary))
    if pe_machine(args.binary) != target[1]:
        raise RuntimeError("Fixture PE machine differs from the native Windows runner architecture")
    if (not same_name(report["runner"]["windowStation"], "WinSta0")
            or not same_name(report["runner"]["threadDesktop"], "Default")):
        raise RuntimeError("The hosted runner process is outside WinSta0 Default")
    with tempfile.TemporaryDirectory(prefix="observer-", dir=args.output) as private:
        host, attempts = select_powershell(private, "accessibility")
    report["observerHosts"] = attempts
    if not host:
        raise RuntimeError("A system PowerShell with native UI Automation could not start")
    trial(report, api, args.binary, args.output / "original", "Default", host)
    desktop_trial(api, args.binary, args.output, host, report)
    if (report["original"].get("status") != "observed" or report["original"].get("workerExit") != 0
            or report["named"].get("status") != "passed" or report["named"].get("workerExit") != 0):
        raise RuntimeError("The original desktop observation or isolated native foreground keyboard trial failed")
    report["status"] = "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    arch = os.environ.get("RUNNER_ARCH")
    if not hosted() or arch not in TARGET:
        parser.error("This test requires a disposable GitHub-hosted Windows x64 or ARM64 runner")
    target = TARGET[arch]
    args.binary, args.output = args.binary.resolve(strict=True), args.output.resolve()
    expected = ROOT / "artifacts/rust/gui-native" / target[0] / "windows-desktop"
    if args.binary != GUI_BINARY.resolve() or args.output != expected.resolve():
        parser.error("Use the assessment binary and the target's new windows-desktop evidence directory")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
              "attempt": os.getenv("GITHUB_RUN_ATTEMPT"), "host": platform.platform(),
              "runnerArch": arch, "pythonMachine": hex(pe_machine(Path(sys.executable))),
              "binarySha256": digest(args.binary)}
    sources = [*sorted(HERE.glob("*.py")), HERE / "field.ps1", QA / "observe-windows-gui.py",
               QA / "observe-windows-input.ps1", QA / "windows_observer.py"]
    report["inputs"] = {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    try:
        execute(args, target, report)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        write(args.output / "results.json", report)
        files = sorted(p for p in args.output.rglob("*") if p.is_file())
        (args.output / "evidence.sha256").write_text("".join(
            f"{digest(p)}  {p.relative_to(args.output).as_posix()}\n" for p in files), encoding="utf-8")
    if report["status"] != "passed":
        print(report.get("error", "The named desktop input check failed"), file=sys.stderr)
        return 1
    print("The fixture owned foreground input on its named desktop. The original desktop was restored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
