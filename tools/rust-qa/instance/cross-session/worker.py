"""Fixed original-session or S4U participant for the synthetic native writer."""

import base64
import ctypes as c
from ctypes import wintypes as w
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import console_levels
from fixture import Accounts, HERE, HOSTED, bind, checked, guard_id, instance, read, release, subject_env, validate_area, wait, write
from standard import AMBIENT, EXISTING, STANDARD, fixed_writer, qualifies, required_authority


PHASES = {"original": (("original-hold", True), ("original-refuse", False), ("original-last", True)),
          "scheduled": (("scheduled-refuse", False), ("scheduled-hold", True))}


def level_inventory(returncode, output):
    # The system utility may emit a localized description in an OEM code page or UTF-16.
    numbers = re.findall(rb"(?<![0-9a-f])0x([0-9a-f]{1,8})(?![0-9a-f])", output.replace(b"\0", b"").lower())
    codes = sorted({int(value, 16) for value in numbers})
    return {"levelQueryExit": returncode, "levelQueryBytes": len(output),
            "levelQuerySha256": hashlib.sha256(output).hexdigest(), "levelCodes": [hex(code) for code in codes],
            "levelListed": returncode == 0 and 0x20000 in codes}


def launch_output(output):
    """Preserve what the fixed launcher wrote to its combined output pipe."""
    prefix = output[:4096]
    return {"bytes": len(output), "sha256": hashlib.sha256(output).hexdigest(),
            "prefixBase64": base64.b64encode(prefix).decode("ascii"), "truncated": len(prefix) < len(output)}


def observe_levels(report, redirected, console_probe):
    """Keep both native observations. Retry only a successful, empty pipe."""
    report.update(level_inventory(redirected.returncode, redirected.stdout))
    if report["levelListed"]:
        report["levelSource"] = "redirected-query"
        return True
    if redirected.returncode or redirected.stdout:
        return False
    console = console_probe()
    if len(console.stdout) > console_levels.MAX_CELLS * 2 or len(console.stdout) % 2:
        raise ValueError("Invalid private console evidence size")
    second = level_inventory(console.returncode, console.stdout)
    second["screenUtf16LeBase64"] = base64.b64encode(console.stdout).decode("ascii")
    second["diagnostic"] = console.stderr.decode("utf-8", errors="replace")[:1024]
    report["privateConsoleQuery"] = second
    if second["levelListed"]:
        report["levelSource"] = "private-console-query"
    return second["levelListed"]


def console_probe(area, role):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return subprocess.run([sys.executable, "-I", "-B", str(HERE / "worker.py"), "--console-levels", role, str(area)],
                          cwd=area, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup, close_fds=True, timeout=20)


def own_identity(area, role):
    if (area / "abort").exists():
        raise RuntimeError("The private writer exercise has stopped")
    config = read(area / "controller.json")
    accounts = Accounts()
    sid, image, identity = accounts.identify(os.getpid())
    if (time.time() > config["expires"] or role not in PHASES or config["hosted"] != HOSTED or identity["sidSha256"] != config["controller"]["sidSha256"]
            or (identity["sessionId"] == config["controller"]["sessionId"]) != (role == "original")
            or image.resolve() != Path(sys.executable).resolve() or instance.sha(image) != config["pythonSha256"]
            or instance.sha(HERE / "worker.py") != config["workerSha256"]
            or guard_id(area / "profile") != config["guard"]):
        raise RuntimeError("The participant account, native session, Python image, script or guard differs")
    return config, accounts, sid, identity


def participant(area, role):
    config, accounts, sid, identity = own_identity(area, role)
    write(area / (role + "-attempt.json"), identity)
    parent = read(area / (role + "-bootstrap.json"))
    if (config["mode"] == AMBIENT and identity != parent) or not required_authority(config["mode"], identity, parent):
        raise RuntimeError("The actual participant does not have the required authority for this trial")
    env = subject_env(area, config["hosted"])
    result = {"passed": False, "worker": identity}
    try:
        write(area / (role + "-ready.json"), {"worker": identity, "guard": config["guard"]})
        for name, hold in PHASES[role]:
            wait(area, name + "-launch.json", timeout=60)
            with fixed_writer(area, accounts, sid, identity, env, config) as (child, receipt):
                write(area / (name + "-created.json"), receipt)
                wait(area, name + "-verified.json")
                child.resume()
                child.expect("WRITER_HELD" if hold else "WRITER_BUSY")
                if hold:
                    write(area / (name + "-held.json"), receipt)
                    wait(area, name + "-release.json")
                    release(child)
                else:
                    child.success()
                write(area / (name + "-finished.json"),
                      {"event": "WRITER_RELEASED" if hold else "WRITER_BUSY", "exitCode": child.proc.returncode,
                       "pid": receipt["pid"], "created100ns": receipt["created100ns"], "guard": guard_id(area / "profile")})
        result["passed"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        write(area / (role + "-done.json"), result)
    return result["passed"]


def system_runas():
    kernel = c.WinDLL("kernel32", use_last_error=True)
    system_directory = bind(kernel, "GetSystemDirectoryW", w.UINT, w.LPWSTR, w.UINT)
    folder = c.create_unicode_buffer(32768)
    n = checked(system_directory(folder, len(folder)), "GetSystemDirectoryW")
    if n >= len(folder):
        raise RuntimeError("Invalid system directory length")
    return Path(folder.value) / "runas.exe"


def basic_user(area, role, config):
    # Use only Windows' installed utility and the fixed, hashed Python/script pair.
    runas = system_runas()
    report = {"launcherSha256": instance.sha(runas), "level": "0x20000", "launched": False}
    try:
        # No service is started or reconfigured. A dormant Secondary Logon prerequisite is reported.
        adv = c.WinDLL("advapi32", use_last_error=True)
        scm_open = bind(adv, "OpenSCManagerW", w.HANDLE, w.LPCWSTR, w.LPCWSTR, w.DWORD)
        svc_open = bind(adv, "OpenServiceW", w.HANDLE, w.HANDLE, w.LPCWSTR, w.DWORD)
        query = bind(adv, "QueryServiceStatus", w.BOOL, w.HANDLE, c.c_void_p)
        close = bind(adv, "CloseServiceHandle", w.BOOL, w.HANDLE)
        manager = checked(scm_open(None, None, 1), "OpenSCManagerW(query)")
        try:
            service = checked(svc_open(manager, "seclogon", 4), "OpenServiceW(query)")
            try:
                status = (w.DWORD * 7)()
                checked(query(service, status), "QueryServiceStatus")
                report["secondaryLogonRunning"] = status[1] == 4
            finally:
                close(service)
        finally:
            close(manager)
        if not report["secondaryLogonRunning"]:
            raise RuntimeError("Secondary Logon is unavailable for an existing Basic User launch")
        options = dict(cwd=area, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       creationflags=0x08000000, timeout=15)
        levels = subprocess.run([runas, "/showtrustlevels"], **options)
        if not observe_levels(report, levels, lambda: console_probe(area, role)):
            raise RuntimeError("The Windows trust-level query did not confirm the Basic User prerequisite")
        command = subprocess.list2cmdline([sys.executable, "-I", "-B", str(HERE / "worker.py"), "--participant", role, str(area)])
        if instance.sha(Path(sys.executable)) != config["pythonSha256"] or instance.sha(HERE / "worker.py") != config["workerSha256"]:
            raise RuntimeError("The fixed participant changed before Basic User launch")
        launch = subprocess.run([runas, "/noprofile", "/trustlevel:0x20000", command], **options)
        report["launchExit"] = launch.returncode
        report["launchOutput"] = launch_output(launch.stdout)
        report["launched"] = launch.returncode == 0
        if not report["launched"]:
            raise RuntimeError("Windows refused the fixed Basic User action")
    finally:
        write(area / (role + "-basic-user.json"), report)


def run(area, result, role="scheduled"):
    config, _, _, identity = own_identity(area, role)
    result["bootstrap"] = identity
    write(area / (role + "-bootstrap.json"), identity)
    if config["mode"] == AMBIENT:
        result["mode"] = "unchanged-bootstrap-authority"
        result["passed"] = participant(area, role)
    elif config["mode"] not in (STANDARD, EXISTING):
        raise RuntimeError("Unknown fixed participant mode")
    elif qualifies(identity):
        result["mode"] = "inherited-standard-user"
        result["passed"] = participant(area, role)
    elif config["mode"] == EXISTING:
        raise RuntimeError("Both pre-existing sessions must already have standard-user authority")
    else:
        result["mode"] = "windows-basic-user"
        basic_user(area, role, config)
        result["passed"] = bool(wait(area, role + "-done.json", timeout=145)["passed"])


def main():
    if os.name != "nt":
        raise SystemExit("A marked native Windows session is required")
    argv = sys.argv[1:]
    actor = len(argv) == 3 and argv[0] == "--participant" and argv[1] in PHASES
    console = len(argv) == 3 and argv[0] == "--console-levels" and argv[1] in PHASES
    original = len(argv) == 2 and argv[0] == "--original"
    if not (actor or console or original or len(argv) == 1):
        raise SystemExit("Expected a fixed synthetic writer role")
    area = Path(argv[-1]).resolve(strict=True)
    validate_area(area)
    role = argv[1] if actor or console else "original" if original else "scheduled"
    if console:
        try:
            config, _, _, _ = own_identity(area, role)
            if (config["mode"] != STANDARD or sys.stdout.isatty()
                    or instance.sha(HERE / "console_levels.py") != config["consoleLevelsSha256"]):
                raise RuntimeError("The private query requires the identified hosted standard-user trial")
            status, raw = console_levels.query(system_runas(), area)
            sys.stdout.buffer.write(raw)
            return status
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    result = {"passed": False}
    if actor:
        try:
            return 0 if participant(area, role) else 1
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            write(area / (role + "-done.json"), result)
            return 1
    try:
        run(area, result, role)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        write(area / ("worker-done.json" if role == "scheduled" else "original-bootstrap-done.json"), result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
