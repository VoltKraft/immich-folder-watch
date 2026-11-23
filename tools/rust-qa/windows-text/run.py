"""Observe native filename glyphs, carets, selection and deletion on a disposable Windows desktop."""

import argparse
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import time
import traceback

from evidence import PLAN, editing, glyphs

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
sys.path[:0] = [str(QA / "windows-desktop"), str(QA)]
from gui import source_profile
from storage.evidence import sha256, write_json
from win32 import Desktop, ordinary_console, same_name
from worker import hosted, powershell, shared_windows
from windows_observer import private_profile, select_powershell

DESKTOP = runpy.run_path(str(QA / "windows-desktop/run.py"))
TARGETS = dict(DESKTOP["TARGET"].values())


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_build(target, binary, folder):
    native_arch = runpy.run_path(str(QA / "check-toolchain.py"))["native_architecture"]()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    receipt = read(folder / "build.json")
    runpy.run_path(str(QA / "verify-gui-inputs.py"))["verify"]()
    approved = source_profile.validate()
    manifests = read(ROOT / "rust/audit/gui-profile.json")
    expected = [QA / "gui/Cargo.toml", *sorted((QA / "gui/src").glob("*.rs")), QA / "gui/src/tray-icon.argb", ROOT / "rust/Cargo.toml",
                ROOT / "rust/crates/desktop-lifecycle/Cargo.toml", ROOT / "rust/crates/desktop-lifecycle/src/lib.rs"]
    if (target != f"{native_arch}-pc-windows-msvc" or DESKTOP["pe_machine"](binary) != TARGETS[target]
            or receipt["source"] != source or (os.getenv("GITHUB_SHA") and source != os.environ["GITHUB_SHA"])
            or receipt["target"] != target or receipt["binarySha256"] != sha256(binary)
            or receipt["compilerSources"] != {p.relative_to(ROOT).as_posix(): sha256(p) for p in expected}
            or receipt["sourceTrees"] != approved["trees"] or receipt["fallbackFonts"] != approved["fonts"]
            or receipt["textNotices"] != approved["noticeFiles"]
            or receipt["sourceReconstructionSha256"] != sha256(Path(source_profile.__file__))
            or receipt["sourceProfileSha256"] != sha256(source_profile.REVIEW)
            or not (receipt["lockSha256"] == manifests["lockSha256"] == sha256(QA / "gui/Cargo.lock"))
            or not (receipt["graphSha256"] == manifests["targetReportSha256"][target] == sha256(folder / "graph.json"))):
        raise ValueError("Native machine, executable, audited fonts, source trees, graph or compiler inputs changed")
    return {"source": source, "target": target, "binarySha256": receipt["binarySha256"],
            "receiptSha256": sha256(folder / "build.json"), "graphSha256": receipt["graphSha256"]}


def evaluate(record, output, pid, hwnd, report):
    if record.get("pid") != pid or record.get("hwnd") != hwnd:
        raise ValueError("The text observation does not bind the owned HWND and process")
    if record.get("status") == "unavailable":
        report["status"] = "unavailable"
        raise RuntimeError(record["error"])
    if record.get("field") != "Dateiname" or record.get("foreground") is not True or record.get("inputDesktop") is not True:
        raise ValueError("The normal editor did not own native input")
    issues = report["issues"] = []
    try:
        report["windowReadback"] = glyphs(record["sample"], output / "observations.json.glyphs.png")
    except (KeyError, OSError, ValueError) as error:
        issues.append("glyphs: " + str(error))
    report["editingPassed"] = []
    for spec in PLAN["cases"]:
        rows = [r for r in record["cases"] if r["text"] == spec["text"]]
        try:
            if len(rows) != 1:
                raise ValueError("Missing or duplicate native case")
            editing(rows[0], spec)
            report["editingPassed"].append(spec["text"])
        except (KeyError, ValueError) as error:
            issues.append(f"{spec['text']}: {error}")
    if issues or record.get("status") != "observed":
        raise RuntimeError(record.get("error") or "Incomplete native text or raster evidence")


def exercise_window(api, context, pid, hwnd, env, ps, output, report):
    """Run the ordinary field observer against this exact process and already visible HWND."""
    name = context["threadDesktop"]
    eligible = isinstance(name, str) and ordinary_console(context, name)
    report["window"] = api.observed(hwnd, pid)["subject"]
    window = report["window"]
    if window["session"] != context["session"] or not same_name(window["threadDesktop"], name):
        raise ValueError("The observed HWND is on a different session or desktop")
    args = ["-SubjectId", pid, "-WindowHandle", hwnd, "-PlanFile", output / "plan.json",
            "-OutputFile", output / "observations.json"]
    if not eligible:
        args += ["-ReadOnly"]
    try:
        report["observerExit"] = powershell(ps, HERE / "observe.ps1", args, env, output, output / "observer.log", 140)
    finally:
        try:
            report["endingDesktop"] = api.context()
        except OSError as error:
            report["endingDesktopError"] = str(error)
    evaluate(read(output / "observations.json"), output, pid, hwnd, report)
    if (report["observerExit"] or not eligible or not report.get("endingDesktop")
            or not ordinary_console(report["endingDesktop"], name)):
        raise RuntimeError("The native observer failed or its active desktop changed")


def observe(binary, output, env, ps, report):
    api = Desktop()
    context = report["desktop"] = api.context()
    log = output / "subject.log"
    observer_type = shared_windows()
    with log.open("wb") as stream, subprocess.Popen([binary], cwd=output, env=env, stdin=subprocess.PIPE,
            stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW) as child:
        observer = None
        try:
            observer = observer_type(child.pid, api.thread_desktop(api.thread()))
            child.stdin.write(b"T")
            child.stdin.flush()
            until = time.monotonic() + 40
            while child.poll() is None and time.monotonic() < until:
                hwnd = observer.visible(waiting_for_first=True)
                adapter = next((s for s in log.read_text(encoding="utf-8", errors="replace").splitlines()
                                if s.startswith("ADAPTER Dx12 ")), None)
                if hwnd and adapter:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError("The owned normal GUI did not present a native DX12 window")
            report["adapter"] = adapter
            exercise_window(api, context, child.pid, hwnd, env, ps, output, report)
        finally:
            try:
                if child.poll() is None:
                    try:
                        child.stdin.write(b"Q")
                        child.stdin.flush()
                        child.wait(timeout=10)
                    except (subprocess.TimeoutExpired, OSError):
                        child.kill()
                        child.wait(timeout=5)
                report["subjectExit"] = child.returncode
                report["drained"] = "DRAINED passes=" in log.read_text(encoding="utf-8", errors="replace")
            finally:
                if observer:
                    observer.close()
    if report["subjectExit"] or not report["drained"]:
        raise RuntimeError("The synthetic subject did not drain cleanly")


def observer_paths():
    return [*[HERE / n for n in ("evidence.py", "run.py", "test_text.py", "observe.ps1", "Pointer.cs")], QA / "gui/profile_text.py",
               QA / "windows_observer.py", QA / "observe-windows-gui.py", QA / "font-coverage/text_observations.py",
               QA / "observe-windows-input.ps1", QA / "check-toolchain.py", QA / "storage/evidence.py",
               QA / "gui/source_profile.py", QA / "build-gui-probe.py", ROOT / "rust/audit/gui-profile.json",
               QA / "verify-gui-inputs.py", ROOT / "rust/audit/gui-inputs.json", source_profile.REVIEW,
               *[QA / "windows-desktop" / f for f in ("run.py","job.py","worker.py","win32.py")]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TARGETS))
    parser.add_argument("--isolated-vm", action="store_true", help="an expressly authorized disposable native Windows VM")
    args = parser.parse_args()
    on_repo_runner = (hosted() and os.getenv("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch"
                      and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust")
    if os.name != "nt" or not (on_repo_runner or args.isolated_vm):
        parser.error("A disposable Windows rewrite runner or an explicitly selected isolated Windows VM is required")
    folder = ROOT / "artifacts/rust/gui-native" / args.target
    output = folder / "windows-text"
    output.mkdir(exist_ok=False)
    report = {"status": "failed", "host": platform.platform(), "run": os.getenv("GITHUB_RUN_ID"),
              "attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
              "inputs": {p.relative_to(ROOT).as_posix(): sha256(p) for p in observer_paths()}}
    try:
        binary = DESKTOP["GUI_BINARY"]
        report["build"] = check_build(args.target, binary, folder)
        write_json(output / "plan.json", PLAN)
        with private_profile(output, "profile-", report) as profile:
            scratch = str(profile)
            env = {**os.environ, "USERPROFILE": scratch, "HOME": scratch, "TEMP": scratch, "TMP": scratch,
                   "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc",
                   "POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}
            for key in ("APPDATA", "LOCALAPPDATA"):
                (profile / key).mkdir()
                env[key] = str(profile / key)
            ps, report["observerHosts"] = select_powershell(output, "accessibility", env=env)
            if not ps:
                report["status"] = "unavailable"
                raise RuntimeError("Native Windows UI Automation is unavailable")
            observe(binary, output, env, ps, report)
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        write_json(output / "result.json", report)
        files = sorted(p for p in output.iterdir() if p.is_file())
        (output / "evidence.sha256").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in files),
                                               encoding="utf-8", newline="\n")
    print(report.get("error") or report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
