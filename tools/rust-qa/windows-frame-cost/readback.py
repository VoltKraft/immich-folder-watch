"""Join owned per-thread measurements to successful DXGI calls and external HWND requests."""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath
from zipfile import ZipFile
from hashlib import sha256
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows-warm-window"))
import dispatch
import prepare
from frame_latency import HOST_BUILD, measured_generation, replay_scan
from inputs import recorder, sha
from metrics import METRICS

FRAME_ORDER = ("update", "tessellate", "prepare", "acquire", "draw", "encode", "submit", "present")
VISIBILITY = {"direct", "flags", "flag-show", "flag-hide", "flag-max", "flag-min", "show-call", "hide-call"}
STAGES = set(FRAME_ORDER) | VISIBILITY | {"frame", "dx12-wait", "dx12-no-object"}
CAPACITY = 262_144


def read_spans(text, pid, frequency):
    lines = [line.split() for line in text.splitlines() if line.startswith("FRAME")]
    if (len(lines) < 4 or lines[0] != ["FRAME_BEGIN", str(pid), str(frequency), str(len(lines) - 2), "0"]
            or lines[-1] != ["FRAME_END"] or len(lines) - 2 > CAPACITY or frequency <= 0):
        raise ValueError("Missing, incomplete or foreign native frame trace")
    active = defaultdict(list)
    nodes = {}
    clock = {}
    seen = Counter()
    for r in lines[1:-1]:
        if len(r) != 16 or r[0] != "FRAME" or r[3] not in STAGES:
            raise ValueError("Unknown native measurement")
        ident, parent = int(r[1]), int(r[2])
        ending, tid, lo, hi, status, switches, reasons, cycles, value, begin, finish, hwnd = map(int, r[4:])
        if (min(ident, tid, lo) <= 0 or lo > hi or lo < clock.get(tid, 0) or ending not in (0, 1)
                or not 0 <= status <= 0xffffffff or not 0 <= switches <= 0xffffffff or not 0 <= reasons < 2**64
                or cycles < (-1 if status else 0) or (status and (switches or reasons))):
            raise ValueError("Invalid thread, timestamp order or scheduler sample")
        clock[tid] = hi
        seen[status] += 1
        stack = active[tid]
        # Windows returns wait reasons since the preceding read on this exact thread.
        for ancestor in stack:
            nodes[ancestor]["reasons"] |= reasons
            nodes[ancestor]["completeScheduler"] &= status == 0
        stage = r[3]
        if not ending:
            if (begin, finish, hwnd) != (0, 0, 0) or len(stack) >= 64 or ident in nodes or parent != (stack[-1] if stack else 0):
                raise ValueError("Repeated span or foreign parent")
            nodes[ident] = dict(id=ident, parent=parent, stage=stage, tid=tid, low=lo, entryAfterQpc=hi, start=hi, arg=value,
                firstStatus=status, firstCycles=cycles, firstSwitches=switches, reasons=0, completeScheduler=status == 0)
            stack.append(ident)
        else:
            if not stack or stack.pop() != ident:
                raise ValueError("Non-nested span exit")
            n = nodes[ident]
            if (stage, tid, parent) != (n["stage"], n["tid"], n["parent"]) or lo < n["start"]:
                raise ValueError("A native span changed stage or thread")
            if (not n["start"] <= begin <= finish <= lo
                    or (r[3] in ("direct", "flag-show", "flag-hide", "flag-max", "flag-min")) != (hwnd > 0)
                    or any(not begin <= nodes[child]["start"] <= nodes[child]["end"] <= finish for child in n.pop("children", []))):
                raise ValueError("Native API timestamps or HWND differ from the frame scope")
            if parent:
                nodes[parent].setdefault("children", []).append(ident)
            diff = cycles - n["firstCycles"] if n["firstCycles"] >= 0 and cycles >= 0 and (n["firstStatus"] == 0) == (status == 0) else None
            cs = switches - n["firstSwitches"] if n["completeScheduler"] else None
            if (cs is not None and cs < 0) or (diff is not None and diff < 0):
                raise ValueError("Nonmonotonic thread counters")
            n.update(start=begin, end=finish, high=hi, exitBeforeQpc=lo, result=value, cycles=diff, switches=cs, hwnd=hwnd,
                     lastStatus=status, lastCycles=cycles, lastSwitches=switches)
    if any(active.values()):
        raise ValueError("The GUI exited with open diagnostic spans")
    return nodes, dict(sorted(seen.items()))


def ancestor(nodes, n, stage):
    while n["stage"] != stage and n["parent"]:
        n = nodes[n["parent"]]
    return n["id"] if n["stage"] == stage else None


def complete_frame(frame, rows):
    groups = defaultdict(list)
    for n in rows:
        groups[n["stage"]].append(n)
    if any(len(groups[label]) != 1 for label in FRAME_ORDER):
        raise ValueError("A presented frame lacks a unique update, draw, acquire, submit or present")
    stages = [groups[label][0] for label in FRAME_ORDER]
    if any(n["parent"] != frame for n in stages) or any(a["end"] > b["start"] for a, b in zip(stages, stages[1:])):
        raise ValueError("A presented frame has out-of-order renderer stages")
    acquire = groups["acquire"][0]
    waits = groups["dx12-wait"]
    if (groups["dx12-no-object"] or not waits or any(n["parent"] != acquire["id"] or n["arg"] < 0 for n in waits)
            or any(n["result"] not in (0, 258) for n in waits)):
        raise ValueError(f"Frame {frame} lacks an observed DX12 signal or timeout inside acquire")
    return waits


def analyze(text, dxgi, scan, limits):
    source = dispatch.correlate(text, dxgi, scan, False)
    problem = dispatch.hidden_failure("root-repaint", source["hidden"])
    if problem:
        raise ValueError(problem)
    pid, tid, hz, hwnd = (source[k] for k in ("guiPid", "uiThread", "frequency", "hwnd"))
    nodes, status = read_spans(text, pid, hz)
    children = defaultdict(list)
    frames = defaultdict(list)
    for n in nodes.values():
        children[n["parent"]].append(n)
        f = ancestor(nodes, n, "frame")
        if f is not None:
            frames[f].append(n)
    ui = [n for n in nodes.values() if n["tid"] == tid]
    presents = sorted((n for n in ui if n["stage"] == "present"), key=lambda n:n["start"])
    starts = [n["start"] for n in presents]
    first, last = scan["presentation"]["firstPassBoundsQpc"]
    observed = set()
    wait_results = Counter()
    timed_out = []
    for line in dxgi.splitlines():
        if not line.startswith("DXGI "):
            continue
        process, thread, interval, flags, a, b = map(int, line.split()[1:])
        if not first <= a <= b <= last:
            continue
        i = bisect_right(starts, a) - 1
        if i < 0 or (process, thread, interval, flags&0x201) != (pid, tid, 0, 0) or b > presents[i]["end"]:
            raise ValueError("A real DXGI present has no enclosing UI-thread submission")
        f = ancestor(nodes, presents[i], "frame")
        if f is None or f in observed:
            raise ValueError("Missing or ambiguous eframe frame")
        observed.add(f)
        for wait in complete_frame(f, frames[f]):
            wait_results[str(wait["result"])] += 1
            if wait["result"] == 258:
                timed_out.append(dict(frame=f, requestedMs=wait["arg"], waitQpc=[wait["start"], wait["end"]],
                                      dxgiPresentQpc=[a, b]))
    if len(observed) != scan["presentation"]["successfulPresents"] or len(observed) < 5:
        raise ValueError("Incomplete coverage of the original successful DXGI events")
    spans = dispatch.parse(text, pid, hz, False)
    calls = sorted((n for n in ui if n["stage"] in ("show-call", "hide-call")), key=lambda n:n["low"])
    starts = [n["low"] for n in calls]
    paths = Counter()
    for operation in (s for s in spans if s["label"] in ("show", "hide")):
        lo = bisect_left(starts, operation["start"])
        hi = bisect_right(starts, operation["end"])
        candidates = [n for n in calls[lo:hi] if n["stage"] == operation["label"] + "-call" and n["high"] <= operation["end"]]
        if len(candidates) != 1 or candidates[0]["arg"] != hwnd:
            raise ValueError("Missing exact HWND visibility boundary")
        call, = candidates
        routes = [n for n in children[call["id"]] if n["stage"] in ("flags", "direct")]
        if len(routes) != 1:
            raise ValueError("Missing or ambiguous winit visibility route")
        route, = routes
        action = operation["label"]
        commands = (0,) if action == "hide" else (4, 5)
        effective = operation["before"] != operation["after"]
        if route["stage"] == "direct":
            if route["arg"] not in commands or route["hwnd"] != hwnd:
                raise ValueError("The direct ShowWindow command differs from the visibility request")
            path = "direct"
        else:
            native = [n for n in children[route["id"]] if n["stage"] in ("flag-show", "flag-hide")]
            if (len(native) > 1 or (effective and not native) or
                    any(n["stage"] != "flag-" + action or n["arg"] not in commands or n["hwnd"] != hwnd for n in native)):
                raise ValueError("The flags path lacks its effective native ShowWindow command")
            path = "flags-with-ShowWindow" if native else "flags-without-ShowWindow"
        paths[f"{action}:{path}"] += 1
    factor = 1000 / hz
    slow = []
    previous = 0
    for q in scan["eligibleResponses"]:
        a, b = q["issuedQpc"], q["responseQpc"]
        if q["hwnd"] != hwnd or b < a or a <= previous:
            raise ValueError("Invalid external response order or HWND")
        previous = b
        if (b - a) * factor > limits["scan_" + q["action"] + "_p95_ms"]:
            slow.append({**q, "overlapMs":{}, "last":{}, "samples":[], "frames":set()})
    ends = [r["responseQpc"] for r in slow]
    for n in sorted(ui, key=lambda n:n["start"]):
        start, end = n["start"], n["end"]
        i = bisect_right(ends, start)
        while i < len(slow) and slow[i]["issuedQpc"] < end:
            r = slow[i]
            a, b = r["issuedQpc"], r["responseQpc"]
            label = n["stage"]
            if min(b, end) > max(a, start):
                last = r["last"].get(label, 0)
                ticks = max(0, min(b, end) - max(last, a, start))
                r["last"][label] = max(last, min(b, end))
                r["overlapMs"][label] = r["overlapMs"].get(label, 0) + ticks * factor
                r["samples"].append(n["id"])
                frame = ancestor(nodes, n, "frame")
                if frame in observed:
                    r["frames"].add(frame)
            i += 1
    for r in slow:
        del r["last"]
        r["frames"] = sorted(r["frames"])
    return dict(pid=pid, thread=tid, hwnd=hwnd, frequency=hz, hidden=source["hidden"], visibilityPaths=dict(paths),
                verifiedPresentedFrames=len(observed), waitResults=dict(wait_results), presentedAfterTimeout=timed_out,
                schedulerReadStatuses={str(k):v for k, v in status.items()}, schedulerComplete=set(status) == {0},
                slowResponses=slow)

TRIAL = "rust-1-scan"
FILES = ("prepare.py", "probes.patch", "sources.json", "trace.rs", "readback.py", "frame_case.py")
RAW = (".log", "-files.log", "-presents.log", "-requests.json")


def inputs():
    return {name: sha(HERE / name) for name in FILES}


def raw_hashes(out):
    return {TRIAL + suffix: sha(out / (TRIAL + suffix)) for suffix in RAW}


def pair(base, report):
    primary_file = base / "measured/result.json"
    dispatch_file = base / "dispatch/result.json"
    primary = json.loads(primary_file.read_bytes())
    regular = json.loads(dispatch_file.read_bytes())
    paired = {**report, "binary": report["pairedBinary"]}
    fields = (*HOST_BUILD, "referenceBudgetSha256", "observerInputs")
    original_observers = {name: sha(prepare.WARM / name) for name in ("measure.py", "frame_latency.py", "inputs.py", "scan_present.py")}
    if (report["observerInputs"] != original_observers or any(record[k] != paired[k] for k in fields for record in (primary, regular))
            or primary["status"] not in ("measured-metrics-passed", "over-budget")
            or regular["status"] != "dispatch-observed" or regular["primaryResultSha256"] != sha(primary_file)
            or regular["dispatchObserverSha256"] != sha(prepare.WARM / "dispatch.py")
            or primary["diagnosticControl"] or not regular["diagnosticControl"]
            or any(record["presentMode"] != "Mailbox" or record["desiredMaximumFrameLatency"] != 1
                   or record["inputs"]["inventory"]["gui"] != paired["binary"] for record in (primary, regular))
            or len(primary["trials"]) != recorder.TRIALS
            or set(primary["comparison"]) != set(METRICS)
            or any(type(primary["comparison"][k]["passed"]) is not bool for k in METRICS)
            or primary["inputs"]["workload"] != regular["inputs"]["workload"]):
        raise ValueError("The ordinary dispatch and measured subjects or their original WPF budget differ")
    return {"measuredSha256": sha(primary_file), "dispatchSha256": sha(dispatch_file)}


def release_outputs(files, expected, app, target):
    """Cargo can place rlibs under release/build/<crate>/<hash>/out or release/deps."""
    if not files or len(files) != len(set(files)) or not all(f.is_relative_to(app.parent) for f in files):
        return False
    libraries = [f for f in files if f.suffix == ".rlib" and
                 (f.stem == "lib" + target or f.stem.startswith("lib" + target + "-"))]
    relative = {f.relative_to(app.parent.parent).as_posix() for f in files}
    return len(libraries) == 1 and relative == set(expected)


def compiler_receipt(out, report):
    base = out.parent
    ordinary = json.loads((base / "build.json").read_bytes())
    receipt = json.loads((out / "diagnostic-build.json").read_bytes())
    sources = receipt["source"]
    binary = out / "diagnostic.exe"
    stream = out / "compiler.jsonl"
    archive = out / "source.zip"
    if (sha(base / "build.json") != report["buildReceipt"] or receipt["pairedBuildSha256"] != report["buildReceipt"]
            or ordinary["revision"] != report["revision"] or ordinary["target"] != prepare.TARGET
            or ordinary["binary"] != report["pairedBinary"] or receipt["pairedBinary"] != ordinary["binary"]
            or receipt["nativeCompiler"] != ordinary["nativeCompiler"]
            or sha(base / "compiler.jsonl") != ordinary["compilerEvidence"]["sha256"]
            or receipt["pairedCompiler"] != ordinary["compilerEvidence"]["sha256"]
            or receipt["compilerSha256"] != sha(stream) or sources["archive"] != sha(archive)
            or sha(out / "diagnostic-build.json") != report["diagBuildSha256"]
            or report["binary"] != sha(binary) or report["binary"] == report["pairedBinary"]
            or recorder.pe_machine(binary) != 0x8664
            or sources["ordinaryInputs"] != ordinary["compilerInputs"]
            or sources["ordinarySource"] != ordinary["eframeSource"]["archiveSha256"]
            or sources["ordinarySource"] != sha(base / "eframe-source.zip")
            or receipt["application"] != dict(target="native-gui-assessment", crateRoot="src/main.rs",
                                               output="native-gui-assessment.exe", sha256=report["binary"])):
        raise ValueError("The diagnostic PE, compiler, ordinary binary or sources differ from their original receipts")
    app_sources = dict(ordinary["compilerInputs"])
    app_sources["ui_trace.rs"] = prepare.PINS["patchSources"]["src/ui_trace.rs"]["after"]
    if sources["application"] != app_sources:
        raise ValueError("A diagnostic application input changed outside the measured trace")
    with ZipFile(archive) as z:
        prepare.verify_compiler_sources(z.read, sources["trees"])
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError("Duplicate source archive member")
        for name in ("sources.json", "probes.patch", "prepare.py", "trace.rs"):
            if z.read(name) != (HERE / name).read_bytes():
                raise ValueError("The original compiler source archive differs from this diagnosis")
        if (z.read("ordinary-source.zip") != (base / "eframe-source.zip").read_bytes()
                or z.read("notices/ifw-frame-timing/LICENSE") != (prepare.ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")):
            raise ValueError("The original ordinary sources or diagnostic license changed")
        for name, pin in prepare.PINS["packages"].items():
            member = f"{name}-{pin['version']}.crate"
            if sha256(z.read(member)).hexdigest() != pin["archiveSha256"]:
                raise ValueError("A diagnostic source archive differs from its pinned crate")
            for notice, expected in pin["noticeSha256"].items():
                if sha256(z.read(f"notices/{name}/{notice}")).hexdigest() != expected:
                    raise ValueError("A source notice changed")
        pins = ordinary["eframeSource"]["pins"]
        for name, entry in pins["notices"].items():
            if name.startswith("eframe/") and sha256(z.read("notices/egui-wgpu/" + Path(name).name)).hexdigest() != entry["sha256"]:
                raise ValueError("The original egui-wgpu notice differs")
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    success = {"reason": "build-finished", "success": True}
    if not messages or messages[-1] != success or sum(m["reason"] == "build-finished" for m in messages) != 1:
        raise ValueError("The native compiler did not finish the diagnostic build")
    units = [m for m in messages if m["reason"] == "compiler-artifact"]
    app, = [m for m in units if m["target"]["kind"] == ["bin"] and m["target"]["name"] == receipt["application"]["target"]]
    project = PureWindowsPath(app["manifest_path"]).parent
    binary_out = PureWindowsPath(app["executable"])
    if (not app["package_id"].startswith("path+file:") or PureWindowsPath(app["target"]["src_path"]) != project / "src/main.rs"
            or binary_out.name != receipt["application"]["output"] or binary_out.parent.name != "release"
            or [PureWindowsPath(f) for f in app["filenames"]].count(binary_out) != 1
            or set(receipt["libraries"]) != set(prepare.LIBS)):
        raise ValueError("The recorded diagnostic compiler binary or library set differs")
    for name, relative in prepare.LIBS.items():
        unit, = [m for m in units if m["target"]["kind"] == ["lib"] and m["target"]["name"] == name.replace("-", "_")]
        library = receipt["libraries"][name]
        files = [PureWindowsPath(f) for f in unit["filenames"]]
        if (not unit["package_id"].startswith("path+file:") or library["manifest"] != (relative / "Cargo.toml").as_posix()
                or library["crateRoot"] != (relative / "src/lib.rs").as_posix()
                or PureWindowsPath(unit["manifest_path"]) != project / library["manifest"]
                or PureWindowsPath(unit["target"]["src_path"]) != project / library["crateRoot"]
                or sorted(unit["features"]) != library["features"]
                or not release_outputs(files, library["outputs"], binary_out, unit["target"]["name"])):
            raise ValueError(f"The original compiler unit for {name} differs")


def recalculate(out, report):
    if (report["target"] != prepare.TARGET or not report["diagnosticControl"] or report["presentMode"] != "Mailbox"
            or report["desiredMaximumFrameLatency"] != 1 or report["pair"] != pair(out.parent, report)
            or report["diagnosticInputs"] != inputs() or report["raw"] != raw_hashes(out)):
        raise ValueError("Wrong source, runner, workload or native observation")
    reference_path = out / "reference-budget.json"
    budget = json.loads(reference_path.read_bytes())
    primary = json.loads((out.parent / "measured/result.json").read_bytes())
    if (sha(reference_path) != report["referenceBudgetSha256"]
            or budget["maximums"] != recorder.budgets(budget["reference"])
            or primary["comparison"] != recorder.comparison(budget["maximums"], recorder.summarize(primary["trials"]))
            or primary["inputs"]["workload"] != report["inputs"]["workload"]
            or any(report["inputs"]["inventory"][k] != primary["inputs"]["inventory"][k]
                   for k in ("compiledEntry", "approvedBundle", "packages", "sources"))
            or report["inputs"]["inventory"]["gui"] != report["binary"]):
        raise ValueError("The original frozen WPF limits or workload changed")
    compiler_receipt(out, report)
    scan = report["scan"]
    if (scan["inventoryCreation100ns"] <= 0 or scan["presentation"]["guiCreation100ns"] <= 0
            or set(scan["rootWindowEvents"]) != {"hide", "show"} or min(scan["rootWindowEvents"].values()) < 5):
        raise ValueError("Insufficient live creation identities or HWND events")
    replay_scan(out, "rust-1", {"scan":scan, "metrics":scan["metrics"]})
    subject = out / (TRIAL + ".log")
    log = subject.read_text(encoding="utf-8")
    if (measured_generation(subject, "Mailbox", dispatch_trace=True) != scan["device"]
            or any(r.startswith(("WINDOW_WAKE ", "WINDOW_HIDDEN_PAINT ")) for r in log.splitlines())):
        raise ValueError("A different device or visibility policy was measured")
    return analyze(log, (out / (TRIAL + "-presents.log")).read_text(encoding="ascii"), scan, budget["maximums"])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--span", type=int, help="print the original counters for one reported sample")
    args = parser.parse_args()
    data = json.loads((args.folder / "result.json").read_bytes())
    result = recalculate(args.folder, data)
    if result != data["cost"] or data["status"] != "frame-cost-observed":
        raise ValueError("The saved stage diagnosis differs from the native originals")
    if args.span is not None:
        text = (args.folder / (TRIAL + ".log")).read_text(encoding="utf-8")
        nodes, _ = read_spans(text, result["pid"], result["frequency"])
        print(json.dumps(nodes[args.span], indent=2))
    else:
        print(json.dumps({k:v for k, v in result.items() if k != "slowResponses"}, indent=2))
