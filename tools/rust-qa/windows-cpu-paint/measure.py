"""Measure CPU-painted egui frames on the retained x64 root against the same runner's WPF limits."""
import argparse
from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
QA = HERE.parent
sys.path.insert(0, str(QA / "windows-warm-window"))
from inputs import ROOT, recorder, sha
import dwm_transitions as dwm
from frame_latency import visible_edit
from metrics import METRICS
from native import CleanupUnconfirmed
from observe import observer_inputs
from window_lifetime import WindowLifetime

sys.path.extend(str(QA / directory) for directory in ("windows-gdi-present", "windows-frame-cost"))
import gdi_case as gdi
from frame_ready_case import job_resources, native_window, resource_metrics, scan_views

MODE = "CPU_PAINT_MODE backend=Dx12 device=Cpu selection=adapter"
CPU = re.compile(r"CPU_FRAME seq=(\d+) pid=(\d+) hwnd=(\d+) tid=(\d+) begin=(\d+) rasterEnd=(\d+) "
                 r"start=(\d+) end=(\d+) width=(\d+) height=(\d+) meshes=(\d+) vertices=(\d+) "
                 r"indices=(\d+) sets=(\d+) frees=(\d+) lines=(\d+) flushed=1")
RAW = ("rust-1.log", "rust-1-idle-presents.log", "rust-1-scan.log", "rust-1-scan-files.log",
       "rust-1-scan-requests.json", "rust-1-scan-presents.log", "editor-presents.log", "scan-editor/hosts.json")
SOURCES = (HERE / "measure.py", QA / "windows-gdi-present/gdi_case.py",
           QA / "windows-frame-cost/frame_ready_case.py", QA / "windows-performance/metrics.py")


def verify_build(out, record):
    import cpu_build
    cpu_build.verify(out, record)


def check_device_lifetime(lines):
    # Graphics::finish marks the generation RELEASED before dropping its device.
    # The lost callback reports only when it changes ACTIVE to LOST, even for reason=Destroyed.
    phases = ("GRAPHICS_ATTEMPT ", "GRAPHICS_MEMORY ", "GRAPHICS_READY ", "GRAPHICS_LOST ",
              "GRAPHICS_ERROR ", "GRAPHICS_RETRY ", "GRAPHICS_UNAVAILABLE ")
    observed = [line for line in lines if line.startswith(phases)]
    if observed != ["GRAPHICS_ATTEMPT generation=1 policy=preferred", "GRAPHICS_MEMORY generation=1 hint=MemoryUsage",
                    "GRAPHICS_READY generation=1"]:
        raise ValueError(f"Expected one retained WARP device without loss or retry, observed {observed}")


def generation(log):
    lines = log.read_text(encoding="utf-8").splitlines()
    check_device_lifetime(lines)
    for prefix, expected in (("CPU_PAINT_MODE", MODE), ("ADAPTER ", "ADAPTER Dx12 Cpu Microsoft Basic Render Driver")):
        if [line for line in lines if line.startswith(prefix)] != [expected]:
            raise ValueError("Missing the retained CPU painter or the original WARP adapter initialization")
    if (sum(line.startswith("DRAINED passes=") for line in lines) != 1
            or any(line.startswith(("STAGING_", "GDI_PRESENT_MODE", "DWM_TRANSITIONS", "DEFERRED_FRAME", "FRAME_READY_"))
                   for line in lines)):
        raise ValueError("The CPU subject did not drain or ran an unrelated renderer control")
    return dict(generation=1, adapter="Dx12 Cpu Microsoft Basic Render Driver", painter="CPU", transfer="GDI")


def frames(text, root, hz):
    """Join actual GDI returns to CPU paint calls; clear-only transfers still count toward the idle rate."""
    if any(type(root[k]) != int or root[k] <= 0 for k in ("pid", "hwnd", "tid", "width", "height")) or type(hz) != int or hz <= 0:
        raise ValueError("Missing native clock, HWND or dimensions")
    series = gdi.FrameSeries([], [], [])
    costs = []
    partial = full = painted = clear_only = mesh_count = texture_sets = texture_frees = 0
    previous = 0
    active = done = False
    pending = None
    for line in text.splitlines():
        if line.startswith(("STAGING_", "GDI_PRESENT_MODE")):
            raise ValueError("Unexpected GPU readback or alternate root renderer")
        if not line.startswith(("CPU_", "GDI_")):
            continue
        if done:
            raise ValueError("Renderer records after the final transfer count")
        if line == MODE and not active:
            active = True
            continue
        if not active:
            raise ValueError("Transfer before verified CPU mode")
        if full and pending is None and line == f"GDI_PRESENT_END frames={full} partial={partial}":
            done = True
            continue
        blit = gdi.FRAME.fullmatch(line)
        if blit and pending is None:
            complete = blit.group(1) == "PRESENT"
            number, hwnd, tid, start, end, width, height, lines = map(int, blit.groups()[1:])
            if (number != (full if complete else partial) + 1 or (hwnd, tid) != (root["hwnd"], root["tid"])
                    or (width, height) != (root["width"], root["height"]) or not previous <= start <= end
                    or start <= 0 or lines > height or (complete and lines != height)):
                raise ValueError("Foreign, overlapping or misclassified GDI transfer")
            pending = (complete, (hwnd, tid, start, end, width, height, lines))
            continue
        entry = CPU.fullmatch(line)
        if not entry or pending is None:
            raise ValueError("Unmatched CPU paint or GDI transfer")
        seq, pid, hwnd, tid, begin, raster_end, start, end, width, height, meshes, vertices, indices, sets, frees, lines = map(int, entry.groups())
        complete, original = pending
        if (seq != len(costs) + 1 or pid != root["pid"] or original != (hwnd, tid, start, end, width, height, lines)
                or not 0 < begin <= raster_end <= start or begin < previous or indices % 3
                or (not meshes and (vertices or indices)) or (indices and vertices < 3)):
            raise ValueError("CPU paint does not match its real PID, geometry, transfer or ordered clock")
        if complete:
            full += 1
            if meshes and indices:
                series.complete.append((start, end))
            else:
                clear_only += 1
        else:
            partial += 1
        if indices:
            painted += 1
        mesh_count += meshes
        texture_sets += sets
        texture_frees += frees
        (series.positive if lines else series.empty).append((start, end))
        costs.append(((raster_end-begin)*1000/hz, (end-start)*1000/hz))
        previous, pending = end, None
    if not done or not series.complete:
        raise ValueError("Missing a full mesh-bearing CPU frame or its final transfer count")
    return series, dict(transfers=len(costs), fullTransfers=full, partialTransfers=partial, clearOnlyFull=clear_only,
                        meshBearingTransfers=painted, meshes=mesh_count, textureSets=texture_sets, textureFrees=texture_frees,
                        cpuPaintP95Ms=recorder.p95([a for a,_ in costs]), dibAndFlushP95Ms=recorder.p95([b for _,b in costs]))


def idle_result(out, row):
    original = out / "rust-1.log"
    source = original.read_text(encoding="utf-8")
    root = row["frameWindows"]["root"]
    series, cost = frames(source, root, row["frameWindows"]["frequency"])
    idle = gdi.idle_observation(row, series, (out / "rust-1-idle-presents.log").read_text(encoding="ascii"))
    tree = {int(k): v for k,v in row["controls"]["wholeProcessTree"].items()}
    workers = [pid for pid, info in tree.items() if info["parent"] == root["pid"] and info["image"].lower() == "ifw-performance-worker.exe"]
    if (len(workers) != 1 or re.findall(r"^INVENTORY_WORKER pid=(\d+)$", source, re.M) != [str(workers[0])]
            or not recorder.idle_complete(source) or any(pid <= 0 or info["creation100ns"] <= 0 for pid,info in tree.items())):
        raise ValueError("Missing the original idle GUI, worker or two completed inventories")
    for sample in row["idleSamples"].values():
        job_resources(sample, root["pid"], workers[0], tree.keys())
    return dict(device=generation(original), cost=cost, **idle)


def editor_result(out, row, series):
    scan = row["scan"]
    edit = scan["editor"]
    root = scan["presentation"]["root"]
    hwnd = root["hwnd"]
    if (edit["root"] != {k: root[k] for k in ("pid", "tid", "hwnd")}
            or edit["creation100ns"] != scan["presentation"]["guiCreation100ns"]
            or edit["creation100ns"] <= row["frameWindows"]["guiCreation100ns"]
            or scan["termination"] != {"method": "control-Q", "exitCode": 0}
            or [e[1] for e in edit["rootLifetimes"] if e[0] == hwnd] != ["create"]
            or [(e["event"], e["hwnd"], e["root"]) for e in edit["rootEvents"]] != [("hide", hwnd, True), ("show", hwnd, True)]):
        raise ValueError("The edited process or root differs from the one that performed the scan")
    clocks = edit["editorClocks"]
    begin_etw, end_etw = edit["presentationQpc"]
    gdi.no_swapchain((out / "editor-presents.log").read_text(encoding="ascii"), root["pid"], row["frameWindows"]["frequency"])
    first, last = (edit["fields"][name] for name in ("before","after"))
    if (first["root"] != root or last["root"] != root or not
            scan["presentation"]["traceBoundsQpc"][1] <= begin_etw <= clocks[0] <= first["qpc"][0] < first["qpc"][1] <= clocks[1]
            < clocks[2] <= last["qpc"][0] < last["qpc"][1] <= clocks[3] <= end_etw):
        raise ValueError("The independent editor inputs were outside their observed visible root intervals")
    counts = [gdi.inside(series.complete, field["qpc"]) for field in (first, last)]
    if not all(counts):
        raise ValueError("Missing a complete mesh-bearing transfer during one of the visible edits")
    view = visible_edit(out / "scan-editor", edit, 1, device_observer=generation, subject_log=out / "rust-1-scan.log")
    return dict(**view, fullMeshTransfers=dict(before=counts[0], after=counts[1]))


def sources(revision):
    paths = (*SOURCES, *((dwm.HERE / name).resolve() for name in dwm.INPUTS))
    observed = {**observer_inputs(), **{p.relative_to(ROOT).as_posix(): sha(p) for p in paths}}
    data = subprocess.check_output(["git", "archive", "--format=tar", revision, "--", *observed], cwd=ROOT)
    with tarfile.open(fileobj=BytesIO(data), mode="r:") as archive:
        committed = {f.name: sha256(archive.extractfile(f).read()).hexdigest() for f in archive if f.isfile()}
    if observed != committed:
        raise ValueError("The CPU, input, inventory, ETW or pixel observer differs from its recorded Git revision")
    return observed


def resource_comparison(metrics, limits, ordinary):
    if set(metrics) != set(METRICS) or set(limits) != set(METRICS) or set(ordinary) != set(METRICS):
        raise ValueError("All eleven same-host WPF limits and measured metrics are required")
    values = recorder.comparison(limits, metrics)
    for name, row in values.items():
        if ordinary[name]["maximum"] != row["maximum"] or ordinary[name]["passed"] is None or row["passed"] is None:
            raise ValueError("The frozen WPF and ordinary single-metric comparison differs")
        row["ordinaryMedian"] = ordinary[name]["candidate"]
    return dict(status="within-limits" if all(r["passed"] for r in values.values()) else "over-budget", metrics=values)


def reopen_delivery(eligible, frames, frequency):
    reopens = [event for event in eligible if event["action"] == "reopen"]
    requests = {event["responseQpc"]: event["issuedQpc"] for event in reopens}
    visible = {frame["hwndVisibleQpc"] for frame in frames}
    if (frequency <= 0 or not frames or len(requests) != len(reopens)
            or len(visible) != len(frames) or not visible.issubset(requests)):
        raise ValueError("Cannot match full frames to distinct eligible reopens")
    delays = []
    for frame in frames:
        observed = frame["hwndVisibleQpc"]
        issued = requests[observed]
        if not issued <= observed <= frame["fullBlitStartQpc"] <= frame["flushReturnedQpc"]:
            raise ValueError("CPU frame preceded its window request or observation")
        delays.append((frame["flushReturnedQpc"] - issued) * 1000 / frequency)
    return dict(eligibleReopens=len(reopens), reopensWithFullBlit=len(delays),
                requestToFirstFullBlitP95Ms=recorder.p95(delays))


def readback(out, record):
    baseline = out.parents[2] / "windows-performance" / ("native-" + dwm.TARGET)
    refs = dwm.references(out, record, baseline, separate_gui=True, candidate_presentation=("CPU-GDI", None))
    verify_build(out, record)
    if (sha(out / "reference-budget.json") != record["referenceBudgetSha256"]
            or record["sources"] != sources(record["revision"]) or record["raw"] != {n: sha(out / n) for n in RAW}
            or record["inputs"]["workload"]["files"] != 100_000):
        raise ValueError("The frozen WPF limits, workload, observers or native originals differ")
    row = record["trial"]
    idle = idle_result(out, row)
    if row["presentation"] != idle or any(row["metrics"][key] != value for key,value in idle["rates"].items()):
        raise ValueError("Idle presentation rates differ from the actual CPU transfers")
    resource_metrics(row)
    scan = row["scan"]
    root = scan["presentation"]["root"]
    meta = dwm.read(out / "rust-1-scan-requests.json")
    if (meta["frequency"] != row["frameWindows"]["frequency"] or set(scan["rootWindowEvents"]) != {"hide", "show"}
            or min(scan["rootWindowEvents"].values()) < 5):
        raise ValueError("The original QPC clock or independently observed HWND transitions differ")
    scan_views(row["views"], meta["requests"], root["hwnd"])
    original = out / "rust-1-scan.log"
    generation(original)
    series, cost = frames(original.read_text(encoding="utf-8"), root, meta["frequency"])
    progress = gdi.scan_observation(out, row, series)
    delivery = reopen_delivery(scan["eligibleResponses"], progress["firstFullBlitAfterObservedReopen"], meta["frequency"])
    pixels = editor_result(out, row, series)
    budget = dwm.read(out / "reference-budget.json")["maximums"]
    ordinary = dwm.read(out.parent / "measured/result.json")["comparison"]
    return dict(references=refs, idle=idle, scan=dict(**progress, cost=cost, delivery=delivery), editor=pixels,
                resources=resource_comparison(row["metrics"], budget, ordinary))


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget):
    if not files or not present or sha(gui) != record["binary"]:
        raise ValueError("The native CPU painter and both ETW observers are required")
    record["scanObserver"] = {n: sha(dwm.HERE / n) for n in dwm.INPUTS}
    record["sources"] = sources(record["revision"])
    dwm.references(out, record, budget.parent, separate_gui=True, candidate_presentation=("CPU-GDI", None))
    shutil.copyfile(budget, out / "reference-budget.json")
    owner = gdi.native_root()
    _, visible = native_window()
    row = recorder.trial(api, fixture, "rust", gui, present, area / "rust-1", endpoint, user_sid, 0x8664,
                         out / "rust-1.log", token, frame_observer=owner)
    record["trial"] = row
    shutil.copyfile(area / "rust-1/present.log", out / "rust-1-idle-presents.log")
    row["presentation"] = idle_result(out, row)
    row["metrics"].update(row["presentation"]["rates"])
    recorder.write(out / "result.json", record)
    root = {}
    views = row["views"] = []
    lifetime = None

    def trace(stack, proc, scan_area, output):
        nonlocal lifetime
        lifetime = WindowLifetime(proc.pid)
        stack.callback(lifetime.close)
        return gdi.trace_scan(api, present, root, stack, proc, scan_area, output)

    def witness(phase, action, hwnd, pid):
        actual = owner(hwnd, pid)
        if root and actual != root:
            raise ValueError("The scan changed the original GUI thread, HWND, PID or dimensions")
        root.update(actual)
        views.append(dict(phase=phase, action=action, hwnd=hwnd, visible=bool(visible(hwnd)), qpc=api.clock()))

    def editor(windows, proc, scratch, env, log, hwnd):
        fields = {}

        def timed_field(shell, scratch, env, output, hwnd, pid, log, phase):
            if owner(hwnd, pid) != root or not visible(hwnd):
                raise ValueError("The original visible editor root changed before input")
            start = api.clock()
            result = dwm.capture_field(shell, scratch, env, output, hwnd, pid, log, phase)
            end = api.clock()
            if owner(hwnd, pid) != root or not visible(hwnd):
                raise ValueError("The original visible editor root changed during input")
            fields[phase] = dict(qpc=[start, end], root=dict(root))
            return result
        try:
            trace_dir = scratch / "editor-trace"
            trace_dir.mkdir()
            with ExitStack() as stack:
                finish, _ = recorder.trace_start(stack, present, proc.pid, trace_dir, timed_log=out / "editor-presents.log")
                begin = api.clock()
                result = dwm.capture_editor(api, fixture, out / "scan-editor", lifetime, windows, proc, scratch, env,
                                            log, hwnd, field_observer=timed_field)
                end = api.clock()
                finish()
                recorder.wait_running(proc)
                result["presentationQpc"] = [begin, end]
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            if CleanupUnconfirmed.in_chain(exc):
                raise
            result = {"error": f"{type(exc).__name__}: {exc}"}
        return dict(**result, fields=fields)

    scan = recorder.measure_scan(api, fixture, "rust", gui, files, area / "rust-1-scan", endpoint, user_sid, out,
                                 recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                 presentation_trace=trace, visibility_witness=witness, after_inventory=editor)
    row["scan"] = scan
    row["metrics"].update(scan["metrics"])
    scan["editor"].update(exitCode=scan["termination"]["exitCode"], subjectLog=sha(out / "rust-1-scan.log"))
    recorder.write(out / "result.json", record)
    if "error" in scan["editor"]:
        raise ValueError("CPU painter editor observation failed: " + scan["editor"]["error"])
    record["raw"] = {n: sha(out / n) for n in RAW}
    recorder.write(out / "result.json", record)
    record["checks"] = readback(out, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output.resolve()
    result = dwm.read(out / "result.json")
    checked = readback(out, result)
    if result["status"] != "cpu-paint-observed" or result["checks"] != checked:
        raise ValueError("The saved CPU-paint comparison differs from its native originals")
    print(json.dumps(checked, indent=2))
