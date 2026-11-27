"""Observe a real system IME composing and committing in the normal Rust filename field."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
sys.path.insert(0, str(QA / "windows-desktop"))
from win32 import Desktop, check, ordinary_console, same_name
from worker import shared_windows
from windows_observer import private_profile, select_powershell

KEYBOARD_CATEGORY = "34745c63-b2f0-4784-8b67-5e12c8701a31"
FIELD_SOURCES = (QA / "gui/src/main.rs", QA / "gui/src/lib.rs")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def native_target():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    probe = kernel.IsWow64Process2
    probe.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16)]
    probe.restype = ctypes.c_int
    emulated, native = ctypes.c_uint16(), ctypes.c_uint16()
    if not probe(-1, ctypes.byref(emulated), ctypes.byref(native)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {0x8664: "x86_64-pc-windows-msvc", 0xaa64: "aarch64-pc-windows-msvc"}[native.value], native.value


def checked_build(binary, path, target, machine, expected_source):
    receipt = read(path)
    with binary.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Expected a native Windows GUI executable")
        stream.seek(60)
        offset, = struct.unpack("<I", stream.read(4))
        stream.seek(offset)
        signature, image_machine = struct.unpack("<4sH", stream.read(6))
    if (signature != b"PE\0\0" or image_machine != machine or receipt["target"] != target
            or receipt["binarySha256"] != digest(binary)
            or any(receipt["compilerSources"].get(p.relative_to(ROOT).as_posix()) != digest(p) for p in FIELD_SOURCES)
            or (expected_source and receipt["source"] != expected_source)):
        raise ValueError("The GUI build receipt, native target or observed Rust field source differs")
    return {"target": target, "sha256": digest(path), "source": receipt["source"]}


def eligibility(inventory):
    layouts = [row for row in inventory["layouts"] if row["language"] == 0x411]
    if not layouts:
        return "no loaded Japanese input locale"
    if any(row["immIme"] for row in layouts):
        return None
    if not inventory.get("enumeratedTsf"):
        return "could not enumerate Japanese TSF input profiles"
    if not any(row.get("language") == 0x411 and row["category"].lower() == KEYBOARD_CATEGORY
               and row["enabled"] and row["type"] == 1
               for row in inventory.get("profiles", [])):
        return "no enabled Japanese TSF keyboard service or loaded IMM IME"
    return None


def accepted(data, pid, hwnd):
    field = data.get("fieldAfterLayout", {})
    return (data.get("status") == "passed" and data.get("subjectId") == pid
            and data.get("windowHandle") == hwnd and field.get("state") == "observed"
            and field.get("lastObservation") == "focused-filename-read" and field.get("attempts", 0) > 0
            and data.get("selectedLayout", 0) & 0xffff == 0x411
            and data.get("preeditBeforeEnter") is True and data.get("commitAfterEnter") is True
            and data.get("normalFilenameConfirmed") is True and data.get("committedCodePoint") == "U+3042"
            and data.get("restoredLayout") == data.get("originalLayout") and bool(data.get("restoredLayout")))


def launch_ps(host, mode, output, env, extra=(), sample_pipe=None):
    cmd = [host, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta",
           "-File", HERE / "observe.ps1", "-Mode", mode, "-OutputFile", output / (mode + ".json"), *map(str, extra)]
    with (output / (mode + ".log")).open("wb") as log:
        options = dict(cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=log,
                       stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        if sample_pipe is None:
            return subprocess.run(cmd, **options, timeout=115, check=False).returncode
        # Extend the existing fixture control pipe only to the trusted composition observer.
        # The temporary inheritable duplicate closes in this process immediately after launch.
        import msvcrt
        with os.fdopen(os.dup(sample_pipe.fileno()), "wb", buffering=0) as duplicate:
            handle = msvcrt.get_osfhandle(duplicate.fileno())
            os.set_handle_inheritable(handle, True)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [handle]}
            process = subprocess.Popen([*cmd, "-SamplePipe", str(handle)], **options, close_fds=True, startupinfo=startup)
        with process:
            try:
                return process.wait(timeout=115)
            finally:
                if process.poll() is None:
                    process.kill()


def subject(args, api, env, host, result):
    native_windows = shared_windows()
    context = api.context()
    result["beforeInput"] = context
    if not isinstance(context["threadDesktop"], str) or not ordinary_console(context, context["threadDesktop"]):
        raise RuntimeError("The disposable worker is outside an active unlocked native input desktop")
    log = args.output / "subject.log"
    with log.open("wb") as stream, subprocess.Popen(
            [args.binary], cwd=args.output, env={**env, "IFW_QA_FILENAME_IME": "1"}, stdin=subprocess.PIPE, stdout=stream,
            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW) as child:
        observer = None
        try:
            desktop = check(api.thread_desktop(api.thread()), "GetThreadDesktop")
            observer = native_windows(child.pid, desktop)
            child.stdin.write(b"T")
            child.stdin.flush()
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                hwnd = observer.visible(waiting_for_first=True)
                if hwnd and "ADAPTER Dx12 " in log.read_text(encoding="utf-8", errors="replace"):
                    break
                if child.poll() is not None:
                    raise RuntimeError("The GUI exited before presenting its native window")
                time.sleep(.04)
            else:
                raise TimeoutError("Waiting for the owned DX12 window")
            info = api.observed(hwnd, child.pid)
            result["window"] = info["subject"]
            if (not same_name(info["subject"]["threadDesktop"], context["threadDesktop"])
                    or info["subject"]["session"] != context["session"]):
                raise RuntimeError("The subject and observer do not share the active desktop and OS session")
            exit_code = launch_ps(host, "compose", args.output, env,
                                  ["-SubjectId", child.pid, "-WindowHandle", hwnd, "-SubjectLog", log], child.stdin)
            result["observerExit"] = exit_code
            result["afterInput"] = api.context()
            compose = read(args.output / "compose.json")
            if exit_code or not accepted(compose, child.pid, hwnd):
                detail = compose.get("restoreError") or compose.get("error") or "missing evidence"
                raise RuntimeError(f"The native composition and normal filename evidence did not pass: {detail}")
            if not ordinary_console(result["afterInput"], context["threadDesktop"]):
                raise RuntimeError("The active input desktop changed before completion")
        finally:
            try:
                if child.poll() is None:
                    try:
                        child.stdin.write(b"Q")
                        child.stdin.flush()
                        child.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        child.kill()
                        child.wait(timeout=8)
                result["subjectExit"] = child.returncode
            finally:
                if observer:
                    observer.close()
    if result["subjectExit"] or "DRAINED passes=" not in log.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError("The native fixture did not drain cleanly")


def run(args, result):
    api = Desktop()
    result["desktop"] = api.context()
    desktop = result["desktop"]["threadDesktop"]
    result["hasActiveInputDesktop"] = isinstance(desktop, str) and ordinary_console(result["desktop"], desktop)
    with private_profile(args.output, "ime-profile-", result) as private:
        scratch = str(private)
        env = {**os.environ, "USERPROFILE": scratch, "HOME": scratch, "TMP": scratch, "TEMP": scratch,
               "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc",
               "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}
        for key in ("APPDATA", "LOCALAPPDATA"):
            folder = private / key
            folder.mkdir()
            env[key] = str(folder)
        host, attempts = select_powershell(args.output, "accessibility", env=env)
        result["observerHosts"] = attempts
        if not host:
            raise RuntimeError("A local PowerShell with UI Automation is required")
        if launch_ps(host, "inventory", args.output, env):
            raise RuntimeError("System IME inventory did not complete")
        inventory = read(args.output / "inventory.json")
        if inventory["status"] != "observed":
            raise RuntimeError("System IME inventory is incomplete")
        result["prerequisite"] = eligibility(inventory)
        if args.inventory_only:
            outcome = "inventory-only"
        elif result["prerequisite"]:
            outcome = "unavailable"
        else:
            target, machine = native_target()
            receipt = args.build_receipt or ROOT / "artifacts/rust/gui-native" / target / "build.json"
            result["guiBuild"] = checked_build(args.binary, receipt, target, machine, os.getenv("GITHUB_SHA"))
            subject(args, api, env, host, result)
            result["compositionObserved"] = True
            outcome = "passed"
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--isolated-vm", action="store_true", help="use an explicitly authorized disposable Windows test VM")
    parser.add_argument("--build-receipt", type=Path, help="the matching native GUI build.json in an isolated test VM")
    parser.add_argument("--inventory-only", action="store_true", help="read actual installed support without sending input")
    args = parser.parse_args()
    hosted = all(os.getenv(k) == v for k, v in {
        "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "VoltKraft/immich-folder-watch", "GITHUB_REF": "refs/heads/rewrite/rust"}.items())
    if os.name != "nt" or not (hosted or args.isolated_vm):
        parser.error("A disposable native Windows runner or an expressly authorized test VM is required")
    args.binary, args.output = args.binary.resolve(strict=True), args.output.resolve()
    if args.binary.name.lower() != "native-gui-assessment.exe":
        parser.error("Use the development-only native GUI assessment binary")
    args.output.mkdir(parents=True, exist_ok=False)
    source = [*sorted(HERE.glob("*.py")), HERE / "observe.ps1", HERE / "hosted.ps1", HERE / "language-list.ps1",
              HERE / "test_language_list.ps1", HERE / "Ime.cs", HERE / "mode-sample.ps1", HERE / "test_mode_sample.ps1",
              HERE / "test_field_focus.ps1",
              QA / "windows-desktop/worker.py", QA / "windows-desktop/win32.py", QA / "windows_observer.py",
              QA / "observe-windows-gui.py", QA / "observe-windows-input.ps1", *FIELD_SOURCES]
    result = {"status": "failed", "source": os.getenv("GITHUB_SHA"), "run": os.getenv("GITHUB_RUN_ID"),
              "host": platform.platform(), "machine": platform.machine(), "binarySha256": digest(args.binary),
              "inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in source}}
    try:
        result["status"] = run(args, result)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        files = sorted(p for p in args.output.iterdir() if p.is_file())
        (args.output / "evidence.sha256").write_text("".join(
            f"{digest(p)}  {p.name}\n" for p in files), encoding="utf-8")
    print(result.get("error") or result.get("prerequisite") or result["status"])
    return 0 if result["status"] in ("passed", "inventory-only") else 1


if __name__ == "__main__":
    sys.exit(main())
