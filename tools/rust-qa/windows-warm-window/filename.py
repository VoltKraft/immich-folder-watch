"""Exercise the ordinary Unicode filename observer on the reopened retained Windows executable."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from functools import partial
import hashlib
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import traceback

from inputs import HERE, QA, ROOT, TARGETS, recorder, sha
from frame_latency import measured_generation
from native import pin_path
from observe import drive

sys.path.insert(0, str(QA / "windows-text"))
text = runpy.run_path(str(QA / "windows-text/run.py"), run_name="ifw_ordinary_filename")
select = runpy.run_path(str(QA / "windows-launcher/retained_subject.py"))["select"]
from win32 import check, ordinary_console, same_name
from worker import named_desktop


def observer_paths():
    sources = [HERE / n for n in ("filename.py", "inputs.py", "observe.py", "residency.py", "window_lifetime.py",
                                  "compiler_units.py", "frame_latency.py")]
    sources.extend(QA / n for n in ("windows-launcher/retained_subject.py", "windows-desktop/session.py",
                                    "windows-performance/build.py", "windows-performance/native.py", "windows-performance/run.py"))
    return sorted({p.relative_to(ROOT).as_posix() for p in [*sources, *text["observer_paths"](), ROOT / ".gitattributes"]})


def check_sources(revision, recorded):
    paths = observer_paths()
    if not re.fullmatch("[0-9a-f]{40}", revision) or set(paths) != set(recorded):
        raise ValueError("Missing, unexpected or unversioned native observer source")
    # Apply the originating commit's checkout attributes. A Windows checkout may use CRLF
    # for paths without an explicit eol. The entire trial must match one Git checkout policy.
    for autocrlf, eol in (("true", "crlf"), ("false", "lf")):
        git = ["git", "--attr-source=" + revision, "-c", "core.autocrlf=" + autocrlf, "-c", "core.eol=" + eol]
        def matches(path):
            content = subprocess.check_output([*git, "cat-file", "--filters", revision + ":" + path], cwd=ROOT)
            return hashlib.sha256(content).hexdigest() == recorded[path]
        if all(map(matches, paths)):
            return
    raise ValueError("The native filename observer sources differ from the originating Git revision")


def eligible_desktop(context):
    name = context["threadDesktop"]
    return isinstance(name, str) and (same_name(name, "Default") or named_desktop(name)) and ordinary_console(context, name)


def check_desktop(subject):
    before, after, window = subject["desktop"], subject["endingDesktop"], subject["window"]
    name = before["threadDesktop"]
    if (not eligible_desktop(before) or not ordinary_console(after, name)
            or not (window["session"] == before["session"] == after["session"])
            or not same_name(window["threadDesktop"], name)
            or window["pid"] != subject["pid"] or window["hwnd"] != hex(subject["hwnd"])
            or type(window["tid"]) is not int or window["tid"] <= 0
            or window["visible"] is not True or window["iconic"] is not False):
        raise ValueError("The field observer, HWND and unlocked input desktop do not share the native session")


def check_lifetime(case, subject, target, expected_hash):
    """Join the original WinEvents, object lifetime and UIA subject to the pinned retained PE."""
    pid, hwnd = subject["pid"], subject["hwnd"]
    expected = f"artifacts/rust/windows-warm-window/{target}/build/release/native-gui-assessment.exe"
    generation = ["GRAPHICS_READY generation=1"]
    if (case["case"] != "retained-filename" or case["exitCode"] != 0 or case["singleWake"]
            or not 0 < pid == case["pid"] or not 0 < case["creation100ns"] == subject["creation100ns"]
            or not hwnd or subject["image"] != expected or subject["imageSha256"] != expected_hash):
        raise ValueError("The text observer used a different process, image or creation time")
    transition, = case["transitions"]
    if (hwnd != transition["hidden"] or hwnd != transition["reopened"]
            or transition["generationBefore"] != generation or transition["generationAfter"] != generation):
        raise ValueError("The original HWND or DX12 device changed during reopen")
    events, objects = case["windowEvents"], case["objectLifetimes"]
    first, last = transition["windowEventRange"]
    start, end = transition["lifetimeStart"], transition["lifetimeEnd"]
    if not (0 <= first < last <= len(events) and 0 <= start <= end <= len(objects)):
        raise ValueError("Missing native lifetime observation interval")
    changes = [e["event"] for e in events[first:last] if e["hwnd"] == hwnd and e["root"] is True]
    own_objects = [(i, row[1]) for i, row in enumerate(objects) if row[0] == hwnd]
    if (not changes or changes[0] != "hide" or changes[-1] != "show"
            or [kind for _, kind in own_objects] != ["create", "destroy"]
            or not own_objects[0][0] < start <= end <= own_objects[1][0]):
        raise ValueError("Window events did not establish an uninterrupted hide and reopen")


def readback(out, target, report):
    """Reopen both original build receipts and the independently captured filename, window and device evidence."""
    paired, canonical, observed = report["retained"], report["canonical"], report["text"]
    warm_path = out.parent / "build.json"
    cold_path = out.parents[2] / "gui-native" / target / "build.json"
    warm, cold = text["read"](warm_path), text["read"](cold_path)
    claims = ("canonicalGraph", "lock", "selectedFeatureRows", "compilerEvidence", "eframeUnit", "winitUnit",
              "eframeSource", "compilerInputs", "variantInputs", "baseFonts", "fallbackFonts")
    graph_path = cold_path.with_name("graph.json")
    if (report["subject"] != "retained" or not (report["target"] == canonical["target"] == paired["target"] == cold["target"] == warm["target"] == target)
            or report["run"] != paired["run"] or report["attempt"] != paired["attempt"]
            or not (canonical["source"] == cold["source"] == warm["revision"] == paired["revision"])
            or not (sha(cold_path) == canonical["receiptSha256"] == paired["baselineReceipt"] == warm["baselineReceipt"])
            or not (cold["binarySha256"] == canonical["binarySha256"] == paired["baseline"] == warm["baseline"])
            or sha(warm_path) != paired["buildReceipt"] or paired["binary"] != warm["binary"] or paired["binary"] == paired["baseline"]
            or any(warm[k] != paired[k] for k in claims)
            or not (sha(graph_path) == canonical["graphSha256"] == cold["graphSha256"] == warm["canonicalGraph"])
            or not (text["read"](graph_path)["lockSha256"] == cold["lockSha256"] == warm["canonicalLock"])
            or warm["fallbackFonts"] != {n: asset["sha256"] for n, asset in cold["fallbackFonts"].items()}
            or warm["compilerEvidence"]["application"]["sha256"] != paired["binary"]
            or sha(out.parent / "compiler.jsonl") != warm["compilerEvidence"]["sha256"]
            or sha(out.parent / "eframe-source.zip") != warm["eframeSource"]["archiveSha256"]):
        raise ValueError("The native text evidence and originating build artifacts differ")
    check_sources(warm["revision"], report["inputs"])
    case = report["lifecycle"]
    log = out / "lifecycle/subject.log"
    if (case["phase"] != "complete" or case.get("failure") or sha(log) != case["subjectLog"]
            or measured_generation(log, "Mailbox") != report["device"]
            or not any(row.startswith("DRAINED passes=") for row in log.read_text(encoding="utf-8").splitlines())
            or text["read"](out / "plan.json") != text["PLAN"] or observed["status"] != "passed"
            or observed["observerExit"] != 0):
        raise ValueError("Incomplete retained renderer, input or worker observations")
    check_lifetime(case, observed, target, paired["binary"])
    check_desktop(observed)
    derived = {}
    text["evaluate"](text["read"](out / "observations.json"), out, observed["pid"], observed["hwnd"], derived)
    if any(derived[name] != observed[name] for name in ("windowReadback", "editingPassed", "issues")):
        raise ValueError("The recorded glyph or editing summary differs from the original captures")


def exercise_reopened(proc, hwnd, env, *, api, desk, binary, expected_hash, output, observed):
    try:
        length = w.DWORD(32768)
        image = c.create_unicode_buffer(length.value)
        check(desk.image(proc._handle, 0, image, c.byref(length)), "QueryFullProcessImageNameW")
        loaded = Path(image.value)
        if loaded != binary or sha(loaded) != expected_hash:
            raise ValueError("The reopened process did not load the pinned retained executable")
        observed.update(pid=proc.pid, hwnd=hwnd, creation100ns=api.process_identity(proc._handle),
                        image=loaded.relative_to(ROOT).as_posix(), imageSha256=expected_hash)
        ps, observed["observerHosts"] = text["select_powershell"](output, "accessibility", env=env)
        if not ps:
            observed["status"] = "unavailable"
            raise RuntimeError("Native Windows UI Automation is unavailable")
        context = observed["desktop"] = desk.context()
        if not eligible_desktop(context):
            observed["status"] = "unavailable"
            raise RuntimeError("The retained GUI does not have an eligible unlocked input desktop")
        text["exercise_window"](desk, context, proc.pid, hwnd, env, ps, output, observed)
        observed["status"] = "passed"
    except Exception:
        # Preserve each actual glyph and edit result, and let the lifecycle fixture drain.
        observed["error"] = traceback.format_exc()


def run(target):
    if (not recorder.hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the disposable native Windows rewrite assessment")
    folder = ROOT / "artifacts/rust/gui-native" / target
    out = ROOT / "artifacts/rust/windows-warm-window" / target / "windows-text"
    out.mkdir(exist_ok=False)
    report = dict(status="failed", subject="retained", target=target, run=os.getenv("GITHUB_RUN_ID"),
                  attempt=os.getenv("GITHUB_RUN_ATTEMPT"), text={"status": "failed"})
    try:
        report["inputs"] = {name: sha(ROOT / name) for name in observer_paths()}
        cold = text["DESKTOP"]["GUI_BINARY"]
        report["canonical"] = text["check_build"](target, cold, folder)
        check_sources(report["canonical"]["source"], report["inputs"])
        api, binary, retained = select(target, cold, text["read"](folder / "build.json"), folder / "graph.json", sha)
        report["retained"] = retained
        if retained["baselineReceipt"] != report["canonical"]["receiptSha256"]:
            raise ValueError("The canonical and retained text assessments have different inputs")
        desk = text["Desktop"]()
        recorder.write(out / "plan.json", text["PLAN"])

        after_reopen = partial(exercise_reopened, api=api, desk=desk, binary=binary,
                               expected_hash=retained["binary"], output=out, observed=report["text"])
        case = report["lifecycle"] = {}
        with pin_path(api, binary.parent, True), pin_path(api, binary, False):
            if sha(binary) != retained["binary"]:
                raise ValueError("The retained binary changed before native launch")
            drive(api, recorder.load_windows_fixture(), binary, out / "lifecycle", "retained-filename",
                  after_reopen=after_reopen, desktop=desk.thread_desktop(desk.thread()), evidence=case)
        log = out / "lifecycle/subject.log"
        if case["subjectLog"] != sha(log):
            raise ValueError("The original retained GUI log changed")
        report["device"] = measured_generation(log, "Mailbox")
        if report["text"]["status"] != "passed":
            report["status"] = report["text"]["status"]
            raise RuntimeError("See the original reopened filename observation")
        readback(out, target, report)
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        recorder.write(out / "result.json", report)
        files = sorted(p for p in out.rglob("*") if p.is_file())
        (out / "evidence.sha256").write_text("".join(f"{sha(p)}  {p.relative_to(out).as_posix()}\n" for p in files),
                                            encoding="utf-8", newline="\n")
    print(report.get("error") or report["status"])
    return int(report["status"] != "passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--replay", type=Path, help="read an extracted windows-text directory beside its native build evidence")
    args = parser.parse_args()
    if args.replay is None:
        sys.exit(run(args.target))
    output = args.replay.resolve()
    result = text["read"](output / "result.json")
    if result["status"] != "passed":
        raise SystemExit(result.get("error") or "Incomplete native filename observation")
    readback(output, args.target, result)
    print("Verified the retained executable, reopened HWND, eight glyphs and three filename edits.")
