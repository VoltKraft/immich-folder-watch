"""Manage private Windows observer profiles and select a capable system PowerShell."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


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
