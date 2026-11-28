"""Exercise the ordinary x64 window Quit on the private Server 2025 console."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
TARGET = "x86_64-pc-windows-msvc"
OUT = ROOT / "artifacts/rust/gui-native" / TARGET / "windows-quit-private"
sys.path.insert(0, str(QA / "windows-launcher"))
import local_tray
import window_quit as observer


def host_identity(launcher, desktop, name):
    if (os.name != "nt" or os.getenv("GITHUB_ACTIONS") or os.getenv("RUNNER_ENVIRONMENT")
            or socket.gethostname().casefold() != "ifw-qa25" or ctypes.windll.shell32.IsUserAnAdmin()):
        raise ValueError("Use the dedicated non-elevated Server 2025 x64 test console")
    ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    identity = json.loads(subprocess.check_output([
        ps, "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "@{user=[Security.Principal.WindowsIdentity]::GetCurrent().Name;"
        "vm=(Get-CimInstance Win32_ComputerSystem).HypervisorPresent} | ConvertTo-Json -Compress",
    ], encoding="utf-8"))
    if (identity["user"].casefold() != r"ifw-qa25\ifw-test" or identity["vm"] is not True
            or launcher.recorder.Win32().machine(-1) != (0x8664, 0x8664)
            or not launcher.ordinary_console(desktop.context(), name)):
        raise ValueError("Expected the standard QA user on its unlocked native x64 input desktop")
    return identity


def canonical_pair(archive, digest, head, directory):
    receipt, _ = local_tray.stage(archive, digest, directory)
    if receipt["revision"] != head:
        raise ValueError("The original tray compiler did not build the requested revision")
    folder = directory / "canonical"
    folder.mkdir()
    gui = folder / local_tray.GUI
    worker = directory / local_tray.WORKER
    key = "canonical/" + gui.name
    with ZipFile(archive) as kit, kit.open(key) as src, gui.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    images = {"gui": local_tray.file_sha(gui), "worker": local_tray.file_sha(worker)}
    if images != {"gui": receipt["files"][key], "worker": receipt["inventory"]["worker"]}:
        raise ValueError("Unexpected canonical GUI or inventory worker after staging")
    return gui, worker, images, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--head", required=True, help="full revision of the original compiler archive")
    parser.add_argument("--worker-desktop", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.head) or not re.fullmatch(r"[0-9a-f]{64}", args.archive_sha256):
        parser.error("Expected a full compiler revision and original Actions SHA-256")
    if args.worker_desktop and not re.fullmatch(r"IfwQa_[0-9a-f]{32}", args.worker_desktop):
        parser.error("Expected the generated private desktop name")
    if os.name != "nt" or os.getenv("GITHUB_ACTIONS") or os.getenv("RUNNER_ENVIRONMENT"):
        parser.error("Select the local Windows test VM")
    import observe as launcher
    native = runpy.run_path(str(QA / "windows-desktop/run.py"))
    desktop = native["Desktop"]()
    identity = host_identity(launcher, desktop, args.worker_desktop or "Default")
    archive = args.archive.resolve(strict=True)
    if local_tray.file_sha(archive) != args.archive_sha256:
        raise ValueError("The archive differs from the original Actions digest")
    result = {"verified": False, "host": identity, "source": args.head, "target": TARGET,
              "archiveSha256": args.archive_sha256,
              "observerRevision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    if args.worker_desktop:
        try:
            with tempfile.TemporaryDirectory(prefix="ifw-quit-") as directory:
                gui, worker, images, receipt = canonical_pair(archive, args.archive_sha256, args.head, Path(directory))
                if any(native["pe_machine"](p) != 0x8664 for p in (gui, worker)):
                    raise ValueError("Expected two native x64 PE images")
                result.update(compilerRun=receipt["run"], compilerAttempt=receipt["attempt"],
                              compilerReceipt=receipt["files"]["canonical/build.json"], images=images)
                observer.observe_window(args.worker_desktop, desktop, launcher, native, result,
                                        gui=gui, worker=worker, images=images, output=OUT,
                                        local_temp=Path(tempfile.gettempdir()))
            result["verified"] = True
        except Exception as error:
            result["error"] = str(error)
            raise
        finally:
            native["write"](OUT / "window-quit.json", result)
        return
    OUT.mkdir(parents=True, exist_ok=False)
    try:
        with native["named_input_desktop"](desktop, result) as name:
            worker_args = ["--archive", str(archive), "--archive-sha256", args.archive_sha256,
                           "--head", args.head, "--worker-desktop", name]
            native["run_worker"](Path(__file__).resolve(), worker_args, name, ROOT, result)
        result["returnedDesktop"] = desktop.context()
        if (result["workerExit"] or not result["jobClosed"] or result["cleanup"]["inputAfterRestore"] != "Default"
                or not native["ordinary_console"](result["returnedDesktop"], "Default")
                or result["returnedDesktop"]["session"] != result["beforeSwitch"]["session"]):
            raise RuntimeError("The worker or its return to the original input desktop failed")
        result["verified"] = True
    finally:
        native["write"](OUT / "session.json", result)


if __name__ == "__main__":
    main()
