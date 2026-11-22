"""Observe an actual Explorer notification-area activation on a private hosted Windows desktop."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
DESKTOP = QA / "windows-desktop"
ART = ROOT / "artifacts/rust/windows-services"
TARGET = {"X64": ("x86_64-pc-windows-msvc", 0x8664), "ARM64": ("aarch64-pc-windows-msvc", 0xaa64)}


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def sha(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(file, item):
    file.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def paths(target):
    return ART / "build" / target / "release/ifw-windows-services-probe.exe", ART / ("native-" + target)


def hosted(target):
    return (os.name == "nt" and os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("RUNNER_OS") == "Windows"
            and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust"
            and TARGET.get(os.getenv("RUNNER_ARCH"), (None,))[0] == target)


def controls(target, exe, directory, report):
    path = directory / "result.json"
    base = json.loads(path.read_text(encoding="utf-8"))
    pins = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    obs = base["observations"]
    if (not base["hosted"] or not base["probeCompleted"] or obs["failedChecks"] or base["target"] != target
            or base["head"] != os.environ["GITHUB_SHA"] or base["workflowRun"] != os.environ["GITHUB_RUN_ID"]
            or base["probeSha256"] != sha(exe) or base["locked"] != pins["lockSha256"]
            or base["canonicalGraphSha256"] != pins["targetGraphs"][target]
            or any(obs[key] is not True for key in ("privateShortcut", "knownStartupShortcut", "hiddenWindowAndControlledCallbacks",
                                                     "privateDesktopHostAbsence", "privateDesktopFallbackWindowVisible"))):
        raise ValueError("Expected the source-bound native service and shell-less controls on the same runner")
    sources = [*HERE.glob("*.py"), *HERE.glob("*.ps1"), *(HERE / "src").glob("*.rs"), HERE / "Cargo.toml",
               HERE / "Cargo.lock", HERE / "inputs.json", QA / "gui/src/tray-icon.argb",
               QA / "gui/src/windows_tray_shell.rs"]
    for source in sources:
        if sha(source) != base["sourceFiles"][source.relative_to(ROOT).as_posix()]:
            raise ValueError("The source used to build or observe the original service changed")
    for name in ("native.txt", "observer.json", "graph.json"):
        if base["evidenceFiles"][name] != sha(directory / name):
            raise ValueError("The original native evidence changed")
    report.update(nativeControlSha256=sha(path), binarySha256=sha(exe), originalControls=obs,
                  sharedSources={p.relative_to(ROOT).as_posix(): sha(p) for p in
                  (DESKTOP / "run.py", DESKTOP / "worker.py", DESKTOP / "win32.py", DESKTOP / "job.py",
                   QA / "windows-performance/native.py", QA / "windows_observer.py")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=[name for name, _ in TARGET.values()])
    target = parser.parse_args().target
    if not hosted(target):
        parser.error("Use the matching native, disposable GitHub Windows rewrite runner")
    exe, original = paths(target)
    output = original / "activation"
    output.mkdir(exist_ok=False)
    report = {"status": "failed", "head": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
              "attempt": os.getenv("GITHUB_RUN_ATTEMPT"), "target": target}
    try:
        controls(target, exe, original, report)
        sys.path[:0] = [str(DESKTOP), str(QA)]
        desktop = module("private_desktop", DESKTOP / "run.py")
        machine = TARGET[os.environ["RUNNER_ARCH"]][1]
        if any(desktop.pe_machine(path) != machine for path in (exe, Path(sys.executable))):
            raise ValueError("The Python and Rust processes must both be native to this runner")
        with tempfile.TemporaryDirectory(prefix="ifw-uia-host-", dir=os.environ["RUNNER_TEMP"]) as area:
            host, report["uiaHosts"] = desktop.select_powershell(area, "accessibility")
        # The tested supervisor restores Default and closes both desktop handles on every outcome.
        with desktop.named_input_desktop(desktop.Desktop(), report) as name:
            exit_code = desktop.run_worker(HERE / "activation_worker.py", [target, name, host or "-"], name, ROOT,
                                           report, timeout_seconds=155)
        child = json.loads((output / "worker.json").read_text(encoding="utf-8"))
        if (report["cleanup"]["inputAfterRestore"].casefold() != "default" or not report["jobClosed"]
                or not report["cleanup"]["namedClosed"] or not report["cleanup"]["originalHandleClosed"]):
            raise RuntimeError("The supervisor could not confirm native desktop cleanup")
        if exit_code == 2 and child["status"] == "unavailable":
            report["status"], report["reason"] = child["status"], child["reason"]
        elif exit_code == 0 and child["status"] == "passed":
            report["status"] = "passed"
        else:
            raise RuntimeError("The private tray worker or its cleanup failed")
    except Exception:
        report["error"] = traceback.format_exc(limit=5)
    finally:
        report["evidenceFiles"] = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
        write(output / "result.json", report)
    print(report.get("reason") or report.get("error") or report["status"])
    return {"passed": 0, "unavailable": 2, "failed": 1}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
