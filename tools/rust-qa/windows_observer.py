"""Select a working system PowerShell and record its desktop observer capabilities."""

import os
import shutil
import subprocess
import time


def select_powershell(directory, capability):
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
                env={**os.environ, "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"},
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
