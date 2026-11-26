"""Compare the original retained root with and without per-window DWM transitions on native x64."""
import argparse
from bisect import bisect_left
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import subprocess

from inputs import HERE, recorder, sha
from build import REFERENCE, REFERENCE_SOURCE_SHA256
from compiler_units import VARIANT_INPUTS
from frame_latency import HOST_BUILD, measured_generation, replay_scan, visible_edit
from metrics import METRICS
from observe import capture_field
from scan import MIN_RESPONSES, coverage
from scan_present import start as trace_presentation
from window_lifetime import WindowLifetime

TARGET = "x86_64-pc-windows-msvc"
MODES = ("ordinary", "disabled")
METRIC_NAMES = ("scan_close_p95_ms", "scan_reopen_p95_ms")
INPUTS = ("dwm_transitions.py", "observe.py", "window_lifetime.py", "../observe-windows-input.ps1",
          "../windows-inventory/scan.py", "../windows-performance/present.cpp", "../windows-performance/etw-owned.h")


def read(path):
    return json.loads(path.read_bytes())


def root_marker(text, mode, root):
    rows = text.splitlines()
    lines = [s for s in rows if s.startswith("DWM_TRANSITIONS")]
    tail = {"ordinary": "set=0", "disabled": "set=1 hresult=0"}[mode]
    expected = f"DWM_TRANSITIONS mode={mode} hwnd={root['hwnd']} pid={root['pid']} tid={root['tid']} {tail}"
    if (min(root.values()) <= 0 or lines != [expected]
            or "GRAPHICS_READY generation=1" not in rows or rows.index(expected) >= rows.index("GRAPHICS_READY generation=1")
            or [s for s in text.splitlines() if s.startswith("ADAPTER ")] != ["ADAPTER Dx12 Cpu Microsoft Basic Render Driver"]):
        raise ValueError("The DWM operation, adapter or independently observed root differs")


def capture_editor(api, fixture, output, lifetime, windows, proc, area, env, log, hwnd, *, field_observer=capture_field):
    """Run after the two passes and after both ETW sessions have been closed and decoded."""
    output.mkdir()
    def owner():
        pid = wintypes.DWORD()
        tid = windows.owner(hwnd, ctypes.byref(pid))
        if pid.value != proc.pid or not tid or windows.ancestor(hwnd, 2) != hwnd:
            raise ValueError("The live editor HWND is not the original process's root")
        return dict(hwnd=hwnd, pid=pid.value, tid=tid)

    def wait(predicate):
        def poll():
            recorder.wait_running(proc)
            windows.pump()
            return predicate()
        return recorder.await_value(poll, "The original scan editor did not complete its HWND transition")

    def reopen():
        proc.stdin.write(b"O")
        proc.stdin.flush()
        wait(lambda: windows.visible() == hwnd)

    def generations():
        return [s for s in log.read_text(encoding="utf-8").splitlines() if s.startswith("GRAPHICS_READY ")]

    def event(since, name):
        return any(e["hwnd"] == hwnd and e["root"] and e["event"] == name for e in windows.events[since:])

    first = api.clock()
    root = owner()
    if not windows.visible():
        since = len(windows.events)
        reopen()
        wait(lambda: event(since, "show"))
    if windows.visible() != hwnd:
        raise ValueError("Cannot edit a different visible window")
    shell, attempts = fixture.select_powershell(area, "accessibility", env)
    recorder.write(output / "hosts.json", attempts)
    if not shell:
        raise ValueError("The native UI Automation input and pixel observer is unavailable")
    before = field_observer(shell, area, env, output, hwnd, proc.pid, log, "before")
    generation = generations()
    windows.pump()
    start = len(windows.events)
    windows.close_window(hwnd)
    wait(lambda: not windows.visible() and event(start, "hide"))
    if owner() != root:
        raise ValueError("The hidden editor belongs to a different process or thread")
    hidden = api.clock()
    reopen()
    wait(lambda: event(start, "show"))
    visible = api.clock()
    after = field_observer(shell, area, env, output, hwnd, proc.pid, log, "after")
    windows.pump()
    if owner() != root:
        raise ValueError("The reopened scan editor lost its owner")
    return dict(case="retained-edit", pid=proc.pid, creation100ns=api.process_identity(proc._handle), root=root,
                singleWake=False, beforeField=before, afterField=after, editorClocks=[first, hidden, visible, api.clock()],
                rootLifetimes=[event for event in lifetime.events if event[0] == hwnd],
                rootEvents=[event for event in windows.events[start:] if event["root"] and event["hwnd"] == hwnd],
                transitions=[dict(hidden=hwnd, reopened=hwnd, generationBefore=generation, generationAfter=generations())])


def native_frames(text, root, clock, bounds):
    lines = text.splitlines()
    if (lines[:2] != ["READY", f"QPC {root['pid']} {clock}"] or lines[-1:] != ["COMPLETE"]
            or len(lines) < 5 or len(lines[2:-1]) % 2):
        raise ValueError("Missing paired DXGI events or native trace clock")
    frames = []
    last = bounds[0]
    for stop, timed in zip(lines[2:-1:2], lines[3:-1:2], strict=True):
        fields = timed.split()
        if len(fields) != 7 or fields[0] != "DXGI":
            raise ValueError("Missing timed native DXGI present")
        pid, tid, interval, flags, begin, end = map(int, fields[1:])
        if (stop != f"P DXGI {end}" or (pid, tid) != (root["pid"], root["tid"]) or flags & (0x1 | 0x200)
                or not last <= begin <= end <= bounds[1]):
            raise ValueError("Unmatched successful DXGI present, unexpected owner, flags or event order")
        frames.append((begin, end, interval))
        last = end
    return frames


def visible_frames(scan, meta, files, graphics, root):
    requests = meta["requests"]
    hz = meta["frequency"]
    bounds = scan["presentation"]["traceBoundsQpc"]
    frames = native_frames(graphics, root, hz, bounds)
    starts = [lo for lo, _, _ in frames]
    first = scan["passes"][0]
    if not bounds[0] <= first["firstFileQpc"] < first["lastFileQpc"] <= meta["secondCompleteQpc"] <= bounds[1]:
        raise ValueError("The inventory lies outside the original DXGI trace")
    eligible = {q["responseQpc"] for q in scan["eligibleResponses"] if q["action"] == "reopen"}
    probes, by_begin = [], {}
    for i, q in enumerate(requests):
        if q["hwnd"] != root["hwnd"] or q["action"] != ("close", "reopen")[i % 2]:
            raise ValueError("Unexpected HWND or action in the scan")
        lo = q["responseQpc"]
        hi = requests[i + 1]["issuedQpc"] if i + 1 < len(requests) else meta["secondCompleteQpc"]
        if hi <= lo:
            raise ValueError("Overlapping acknowledged HWND requests")
        index = bisect_left(starts, lo)
        if q["action"] == "close":
            probes.append(q)
            if ((index and frames[index - 1][1] > lo) or (index < len(frames) and starts[index] < hi)):
                raise ValueError("A DXGI present crossed an independently observed hidden interval")
        elif (lo in eligible and i + 1 < len(requests) and index < len(frames)
              and first["firstFileQpc"] <= frames[index][0] <= frames[index][1] <= first["lastFileQpc"]
              and frames[index][1] < hi and frames[index][2] == 0):
            begin, end, _ = frames[index]
            probes.append(dict(action="reopen", issuedQpc=begin, responseQpc=end, hwnd=root["hwnd"]))
            by_begin[begin] = lo
    # Reuse the original bracketing file-completion criterion on the presented frame itself.
    near_files = coverage(files, probes, meta["firstCompleteQpc"], meta["secondCompleteQpc"], hz, meta["inventoryPid"], "rust")
    hits = [dict(visibleQpc=by_begin[q["issuedQpc"]], beginQpc=q["issuedQpc"], endQpc=q["responseQpc"])
            for q in near_files["eligibleResponses"] if q["action"] == "reopen"]
    if len(hits) < MIN_RESPONSES:
        raise ValueError("Fewer than five distinct file-qualified reopens with a complete Mailbox present")
    return dict(eligibleReopens=len(eligible), eligibleReopensWithPresent=len(hits), firstPresents=hits,
                visibleToFirstPresentP95Ms=recorder.p95([(r["endQpc"]-r["visibleQpc"]) * 1000 / hz for r in hits]))


def scan_result(out, idx, mode, row):
    name = f"rust-{idx}"
    stem = name + "-scan"
    scan = row["scan"]
    log = out / (stem + ".log")
    meta = read(out / (stem + "-requests.json"))
    replay_scan(out, name, row)
    edit = scan["editor"]
    if "error" in edit:
        raise ValueError(f"{mode} scan editor observation failed: {edit['error']}")
    root = edit["root"]
    text = log.read_text(encoding="utf-8")
    root_marker(text, mode, root)
    if (root["pid"] != meta["guiPid"] or edit["creation100ns"] != scan["presentation"]["guiCreation100ns"]
            or re.findall(r"^INVENTORY_WORKER pid=(\d+)$", text, re.M) != [str(meta["inventoryPid"])]
            or scan["termination"] != {"method": "control-Q", "exitCode": 0}
            or [e[1] for e in edit["rootLifetimes"] if e[0] == root["hwnd"]] != ["create"]
            or [(e["event"], e["hwnd"], e["root"]) for e in edit["rootEvents"]] != [
                ("hide", root["hwnd"], True), ("show", root["hwnd"], True)]):
        raise ValueError("The inventory, original root lifetime or external editor identity differs")
    a, b, c, d = edit["editorClocks"]
    if not scan["presentation"]["traceBoundsQpc"][1] <= a < b < c < d:
        raise ValueError("Editor input overlapped the inventory or presentation measurement")
    view = visible_edit(out / (mode + "-editor"), edit, 1, subject_log=log)
    if (view["hwnd"], view["pid"]) != (root["hwnd"], root["pid"]):
        raise ValueError("The captured editor differs from the measured root")
    frames = visible_frames(scan, meta, (out / (stem + "-files.log")).read_text(encoding="ascii"),
                            (out / (stem + "-presents.log")).read_text(encoding="ascii"), root)
    return dict(mode=mode, root=root, editor=view, frames=frames, metrics=scan["metrics"])


def references(out, record, baseline, *, separate_gui=False, candidate_presentation=("Mailbox", 1)):
    base = out.parent
    ordinary_path = base / "measured/result.json"
    ordinary = read(ordinary_path)
    expected_gui = record["pairedBinary"] if separate_gui else record["binary"]
    common_fields = tuple(k for k in HOST_BUILD if k != "binary")
    fixed = read(baseline / "reference-budget.json")
    wpf = read(baseline / "result.json")
    inputs = read(baseline / "inputs.json")
    art = base.parents[1]
    build = read(base / "build.json")
    canonical_path = art / "gui-native" / TARGET / "build.json"
    canonical = read(canonical_path)
    if (record["target"] != TARGET or (record["presentMode"], record["desiredMaximumFrameLatency"]) != candidate_presentation
            or record["diagnosticControl"] is not True
            or record["scanObserver" if separate_gui else "dwmObserver"] != {name: sha(HERE / name) for name in INPUTS}
            or record["observerInputs"] != {name: sha(HERE / name) for name in ("measure.py", "frame_latency.py", "inputs.py", "scan_present.py")}
            or any(ordinary[k] != record[k] for k in (*common_fields, "referenceBudgetSha256", "observerInputs"))
            or ordinary["binary"] != expected_gui or ordinary["inputs"]["inventory"]["gui"] != expected_gui
            or ordinary["status"] not in ("over-budget", "measured-metrics-passed") or len(ordinary["trials"]) != recorder.TRIALS
            or (separate_gui and expected_gui == record["binary"])
            or ordinary["presentMode"] != "Mailbox" or ordinary["desiredMaximumFrameLatency"] != 1 or ordinary["diagnosticControl"]
            or ordinary["inputs"]["workload"] != record["inputs"]["workload"]
            or any(ordinary["inputs"]["inventory"][k] != record["inputs"]["inventory"][k]
                   for k in ("compiledEntry", "approvedBundle", "packages", "sources"))):
        raise ValueError("The three ordinary trials and the transition pair differ in host, build, workload or observers")
    if (sha(base / "build.json") != record["buildReceipt"]
            or build["binary"] != expected_gui
            or any(build[k] != record[k] for k in ("target", "revision", "baseline", "baselineReceipt"))
            or build["variantInputs"] != {name: sha(HERE / name) for name in VARIANT_INPUTS}
            or any(build["compilerInputs"][n] != sha(HERE / n) for n in ("windows_present.rs", "dwm_transitions.rs"))
            or sha(base / "build/release/native-gui-assessment.exe") != expected_gui
            or sha(art / "gui-build/release/native-gui-assessment.exe") != record["baseline"]
            or sha(canonical_path) != record["baselineReceipt"] or canonical["binarySha256"] != record["baseline"]
            or (canonical["source"], canonical["target"]) != (record["revision"], TARGET)
            or (canonical["lockSha256"], canonical["graphSha256"]) != (build["canonicalLock"], build["canonicalGraph"])
            or build["compilerEvidence"]["application"] != dict(target="native-gui-assessment", crateRoot="src/main.rs",
                                                                 output="native-gui-assessment.exe", sha256=expected_gui)
            or sha(base / "compiler.jsonl") != build["compilerEvidence"]["sha256"]
            or sha(base / "eframe-source.zip") != build["eframeSource"]["archiveSha256"]
            or record["inputs"]["inventory"]["gui"] != record["binary"]):
        raise ValueError("The native executables or their original compiler, source or graph receipts differ")
    if (not record["run"]
            or (record["run"], record["attempt"]) != (wpf["host"]["run"], wpf["host"]["attempt"])
            or (inputs["target"], inputs["candidateRevision"], inputs["guiBinarySha256"], inputs["guiReceiptSha256"])
            != tuple(record[k] for k in ("target", "revision", "baseline", "baselineReceipt"))
            or (inputs["referenceRevision"], inputs["referenceSourceSha256"]) != (REFERENCE, REFERENCE_SOURCE_SHA256)
            or not sha(baseline / "reference-budget.json") == record["referenceBudgetSha256"] == wpf["budgetSha256"]
            or fixed["sourceInputsSha256"] != sha(baseline / "inputs.json")
            or any(inputs["inventory"][k] != record["inputs"]["inventory"][k] for k in ("compiledEntry", "approvedBundle", "packages", "sources"))
            or any(inputs["workload"].get(k) != v for k, v in record["inputs"]["workload"].items())
            or recorder.summarize(wpf["trials"]["wpf"]) != fixed["reference"] or recorder.budgets(fixed["reference"]) != fixed["maximums"]):
        raise ValueError("The three native WPF trials, frozen limits or inventory inputs differ")
    rows = recorder.comparison(fixed["maximums"], recorder.summarize(ordinary["trials"]))
    outcome = "over-budget" if any(r["passed"] is False for r in rows.values()) else "measured-metrics-passed"
    if ordinary["comparison"] != rows or ordinary["status"] != outcome or any(rows[k]["passed"] is None for k in METRICS):
        raise ValueError("The three ordinary trials do not cover the eleven original WPF metrics")
    for idx, row in enumerate(ordinary["trials"], 1):
        name = f"rust-{idx}"
        replay_scan(ordinary_path.parent, name, row)
        for suffix, subject in ((".log", row), ("-scan.log", row["scan"])):
            log = ordinary_path.parent / (name + suffix)
            if (measured_generation(log, "Mailbox") != subject["device"]
                    or "DWM_TRANSITIONS" in log.read_text(encoding="utf-8")):
                raise ValueError("An ordinary three-trial subject used a different presentation policy")
    return dict(wpfInputsSha256=sha(baseline / "inputs.json"), wpfResultSha256=sha(baseline / "result.json"),
                ordinaryResultSha256=sha(ordinary_path), ordinaryThree={k: rows[k] for k in METRIC_NAMES})


def comparison(out, record, baseline):
    source = references(out, record, baseline)
    legs = {}
    for idx, (mode, trial) in enumerate(zip(MODES, record["trials"], strict=True), 1):
        legs[mode] = scan_result(out, idx, mode, trial)
    first, second = (legs[m]["editor"]["creation100ns"] for m in MODES)
    if not 0 < first < second:
        raise ValueError("The control and disabled runs did not use consecutive fresh GUI processes")
    checks = {mode: {k: dict(maximum=source["ordinaryThree"][k]["maximum"], candidate=leg["metrics"][k],
                               passed=leg["metrics"][k] <= source["ordinaryThree"][k]["maximum"]) for k in METRIC_NAMES}
              for mode, leg in legs.items()}
    return dict(source, checks=checks, legs=legs)


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget):
    if record["target"] != TARGET or not files:
        raise ValueError("The DWM comparison requires native Windows x64 and both ETW observers")
    record["dwmObserver"] = {name: sha(HERE / name) for name in INPUTS}
    references(out, record, budget.parent)
    for idx, mode in enumerate(MODES, 1):
        lifetime = None

        def trace(stack, proc, scan_area, output):
            nonlocal lifetime
            lifetime = WindowLifetime(proc.pid)
            stack.callback(lifetime.close)
            return trace_presentation(api, present, "Mailbox", stack, proc, scan_area, output)

        def editor(*args):
            # Keep the completed scan and run the second leg even if native field capture fails.
            try:
                return capture_editor(api, fixture, out / (mode + "-editor"), lifetime, *args)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
                return {"error": f"{type(exc).__name__}: {exc}"}

        name = f"rust-{idx}-scan"
        scan = recorder.measure_scan(api, fixture, "rust", gui, files, area / name, endpoint, user_sid, out,
                                     recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                     presentation_trace=trace, dwm_transitions=mode, after_inventory=editor)
        scan["editor"].update(exitCode=scan["termination"]["exitCode"], subjectLog=sha(out / (name + ".log")))
        record["trials"].append(dict(scan=scan, metrics=scan["metrics"]))
        recorder.write(out / "result.json", record)
    record["pair"] = comparison(out, record, budget.parent)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recompute the complete native DWM pair from extracted same-run evidence.")
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output.resolve()
    report = read(out / "result.json")
    baseline = out.parents[2] / "windows-performance" / ("native-" + TARGET)
    if report["status"] != "dwm-transitions-observed" or comparison(out, report, baseline) != report["pair"]:
        raise ValueError("The saved transition pair differs from its original native evidence")
    print(json.dumps(report["pair"]["checks"], indent=2))
