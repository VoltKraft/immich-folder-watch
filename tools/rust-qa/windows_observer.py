"""Manage private Windows observer profiles and select a capable system PowerShell."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def isolated_windows_vm(selected):
    """Allow the explicitly selected native VM mode outside an Actions job."""
    return selected and sys.platform == "win32" and os.getenv("GITHUB_ACTIONS") != "true"


def private_gui_environment(profile):
    """Give a desktop subject synthetic user directories and only its required Windows environment."""
    keys = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
            "COMMONPROGRAMW6432", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keys}
    env.update(USERPROFILE=str(profile), HOME=str(profile), TEMP=str(profile), TMP=str(profile),
               IFW_QA_ISOLATED="1", WGPU_DX12_COMPILER="Fxc", POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
    for key in ("APPDATA", "LOCALAPPDATA"):
        (profile / key).mkdir()
        env[key] = str(profile / key)
    return env


@contextmanager
def private_profile(parent, prefix, report):
    directory = tempfile.TemporaryDirectory(dir=parent, prefix=prefix)
    profile = Path(directory.name)
    report["profileRemoved"] = False
    observation_failed = False
    try:
        yield profile
    except BaseException:
        observation_failed = True
        raise
    finally:
        deadline = time.monotonic() + 20
        while True:
            try:
                directory.cleanup()
                try:
                    profile.lstat()
                except FileNotFoundError:
                    report["profileRemoved"] = True
                    break
                raise OSError("The private observer profile is still present after cleanup")
            except OSError as error:
                # A native text service or accessibility helper may briefly retain a directory or DLL.
                code = getattr(error, "winerror", None)
                if code in (5, 32, 33) and time.monotonic() < deadline:
                    time.sleep(.25)
                    continue
                report["profileCleanupError"] = {
                    "type": type(error).__name__, "winerror": code, "file": Path(error.filename or "").name,
                }
                if not observation_failed:
                    raise
                break


def select_powershell(directory, capability, env=None):
    check = {
        "shortcut": ("$shell=New-Object -ComObject WScript.Shell;"
                     "[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell);"),
        "accessibility": "Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms;",
    }[capability]
    probe = "$ErrorActionPreference='Stop';" + check + "[Console]::WriteLine($PSVersionTable.PSVersion.ToString())"
    attempts = []
    for name in ("powershell.exe", "pwsh.exe"):
        program = shutil.which(name)
        if not program:
            attempts.append({"host": name, "status": "missing"})
            continue
        start = time.monotonic()
        record = {"host": name}
        attempts.append(record)
        try:
            process = subprocess.run(
                [program, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-Command", probe],
                stdin=subprocess.DEVNULL, capture_output=True, cwd=directory, timeout=30,
                env={**(os.environ if env is None else env),
                     "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"},
            )
            record["status"] = process.returncode
            if not process.returncode:
                record["version"] = process.stdout.decode("utf-8-sig", errors="replace").strip()
                return program, attempts
            record["diagnostic"] = process.stderr.decode("utf-8-sig", errors="replace").strip()[-1024:]
        except (subprocess.TimeoutExpired, OSError) as error:
            record["status"] = type(error).__name__
        finally:
            record["seconds"] = round(time.monotonic() - start, 3)
    return None, attempts
