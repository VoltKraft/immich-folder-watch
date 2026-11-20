"""Build and observe native Windows Shell services on a disposable test profile."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def actual_startup():
    # Independent known-folder lookup; used only to validate the exact recovery
    # path of a test-owned shortcut after an interrupted native process.
    shell = ctypes.OleDLL("shell32")
    guid = ctypes.create_string_buffer(uuid.UUID("b97d20bb-f46a-4c97-ba10-5e3608430854").bytes_le)
    ptr = ctypes.c_void_p()
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(ptr))
    try:
        return Path(ctypes.wstring_at(ptr))
    finally:
        ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.ole32.CoTaskMemFree(ptr)


def recover(area, token, known):
    # Never touch any pre-existing startup entry. A reservation marker is made
    # only after create_new succeeds, and the name and saved bytes must match.
    cleaned = []
    for stage in (["private", "startup"] if known else ["private"]):
        marker = area / (stage + ".owned")
        if not marker.exists():
            continue
        path = Path(marker.read_text(encoding="utf-8"))
        expected = (actual_startup() if stage == "startup" else area / "Synthetic Startup") / f"IFW-RW02-{token}.lnk"
        if path != expected:
            raise ValueError("Recovery path differs from the test-owned reservation")
        if path.exists():
            saved = area / (stage + ".saved")
            data = path.read_bytes()
            if data and (not saved.is_file() or saved.read_bytes() != data):
                raise ValueError("The shortcut differs from the test-owned contents")
            path.unlink()
            cleaned.append(stage)
    return cleaned


def observe(stage, area, token, exe):
    command = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(HERE / "observe.ps1"), "-Stage", stage, "-Fixture", str(area),
               "-Token", token, "-Executable", str(exe)]
    try:
        proc = subprocess.run(command, cwd=area, capture_output=True, timeout=25)
        if proc.returncode:
            return {"error": "PowerShell observer failed", "exitCode": proc.returncode,
                    "diagnostic": proc.stderr.decode("utf-8", errors="replace")[-2048:]}
        return json.loads(proc.stdout.decode("utf-8-sig"))
    except (subprocess.TimeoutExpired, OSError, ValueError) as err:
        return {"error": type(err).__name__}


def read_native(file):
    metrics = {}
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, raw = line.partition("=")
        if not separator:
            continue
        if raw in ("true", "false"):
            metrics[key] = raw == "true"
        else:
            metrics[key] = int(raw)
    return metrics


def measure(exe, output, hosted, known):
    token = uuid.uuid4().hex
    observations = {}
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    area = temp_root / ("ifw-shell-" + token)
    area.mkdir()
    recovered = []
    try:
        (area / "synthetic.fixture").write_text(token, encoding="ascii")
        mode = "--github-hosted" if hosted else "--isolated-session"
        with (output / "native.txt").open("wb") as stream:
            proc = subprocess.Popen([exe, mode, area, token, "hosted-startup" if known else "private"],
                                    cwd=area, stdout=stream, stderr=stream)
            try:
                deadline = time.monotonic() + 150
                while proc.poll() is None and time.monotonic() < deadline:
                    for stage in ("private", "startup", "tray"):
                        if stage not in observations and (area / (stage + ".ready")).is_file():
                            observations[stage] = observe(stage, area, token, exe)
                            (area / (stage + ".observed")).touch()
                    time.sleep(0.06)
                if proc.poll() is None:
                    raise TimeoutError("Native Windows probe exceeded its deadline")
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=15)
    finally:
        try:
            recovered = recover(area, token, known)
        finally:
            write(output / "observer.json", {"stages": observations, "recoveredOwnedLinks": recovered})
        shutil.rmtree(area)
    native = read_native(output / "native.txt")
    failures = []
    checked = {}
    for label in (["private", "startup"] if known else ["private"]):
        observed = observations.get(label, {})
        fields = ("fileExists", "directoryMatches", "targetMatches", "argumentsMatch", "workingDirectoryMatches",
                  "descriptionMatches", "iconMatches")
        checked[label] = (all(observed.get(k) is True for k in fields) and
                          all(native.get(label + "." + k) is True for k in
                              ("target", "arguments", "working_directory", "description", "icon", "disabled")))
        if not checked[label]:
            failures.append(f"{label} shortcut did not pass both native and independent readback/cleanup")
    if proc.returncode or recovered or not native.get("tray.hidden_hwnd") or native.get("tray.callbacks.synthetic_open") != 1:
        failures.append("Native hidden-window, targeted callback or resource cleanup did not complete")
    if native.get("tray.callbacks.synthetic_taskbar_created") != 1:
        failures.append("The receiver did not process the controlled TaskbarCreated message")
    tray = observations.get("tray", {})
    if "error" in tray:
        failures.append("Windows accessibility observer did not execute successfully")
    acknowledged = native.get("tray.initial.add") is True
    required = ("tray.initial.version4", "tray.modify", "tray.controlled_remove", "tray.synthetic_taskbar_readd.add",
                "tray.synthetic_taskbar_readd.version4", "tray.remove")
    if acknowledged and not all(native.get(k) is True for k in required):
        failures.append("A registered native icon failed modification, re-registration or removal")
    return {
        "failedChecks": failures,
        "hiddenWindowAndControlledCallbacks": native.get("tray.hidden_hwnd") is True
                                             and native.get("tray.callbacks.synthetic_open") == 1
                                             and native.get("tray.callbacks.synthetic_taskbar_created") == 1,
        "privateShortcut": checked.get("private"),
        "knownStartupShortcut": checked.get("startup"),
        "privateDesktopHostAbsence": native.get("empty.completed") is True and native.get("empty.taskbar_present") is False
                                    and native.get("empty.fallback_required") is True,
        "privateDesktopFallbackWindowVisible": native.get("empty.fallback_visible") is True,
        "nativeTaskbarPresent": native.get("tray.taskbar_present") is True,
        "shellIconAcceptedAndRemoved": acknowledged and native.get("tray.remove") is True,
        "shellNotificationRequestAccepted": native.get("tray.notification_request") is True,
        "shellReportedBalloonShown": native.get("tray.callbacks.balloon_show", 0) > 0,
        "independentNotificationUiaElement": tray.get("notificationElementFound") is True,
        "trayAccessibleNameObserved": tray.get("trayElementFound") is True,
        "uiaInvokeSent": tray.get("invokeSent") is True,
        "nativeActivationCallbackObserved": native.get("tray.callbacks.shell_open", 0) > 0,
        "nativeTaskbarCreatedMessageObserved": native.get("tray.callbacks.taskbar_created", 0) > 0,
        "controlledShellMessageReregistration": native.get("tray.synthetic_taskbar_readd.add") is True,
        "shellAvailability": "acknowledged" if acknowledged else "unavailable",
    }


def main():
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["targetGraphs"]))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cargo-home", type=Path, default=ROOT / "artifacts/rust/windows-services/cargo-home")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--hosted-startup", action="store_true", help="also test a unique link in the hosted runner's Startup")
    parser.add_argument("--isolated-session", action="store_true", help="this is a disposable synthetic Windows test profile")
    args = parser.parse_args()
    hosted = (os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted"
              and os.getenv("RUNNER_OS") == "Windows")
    if sys.platform != "win32" or not (hosted or args.isolated_session) or args.hosted_startup and not hosted:
        raise ValueError("Use a native hosted Windows runner or an explicitly isolated Windows test profile")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    build = ROOT / "artifacts/rust/windows-services/build" / args.target
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CARGO_", "RUSTC_", "RUSTDOC"))
           and k not in ("RUSTFLAGS", "RUSTC")}
    env.update(CARGO_HOME=str(args.cargo_home.resolve()), CARGO_TARGET_DIR=str(build))
    result = {"target": args.target, "hosted": hosted, "locked": sha(HERE / "Cargo.lock"),
              "steps": {}, "workflowRun": os.getenv("GITHUB_RUN_ID"),
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    files = list(HERE.glob("*")) + list((HERE / "src").glob("*.rs")) + [QA / "audit-graph.py",
             QA / "check-toolchain.py", QA / "storage/evidence.py", ROOT / "rust/toolchain-inputs.json"]
    result["sourceFiles"] = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files) if p.is_file()}

    def step(name, cmd):
        result["steps"][name] = "started"
        with (output / (name + ".txt")).open("wb") as stream:
            finished = subprocess.run(cmd, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        result["steps"][name] = finished.returncode
        finished.check_returncode()

    try:
        if result["locked"] != inputs["lockSha256"]:
            raise ValueError("Unreviewed Windows lockfile")
        step("compiler", [sys.executable, QA / "check-toolchain.py", args.target])
        step("recovery", [sys.executable, "-m", "unittest", "test_recovery"])
        if not args.offline:
            step("fetch", ["cargo", "fetch", "--locked"])
        step("inventory", [sys.executable, QA / "audit-graph.py", HERE / "Cargo.toml", args.target, output / "graph.json",
                           "--verify-unpacked"])
        graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
        fingerprint = hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if fingerprint != inputs["targetGraphs"][args.target]:
            raise ValueError("Native Windows graph differs from the audited profile")
        result["canonicalGraphSha256"] = fingerprint
        step("format", ["cargo", "fmt", "--all", "--check"])
        step("clippy", ["cargo", "clippy", "--frozen", "--all-targets", "--", "-D", "warnings"])
        step("build", ["cargo", "build", "--frozen", "--release"])
        exe = build / "release/ifw-windows-services-probe.exe"
        result["probeSha256"] = sha(exe)
        result["observations"] = measure(exe, output, hosted, args.hosted_startup)
        if result["observations"]["failedChecks"]:
            raise ValueError("Native checks failed, see result.json, native.txt and observer.json")
        result["probeCompleted"] = True
    finally:
        result.setdefault("probeCompleted", False)
        result["evidenceFiles"] = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "result.json"}
        write(output / "result.json", result)


if __name__ == "__main__":
    main()
