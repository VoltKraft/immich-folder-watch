"""Measure one isolated deferred-render trial and verify its original native evidence."""
from bisect import bisect_left, bisect_right
from functools import partial
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path, PureWindowsPath
from statistics import median
import re
import shutil
import sys
from zipfile import ZipFile

import prepare
from deferred_build import FILES, GATE
from frame_latency import measured_generation, replay_scan, visible_edit
from inputs import recorder, sha
from metrics import METRICS
from observe import drive, observer_inputs
from readback import release_outputs
from scan_present import start


def summary(path):
    device = measured_generation(path, "Mailbox", wait_policy="DontWait")
    lines = path.read_text(encoding="utf-8").splitlines()
    events = [row for row in lines if row.startswith("DEFERRED_FRAME ")]
    pattern = r"DEFERRED_FRAME signalled=(\d+) timeouts=(\d+) resumed=(\d+) early_callbacks=(\d+) dropped=(\d+)"
    match = re.fullmatch(pattern, events[0]) if len(events) == 1 else None
    if not match:
        raise ValueError("Missing complete readiness counts for the native renderer")
    ready, timeouts, resumed, early, dropped = map(int, match.groups())
    if not ready or dropped or resumed > min(ready, timeouts) or (early and not timeouts):
        raise ValueError("Inconsistent zero-time readiness samples")
    spans = []
    previous = 0
    for row in lines:
        if row.startswith("DEFERRED_PRESENT "):
            tid, signal, start, end = map(int, row.split()[1:])
            if not (tid > 0 and previous < signal <= start <= end):
                raise ValueError("Unordered resumed frame or invalid UI thread")
            spans.append((tid, signal, start, end))
            previous = end
    if len(spans) > resumed:
        raise ValueError("More resumed presentation spans than readiness signals")
    return dict(device=device, signalled=ready, timeouts=timeouts, resumed=resumed,
                earlyCallbacks=early, presentedAfterRetry=len(spans)), spans


def matched_presents(lines, process, bounds, spans, requests):
    """Join resumed queue calls to the independent, successful DXGI events on their native thread and clock."""
    active = [(tid, start, end) for tid, ready, start, end in spans if bounds[0] <= ready <= end <= bounds[1]]
    if not active:
        raise ValueError("No completed retry during the independently observed first inventory")
    events = []
    for line in lines:
        if line.startswith("DXGI "):
            pid, tid, interval, flags, start, end = map(int, line.split()[1:])
            if bounds[0] <= start <= end <= bounds[1]:
                if pid != process or tid <= 0 or interval or flags & 0x201:
                    raise ValueError("Foreign process, unexpected mode or unsuccessful native DXGI control")
                events.append((start, end, tid))
    events.sort()
    starts = [start for start, _, _ in events]
    for tid, lo, hi in active:
        i = bisect_left(starts, lo)
        if (i == len(events) or events[i][1] > hi or events[i][2] != tid
                or (i + 1 < len(events) and events[i + 1][0] <= hi)):
            raise ValueError("A resumed presentation does not enclose one matching UI-thread DXGI present")
    visible = [(opened["responseQpc"], closed["issuedQpc"]) for opened, closed in zip(requests, requests[1:])
               if opened["action"] == "reopen" and closed["action"] == "close" and opened["hwnd"] == closed["hwnd"]]
    begins = [start for start, _ in visible]
    observed = 0
    for _, ready, _, end in spans:
        if bounds[0] <= ready <= end <= bounds[1]:
            index = bisect_right(begins, ready) - 1
            if index >= 0 and end <= visible[index][1]:
                observed += 1
    if not observed:
        raise ValueError("No resumed DXGI frame after the independent observer saw its HWND reopen")
    return dict(firstInventory=len(active), afterObservedReopen=observed)


def resource_samples(row):
    metrics = row["metrics"]
    controls = row["presentation"]["reopenControls"]
    if (not isinstance(controls, list) or len(controls) != 2 or any(type(n) != int or n < 1 for n in controls)
            or row["presentation"]["idleCounts"] != {"visible": 0, "hidden": 0}
            or row["controls"]["successfulVisibilityCycles"] != recorder.SWITCHES
            or row["termination"]["exitCode"] != 0 or set(metrics) != set(METRICS)
            or any(type(n) not in (float, int) or not isfinite(n) or n < 0 for n in metrics.values())):
        raise ValueError("Missing idle control, process exit or timing metric")
    for action in ("close", "reopen"):
        values = row["idleVisibilityMs"][action]
        if len(values) != recorder.SWITCHES or metrics[f"idle_{action}_p95_ms"] != recorder.p95(values):
            raise ValueError("Idle response differs from its eight individual observations")
    for mode in ("visible", "hidden"):
        sample = row["idleSamples"][mode]
        if (sample["seconds"] < recorder.IDLE_SECONDS or metrics[mode + "_present_per_second"] != 0
                or sample["working_set_mib"] != median(sample["samples"])
                or any(metrics[mode + "_" + key] != sample[key] for key in ("cpu_one_core_pct", "working_set_mib"))):
            raise ValueError("Idle resource values differ from the original native samples")


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget):
    if not files:
        raise ValueError("The original native file observer is required")
    shutil.copyfile(budget, out / "reference-budget.json")
    row = recorder.trial(api, fixture, "rust", gui, present, area / "rust-1", endpoint, user_sid,
                         0x8664, out / "rust-1.log", token)
    shutil.copyfile(area / "rust-1/present.log", out / "rust-1-idle-presents.log")
    record["idlePresentsSha256"] = sha(out / "rust-1-idle-presents.log")
    record["trial"] = row
    recorder.write(out / "result.json", record)
    row["scan"] = recorder.measure_scan(api, fixture, "rust", gui, files, area / "rust-1-scan", endpoint, user_sid,
                                         out, recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                         presentation_trace=partial(start, api, present, "Mailbox"))
    row["metrics"].update(row["scan"]["metrics"])
    recorder.write(out / "result.json", record)
    record["editObservers"] = observer_inputs()
    record["ordinaryObserverReceipt"] = sha(out.parent / "observed/result.json")
    record["edit"] = {}
    drive(api, fixture, gui, out / "retained-edit", "retained-edit", evidence=record["edit"])
    record["checks"] = readback(out, record)


def readback(out, record):
    base = out.parent
    read = lambda path: json.loads(path.read_bytes())
    primary = read(base / "measured/result.json")
    frame = read(base / "frame-cost/result.json")
    observed = read(base / "observed/result.json")
    receipt = read(out / "deferred-build.json")
    ordinary = read(base / "build.json")
    prior = read(base / "frame-cost/diagnostic-build.json")
    budget = read(out / "reference-budget.json")
    if (record["target"] != prepare.TARGET or record["presentMode"] != "Mailbox"
            or record["desiredMaximumFrameLatency"] != 1 or record["diagnosticControl"] is not True or frame["status"] != "frame-cost-observed"
            or any(record[k] != primary[k] or primary[k] != frame[k] for k in
                   ("revision", "target", "run", "attempt", "baseline", "baselineReceipt", "buildReceipt",
                    "referenceBudgetSha256", "observerInputs"))
            or record["ordinaryObserverReceipt"] != sha(base / "observed/result.json")
            or record["editObservers"] != observed["observerInputs"] or observed["observerInputs"] != observer_inputs()
            or any(observed[k] != primary[k] for k in ("revision", "target", "run", "attempt", "binary", "buildReceipt"))
            or record["pairedBinary"] != primary["binary"] or record["pairedBinary"] != frame["pairedBinary"]
            or record["buildReceipt"] != sha(base / "build.json") or receipt["baselineBuild"] != record["buildReceipt"]
            or receipt["ordinaryBinary"] != ordinary["binary"] or receipt["ordinaryBinary"] != record["pairedBinary"]
            or receipt["nativeCompiler"] != ordinary["nativeCompiler"] or receipt["nativeCompiler"] != prior["nativeCompiler"]
            or receipt["originalFrameResult"] != sha(base / "frame-cost/result.json")
            or receipt["diagnosticBuild"] != sha(base / "frame-cost/diagnostic-build.json")
            or receipt["sourceArchive"] != sha(base / "frame-cost/source.zip") or receipt["sourceArchive"] != prior["source"]["archive"]
            or record["deferredBuild"] != sha(out / "deferred-build.json")
            or record["binary"] != sha(out / "deferred.exe") or record["binary"] != receipt["application"]["sha256"]
            or record["binary"] in (ordinary["binary"], frame["binary"]) or recorder.pe_machine(out / "deferred.exe") != 0x8664
            or record["inputs"]["inventory"]["gui"] != record["binary"] or record["inputs"]["workload"] != primary["inputs"]["workload"]
            or any(record["inputs"]["inventory"][k] != primary["inputs"]["inventory"][k] for k in
                   ("compiledEntry", "approvedBundle", "packages", "sources"))
            or sha(out / "reference-budget.json") != record["referenceBudgetSha256"] or budget["maximums"] != recorder.budgets(budget["reference"])
            or recorder.comparison(budget["maximums"], recorder.summarize(primary["trials"])) != primary["comparison"]
            or receipt["compiler"] != sha(out / "compiler.jsonl") or receipt["supplement"] != sha(out / "deferred-source.zip")):
        raise ValueError("Different native subject, source, WPF limits or file workload")
    with ZipFile(out / "deferred-source.zip") as sources:
        members = sources.namelist()
        configuration = json.loads(sources.read("deferred-pins.json"))
        pins = configuration["files"]
        if (set(members) != set(FILES) | {"compiled/" + n for n in [*pins, GATE]} or len(set(members)) != len(members)
                or {n:sha256(sources.read(n)).hexdigest() for n in members} != receipt["sources"]
                or any(sources.read(n) != (prepare.HERE / n).read_bytes() for n in FILES)
                or any(receipt["sources"]["compiled/" + n] != pair[1] for n, pair in pins.items())
                or sources.read("compiled/" + GATE) != sources.read("deferred_gate.rs")):
            raise ValueError("Invalid deferred source supplement")
    compiled = receipt["compilerSources"]
    original_trees = prior["source"]["trees"]
    if (set(configuration["libraries"]) != {"eframe", "egui-wgpu"}
            or compiled["libraries"] != {**original_trees, **configuration["libraries"]}
            or compiled["application"] != {**prior["source"]["application"], "graphics.rs": pins["src/graphics.rs"][1]}):
        raise ValueError("An unrelated library or GUI source differs from the native frame diagnostic")
    idle_log = out / "rust-1-idle-presents.log"
    idle_lines = idle_log.read_text(encoding="ascii").splitlines()
    if (sha(idle_log) != record["idlePresentsSha256"] or not idle_lines or idle_lines[0] != "READY"
            or idle_lines[-1] != "COMPLETE" or sum(s.startswith("P ") for s in idle_lines) != record["trial"]["presentation"]["acceptedPresents"]):
        raise ValueError("Incomplete idle presentation trace")
    messages = [json.loads(row) for row in (out / "compiler.jsonl").read_bytes().splitlines()]
    if not messages or messages[-1] != {"reason":"build-finished","success":True} or sum(m["reason"] == "build-finished" for m in messages) != 1:
        raise ValueError("Incomplete native x64 compiler stream")
    units = [m for m in messages if m["reason"] == "compiler-artifact"]
    app, = [m for m in units if m["target"]["kind"] == ["bin"] and m["target"]["name"] == receipt["application"]["target"]]
    project = PureWindowsPath(app["manifest_path"]).parent
    exe = PureWindowsPath(app["executable"])
    if (not app["package_id"].startswith("path+file:") or PureWindowsPath(app["target"]["src_path"]) != project / "src/main.rs"
            or exe.name != receipt["application"]["output"] or exe.parent.name != "release"
            or [PureWindowsPath(n) for n in app["filenames"]].count(exe) != 1 or set(receipt["libraries"]) != set(prepare.LIBS)):
        raise ValueError("Unexpected native compiler executable or library set")
    for name, relative in prepare.LIBS.items():
        library = receipt["libraries"][name]
        unit, = [m for m in units if m["target"]["kind"] == ["lib"] and m["target"]["name"] == name.replace("-","_")]
        if (not unit["package_id"].startswith("path+file:") or PureWindowsPath(unit["manifest_path"]) != project / relative / "Cargo.toml"
                or PureWindowsPath(unit["target"]["src_path"]) != project / relative / "src/lib.rs"
                or sorted(unit["features"]) != prior["libraries"][name]["features"] or sorted(unit["features"]) != library["features"]
                or not release_outputs([PureWindowsPath(f) for f in unit["filenames"]], library["outputs"], exe, unit["target"]["name"])):
            raise ValueError("The native deferred comparison selected a different library")
    row = record["trial"]
    replay_scan(out, "rust-1", row)
    resource_samples(row)
    phases = (("idle", "rust-1.log"), ("scan", "rust-1-scan.log"), ("edit", "retained-edit/subject.log"))
    observations = {name: summary(out / path) for name, path in phases}
    samples = {name: observed[0] for name, observed in observations.items()}
    scan = row["scan"]
    verified = matched_presents((out / "rust-1-scan-presents.log").read_text(encoding="ascii").splitlines(),
                             scan["guiPid"], scan["presentation"]["firstPassBoundsQpc"], observations["scan"][1], scan["allRequests"])
    edit = visible_edit(out / "retained-edit", record["edit"], 1, wait_policy="DontWait")
    return dict(samples=samples, edit=edit, verifiedResumedScanPresents=verified, workQualifiedResponses=len(row["scan"]["eligibleResponses"]),
                successfulScanPresents=row["scan"]["presentation"]["successfulPresents"],
                singleTrial={k:dict(wpfMaximum=budget["maximums"][k], ordinaryMedian=primary["comparison"][k]["candidate"],
                                     deferred=row["metrics"][k]) for k in METRICS})


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    report = json.loads((folder / "result.json").read_bytes())
    if report["status"] != "deferred-frame-observed" or readback(folder, report) != report["checks"]:
        raise ValueError("The native deferred-frame readback differs")
    print(json.dumps(report["checks"]["singleTrial"], indent=2))
