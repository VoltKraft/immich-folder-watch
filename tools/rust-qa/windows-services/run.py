"""Build and observe native Windows Shell services on a disposable test profile."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
sys.path.insert(0, str(QA))
from service_sources import service_files, verify_checkout

ICON_TEST = "tray::image_tests::archived_marker_pixels_survive_native_hicon_rasterization"


def verify_icon_rasters(path):
    """Read the eight original offscreen DIB snapshots, both handle releases and the exact native test result."""
    rows = path.read_text(encoding="utf-8").splitlines()
    if rows.count(f"test {ICON_TEST} ... ok") != 1:
        raise ValueError("The native tray image test did not run successfully")
    captures = [row for row in rows if row.startswith("HICON_RASTER ")]
    keys = [(rgb, scale, bg) for rgb in ("1fc653", "33c733") for scale in ("source", "systemSmall")
            for bg in ("ff000000", "ffffffff")]
    if len(captures) != len(keys) or [line for line in rows if line.startswith("HICON_RELEASED ")] != [
            "HICON_RELEASED rgb=1fc653", "HICON_RELEASED rgb=33c733"]:
        raise ValueError("Missing native raster or checked HICON destruction")
    small = None
    for line, (rgb, scale, bg) in zip(captures, keys):
        fields = dict(part.split("=", 1) for part in line.split()[1:])
        width, height = int(fields["width"]), int(fields["height"])
        if (fields["rgb"], fields["scale"], fields["background"]) != (rgb, scale, bg) or not (
                8 <= width <= 128 and 8 <= height <= 128):
            raise ValueError("Unexpected native raster size or challenge")
        if scale == "source":
            if (width, height) != (32, 32):
                raise ValueError("The producer's source image size differs")
            left, top, right, bottom = 5, 5, 27, 27
        else:
            if small is not None and small != (width, height):
                raise ValueError("The system small icon metrics differ between native renders")
            small = width, height
            left, top, right, bottom = (width + 3) // 4, (height + 3) // 4, width * 3 // 4, height * 3 // 4
        pixels = fields["pixels"]
        if (fields["interior"] != f"{left},{top},{right},{bottom}" or len(pixels) != 8 * width * height
                or not re.fullmatch("[0-9a-f]+", pixels)):
            raise ValueError("Incomplete original top-down DIB or incorrect sampled bounds")
        # All four corners of the pinned unscaled 32x32 frame have zero alpha.
        if scale == "source" and any(pixels[8 * i + 2:8 * (i + 1)] != bg[2:]
                                     for i in (0, width - 1, width * (height - 1), width * height - 1)):
            raise ValueError("Transparent source corners did not retain their original DIB background")
        expected = (right - left) * (bottom - top)
        exact = sum(pixels[8 * (y * width + x) + 2:8 * (y * width + x + 1)] == rgb
                    for y in range(top, bottom) for x in range(left, right))
        if exact != expected or fields["exact"] != f"{exact}/{expected}":
            raise ValueError("The original opaque marker pixels differ from the recorded observation")


def observe_services_and_image(result, output, step, observe_services):
    try:
        step("tray-image", ["cargo", "test", "--frozen", ICON_TEST, "--", "--exact", "--show-output", "--test-threads=1"])
        verify_icon_rasters(output / "tray-image.txt")
        result["trayImage"] = {"status": "passed", "log": "tray-image.txt"}
    except (subprocess.SubprocessError, OSError, KeyError, ValueError) as error:
        # Keep measuring the actual Shell even when its separate image control fails.
        result["trayImage"] = {"status": "failed", "log": "tray-image.txt", "reason": str(error)}
    result["observations"] = observe_services()
    if result["observations"]["failedChecks"]:
        raise ValueError("Native checks failed, see result.json, native.txt and observer.json")
    result["probeCompleted"] = True
    if result["trayImage"]["status"] == "failed":
        print("Independent HICON producer control failed:", result["trayImage"]["reason"], file=sys.stderr)


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


def observe(stage, area, token, exe, program):
    if not program:
        return {"error": "No Windows scripting host completed this observer capability check"}
    command = [program, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
               "-File", str(HERE / "observe.ps1"), "-Stage", stage, "-Fixture", str(area),
               "-Token", token, "-Executable", str(exe)]
    try:
        proc = subprocess.run(command, cwd=area, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        if proc.returncode:
            return {"error": "PowerShell observer failed", "exitCode": proc.returncode,
                    "diagnostic": proc.stderr.decode("utf-8", errors="replace")[-2048:]}
        return json.loads(proc.stdout.decode("utf-8-sig"))
    except (subprocess.TimeoutExpired, OSError, ValueError) as err:
        progress = area / (stage + ".observer-progress")
        return {"error": type(err).__name__, "lastStep": progress.read_text(encoding="ascii") if progress.is_file() else "host-start"}


def read_native(file):
    metrics = {}
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, raw = line.partition("=")
        if not separator:
            continue
        if raw in ("true", "false"):
            metrics[key] = raw == "true"
        elif key.endswith((".taskbar_desktop", ".thread_desktop")):
            metrics[key] = raw
        else:
            metrics[key] = int(raw)
    return metrics


def measure(exe, output, hosted, known):
    from windows_observer import select_powershell
    token = uuid.uuid4().hex
    observations = {}
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    area = temp_root / ("ifw-shell-" + token)
    area.mkdir()
    recovered = []
    observer_hosts = {}
    try:
        programs = {}
        for capability in ("shortcut", "accessibility"):
            programs[capability], observer_hosts[capability] = select_powershell(area, capability)
        (area / "synthetic.fixture").write_text(token, encoding="ascii")
        mode = "--github-hosted" if hosted else "--isolated-session"
        with (output / "native.txt").open("wb") as stream:
            proc = subprocess.Popen([exe, mode, area, token, "hosted-startup" if known else "private"],
                                    cwd=area, stdout=stream, stderr=stream)
            try:
                deadline = time.monotonic() + 250
                while proc.poll() is None and time.monotonic() < deadline:
                    for stage in ("private", "startup", "tray"):
                        if stage not in observations and (area / (stage + ".ready")).is_file():
                            capability = "accessibility" if stage == "tray" else "shortcut"
                            observations[stage] = observe(stage, area, token, exe, programs[capability])
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
            write(output / "observer.json", {"hosts": observer_hosts, "stages": observations, "recoveredOwnedLinks": recovered})
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
    if not tray or "error" in tray:
        failures.append("Windows accessibility observer did not execute successfully")
    if tray.get("overflow") == "requested" and tray.get("overflowClosed") is not True:
        failures.append("The Explorer notification flyout did not return to its original closed state")
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
        "openedTrayOverflowObserved": tray.get("overflowVisibleAfterRequest") is True,
        "openedTrayOverflowClosed": tray.get("overflowClosed"),
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
              "workflowAttempt": os.getenv("GITHUB_RUN_ATTEMPT"), "runner": os.getenv("RUNNER_NAME"),
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}

    def step(name, cmd):
        result["steps"][name] = "started"
        with (output / (name + ".txt")).open("wb") as stream:
            finished = subprocess.run(cmd, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        result["steps"][name] = finished.returncode
        finished.check_returncode()

    try:
        files = service_files()
        result["checkoutVerified"] = False
        if hosted:
            if result["head"] != os.environ["GITHUB_SHA"]:
                raise ValueError("The native service checkout differs from this hosted job")
            result["sourceFiles"] = verify_checkout(ROOT, files, result["head"], HERE)
            result["checkoutVerified"] = True
        else:
            result["sourceFiles"] = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
        if result["locked"] != inputs["lockSha256"]:
            raise ValueError("Unreviewed Windows lockfile")
        if sha(QA / "gui/src/tray-icon.argb") != inputs["trayArgbSha256"]:
            raise ValueError("The embedded first-party tray image differs from the reviewed input")
        step("compiler", [sys.executable, QA / "check-toolchain.py", args.target])
        step("recovery", [sys.executable, "-m", "unittest", "test_recovery", "test_activation", "test_notification"])
        step("toast-controls", [sys.executable, "-B", "-m", "unittest", "-v", "test_toast_history"])
        step("tray-cleanup", ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", HERE / "test_tray_state.ps1"])
        step("notification-points", ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                     "-File", HERE / "test_notification_points.ps1"])
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
        step("balloon-id", ["cargo", "test", "--frozen", "balloon_callbacks_belong_to_the_registered_v4_icon"])
        step("notifier-readiness", ["cargo", "test", "--frozen", "toast_readiness::tests"])
        step("build", ["cargo", "build", "--frozen", "--release"])
        if hosted:
            result["checkoutVerified"] = False
            if verify_checkout(ROOT, service_files(), result["head"], HERE) != result["sourceFiles"]:
                raise ValueError("The first-party fixture sources changed during the native build")
            result["checkoutVerified"] = True
        exe = build / "release/ifw-windows-services-probe.exe"
        result["probeSha256"] = sha(exe)
        from activation import TARGET, module
        from toast_history import validate_imports
        machine = next(machine for target, machine in TARGET.values() if target == args.target)
        imports = module("service_pe", QA / "windows-imports/formats.py").pe_imports(exe, machine)
        validate_imports(imports)
        write(output / "pe-imports.json", imports)
        tick = ctypes.WinDLL("kernel32").GetTickCount64
        tick.restype = ctypes.c_uint64
        tick.argtypes = []
        def observe_services():
            result["measureUptimeMs"] = tick()
            return measure(exe, output, hosted, args.hosted_startup)

        observe_services_and_image(result, output, step, observe_services)
    finally:
        result.setdefault("probeCompleted", False)
        result["evidenceFiles"] = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "result.json"}
        write(output / "result.json", result)


if __name__ == "__main__":
    main()
