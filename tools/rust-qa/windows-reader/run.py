"""Run a checksum-pinned, temporary portable NVDA against the owned Windows GUI fixture."""

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import http.client
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from speech import EXPECTED, LogTail, Speech


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERSION = "2026.3.1"
ASSET = f"nvda_{VERSION}.exe"
DIGEST = "6f80a5b0ca720a7d0d314b5be212f37388bbe81a1107ac3298c1821a1cd3f052"
SIZE = 69_896_584
URLS = (f"https://download.nvaccess.org/releases/{VERSION}/{ASSET}",
        f"https://github.com/nvaccess/nvda/releases/download/release-{VERSION}/{ASSET}")


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def acquire():
    cache = ROOT / "artifacts/rust/windows-reader/input"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / ASSET
    if path.exists():
        if path.stat().st_size != SIZE or sha(path) != DIGEST:
            raise ValueError("Cached NVDA differs from the official signed release")
        return path
    with tempfile.TemporaryDirectory(dir=cache) as staging:
        temp = Path(staging) / ASSET
        for url in URLS:
            try:
                with urllib.request.urlopen(url, timeout=60) as reader, temp.open("wb") as output:
                    total = 0
                    while chunk := reader.read(1 << 20):
                        total += len(chunk)
                        if total > SIZE:
                            raise ValueError("Unexpected NVDA download length")
                        output.write(chunk)
                break
            except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead):
                if url == URLS[-1]:
                    raise
        if total != SIZE or sha(temp) != DIGEST:
            raise ValueError("NVDA download differs from the published SHA-256")
        temp.replace(path)
    return path


def architecture(path):
    with path.open("rb") as file:
        if file.read(2) != b"MZ":
            raise ValueError("Expected a Windows executable")
        file.seek(60)
        file.seek(struct.unpack("<I", file.read(4))[0])
        if file.read(4) != b"PE\x00\x00":
            raise ValueError("Expected a PE signature")
        return {0x8664: "x64", 0xaa64: "arm64", 0x14c: "x86"}[struct.unpack("<H", file.read(2))[0]]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@contextmanager
def private_profile(report):
    directory = tempfile.TemporaryDirectory(prefix="ifw-reader-", dir=os.environ["RUNNER_TEMP"])
    try:
        yield Path(directory.name)
    finally:
        # NVDA's per-process accessibility helpers can outlive its main window briefly.
        prior_error = sys.exc_info()[0]
        deadline = time.monotonic() + 20
        while True:
            try:
                directory.cleanup()
                report["profileRemoved"] = True
                break
            except PermissionError as error:
                if time.monotonic() >= deadline:
                    report.update(profileRemoved=False, cleanupLockedFile=Path(error.filename or "").name)
                    if prior_error is None:
                        raise
                    break
                time.sleep(.25)


def close_reader(process):
    if process.poll() is not None:
        return "already exited"
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    hwnd = user.FindWindowW("wxWindowClassNR", "NVDA")
    owner = wintypes.DWORD()
    if hwnd and user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner)) and owner.value == process.pid:
        # The pinned release uses this window message for its own quit operation.
        if user.PostMessageW(hwnd, 0x0012, 0, 0):
            try:
                process.wait(timeout=20)
                return "owned reader window quit"
            except subprocess.TimeoutExpired:
                pass
    stop(process)
    return "owned child terminated"


def verified_edit(record, pass_key_announced):
    """Qualify the observed edit route independently of the input driver's exit."""
    filename = "Grüße – Sommer.jpg"
    edit = record["readerEdit"]
    route = edit["clearedBy"]
    states = edit["states"]
    ordinary = "ordinaryDelete"
    if route not in (ordinary, "nvdaPassThroughDelete") or pass_key_announced != (route != ordinary):
        raise ValueError("The reported Delete route disagrees with NVDA's speech")
    full_selections = ["selectedForCopy", "selectedForDelete"]
    if route != ordinary:
        full_selections += ["selectedForPassThrough", "afterPassAnnouncement"]
        if (states[ordinary]["document"], states[ordinary]["value"]) != (filename, filename):
            raise ValueError("The ordinary Delete outcome cannot be attributed to the restored original selection")
    for phase in full_selections:
        state = states[phase]
        if (state["value"], state["document"], state["selected"], state["selectionCount"],
                state["selectionStart"], state["selectionEnd"]) != (filename, filename, filename, 1, 0, len(filename)):
            raise ValueError(f"The entire actual filename was not selected at {phase}")
    empty = states[route]
    if (empty["value"], empty["document"], empty["valueLength"], empty["documentLength"],
            empty["documentCollapsed"]) != ("", "", 0, 0, True):
        raise ValueError("The field did not expose both empty text values and equal document endpoints")
    pasted = states["pasted"]
    if not record["clipboardCopied"] or not record["unicodeClipboardRoundTrip"] or (
            pasted["value"], pasted["document"], pasted["documentCollapsed"]) != (filename, filename, False):
        raise ValueError("The native clipboard did not restore the complete Unicode filename")
    return route


def assess(installer, binary, output, report):
    if os.name != "nt" or any(os.getenv(key) != value for key, value in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_REF": "refs/heads/rewrite/rust",
        "GITHUB_REPOSITORY": "VoltKraft/immich-folder-watch"}.items()):
        raise ValueError("A disposable Windows rewrite runner is required")
    with private_profile(report) as area:
        temp = str(area)
        config = area / "config"
        portable = area / "portable"
        cues = area / "cues"
        for folder in (config, cues, area / "tmp", area / "Local", area / "Roaming"):
            folder.mkdir()
        env = dict(os.environ, IFW_QA_ISOLATED="1", USERPROFILE=temp, HOME=temp, LOCALAPPDATA=str(area / "Local"),
                   APPDATA=str(area / "Roaming"), TEMP=str(area / "tmp"), TMP=str(area / "tmp"))
        report["lastStep"] = "create portable reader"
        subprocess.run([installer, "--create-portable-silent", f"--portable-path={portable}", "--minimal",
                        "--disable-addons", "--no-sr-flag", f"--config-path={config}"],
                       stdin=subprocess.DEVNULL, cwd=area, env=env, check=True, timeout=240)
        exe = portable / "nvda.exe"
        report.update(portableArchitecture=architecture(exe), portableSha256=sha(exe))
        report["lastStep"] = "check for existing reader"
        args = [exe, "--minimal", "--disable-addons", "--no-sr-flag", f"--config-path={config}"]
        check = subprocess.run([*args, "--check-running"], cwd=area, env=env, timeout=25, stdin=subprocess.DEVNULL)
        if check.returncode != 1:
            raise RuntimeError("The disposable desktop did not confirm the absence of an existing NVDA instance")
        (config / "nvda.ini").write_text("schemaVersion = 25\n[general]\nshowWelcomeDialogAtStartup = false\nplayStartAndExitSounds = false\n"
            "[update]\nautoCheck = false\nallowUsageStats = false\naskedAllowUsageStats = true\n"
            "[speech]\nsynth = espeak\n[keyboard]\nspeakTypedCharacters = 2\nspeakTypedWords = 0\n"
            "[remote]\nenabled = false\n[addonStore]\nautomaticUpdates = disabled\n", encoding="utf-8")
        raw_log = area / "speech.log"
        speech = Speech(cues)
        log = LogTail(raw_log, speech)
        report["lastStep"] = "start NVDA with private configuration"
        reader = subprocess.Popen([*args, "--lang=en", "--log-level=12", f"--log-file={raw_log}"], cwd=area,
                                  env=env, stdin=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline and reader.poll() is None:
                log.read()
                if log.synth in ("espeak", "oneCore") and log.initialized:
                    break
                time.sleep(.12)
            else:
                raise RuntimeError("Portable NVDA did not initialize a supported speech synthesizer")
            report["lastStep"] = "observe owned GUI and screen reader speech"
            test = subprocess.Popen([sys.executable, HERE.parent / "observe-windows-gui.py", binary, output / "gui",
                                     "--input-only", "--speech-cues", cues], stdin=subprocess.DEVNULL, cwd=ROOT)
            try:
                deadline = time.monotonic() + 185
                while time.monotonic() < deadline and test.poll() is None and reader.poll() is None:
                    log.read()
                    time.sleep(.06)
                log.read()
                report["inputDriverExit"] = test.poll()
                report["readerActiveAfterInput"] = reader.poll() is None
                if report["inputDriverExit"] != 0 or not report["readerActiveAfterInput"] or tuple(speech.observed) != EXPECTED:
                    raise RuntimeError("Reader, foreground driver or ordered speech criteria did not pass")
                record = json.loads((output / "gui" / "input.json").read_text(encoding="utf-8"))
                report["filenameClearedBy"] = verified_edit(record, speech.pass_key_announced)
            finally:
                stop(test)
        finally:
            report.update(announcements=speech.observed, utterancesExamined=speech.utterances,
                          orderedSpeechPassed=tuple(speech.observed) == EXPECTED,
                          passNextKeyAnnounced=speech.pass_key_announced,
                          synth=log.synth, readerInitialized=log.initialized, readerDiagnosticModules=log.diagnostics)
            if raw_log.is_file():
                report["privateLogSha256"] = sha(raw_log)
            report["readerShutdown"] = close_reader(reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire-only", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    installer = acquire()
    if args.acquire_only:
        print(f"NVDA {VERSION} release digest verified")
        return
    if not args.binary or not args.output:
        parser.error("supply --binary and --output for a native test")
    binary = args.binary.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"nvda": VERSION, "installerSha256": DIGEST, "guiArchitecture": architecture(binary),
              "guiSha256": sha(binary), "passed": False, "sourceSha256": {p.name: sha(p) for p in (
                  HERE / "run.py", HERE / "speech.py", HERE / "Keyboard.cs", HERE / "clipboard.ps1",
                  HERE.parent / "observe-windows-input.ps1",
                  HERE.parent / "observe-windows-gui.py", HERE.parent / "windows_observer.py")}}
    try:
        assess(installer, binary, output, report)
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
