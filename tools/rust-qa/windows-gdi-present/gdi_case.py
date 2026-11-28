"""Compare full-view WARP/GDI rendering with the original same-run WPF limits."""
from bisect import bisect_left
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
from functools import partial
import json
from math import isfinite
from pathlib import Path
import re
import shutil
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows-warm-window"))
from inputs import recorder, sha
from frame_latency import visible_edit
from metrics import METRICS
from observe import drive, observer_inputs
from scan import completion_count, coverage


MODE = "GDI_PRESENT_MODE backend=Dx12 device=Cpu"
FRAME = re.compile(r"GDI_(PRESENT|PARTIAL) frame=(\d+) hwnd=(\d+) tid=(\d+) start=(\d+) end=(\d+) width=(\d+) height=(\d+) lines=(\d+)")
COPY = re.compile(r"STAGING_COPY seq=(\d+) reused=([01]) width=(\d+) height=(\d+) bytes=(\d+) "
                  r"begin=(\d+) prepared=(\d+) map=(\d+) ready=(\d+) returned=(\d+) transfers=([01])")
TARGET = "x86_64-pc-windows-msvc"


@dataclass
class FrameSeries:
    complete: list
    positive: list
    empty: list

    @property
    def attempts(self):
        return sorted(self.positive + self.empty)


def native_root():
    """Snapshot the actual root HWND, its native owner and full client dimensions."""
    user = c.WinDLL("user32", use_last_error=True)
    owner = recorder.bind(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, c.POINTER(w.DWORD))
    ancestor = recorder.bind(user, "GetAncestor", w.HWND, w.HWND, w.UINT)
    client = recorder.bind(user, "GetClientRect", w.BOOL, w.HWND, c.POINTER(w.RECT))

    def observe(hwnd, pid):
        process, rect = w.DWORD(), w.RECT()
        thread = owner(hwnd, c.byref(process))
        if (not thread or process.value != pid or ancestor(hwnd, 2) != hwnd or not client(hwnd, c.byref(rect))
                or rect.left or rect.top or min(rect.right, rect.bottom) <= 0):
            raise ValueError("The observer could not identify the original process's root client")
        return dict(pid=pid, hwnd=hwnd, tid=thread, width=rect.right, height=rect.bottom)

    return observe


def generation(log):
    lines = log.read_text(encoding="utf-8").splitlines()
    if ([s for s in lines if s.startswith("GDI_PRESENT_MODE")] != [MODE]
            or [s for s in lines if s.startswith("GRAPHICS_READY ")] != ["GRAPHICS_READY generation=1"]
            or [s for s in lines if s.startswith("GRAPHICS_MEMORY ")] != ["GRAPHICS_MEMORY generation=1 hint=MemoryUsage"]
            or len([s for s in lines if s.startswith("ADAPTER ")]) != 1
            or not any(s.startswith("ADAPTER Dx12 Cpu ") for s in lines)
            or len([s for s in lines if s.startswith("DRAINED passes=")]) != 1):
        raise ValueError("Missing the original WARP device, GDI root generation or clean drain")
    return dict(generation=1, backend="Dx12", device="Cpu", presenter="GDI")


def frame_spans(text, root):
    """Require every blit to the observed full client, between its mode and final count records."""
    if any(type(v) != int or v <= 0 for v in (root[k] for k in ("pid", "hwnd", "tid", "width", "height"))):
        raise ValueError("Incomplete independent root identity or dimensions")
    series = FrameSeries([], [], [])
    partials = last_end = 0
    mode = ended = False
    for line in text.splitlines():
        if not line.startswith("GDI_"):
            continue
        if ended:
            raise ValueError("Unexpected GDI output after the final frame count")
        if line == MODE and not mode:
            mode = True
            continue
        if series.complete and line == f"GDI_PRESENT_END frames={len(series.complete)} partial={partials}":
            ended = True
            continue
        match = FRAME.fullmatch(line)
        if not mode or not match:
            raise ValueError("Malformed or out-of-order native full-frame receipt")
        complete = match.group(1) == "PRESENT"
        seq, hwnd, tid, lo, hi, width, height, scanlines = map(int, match.groups()[1:])
        if (seq != (len(series.complete) if complete else partials) + 1 or (hwnd, tid) != (root["hwnd"], root["tid"])
                or not (0 < lo <= hi) or lo < last_end or (width, height) != (root["width"], root["height"])
                or scanlines > height or (complete and scanlines != height)):
            raise ValueError("Missing, foreign, overlapping or misclassified native frame")
        if complete:
            series.complete.append((lo, hi))
        else:
            partials += 1
        (series.positive if scanlines else series.empty).append((lo, hi))
        last_end = hi
    if not ended:
        raise ValueError("The GDI renderer did not confirm its final frame count")
    return series


def no_swapchain(text, pid, frequency):
    if (type(pid) != int or pid <= 0 or type(frequency) != int or frequency <= 0
            or text.splitlines() != ["READY", f"QPC {pid} {frequency}", "COMPLETE"]):
        raise ValueError("A different process or clock, a failed session, or a successful DXGI/D3D9 present was recorded")


def staging_observation(text, frequency):
    """Match each actual transfer to its mapped copy and verify reuse before reporting stage costs."""
    allocation, reuse, mapping = [], [], []
    previous_size = previous_return = None
    transfers = []
    ended = False
    for line in text.splitlines():
        frame = FRAME.fullmatch(line)
        if frame:
            if ended or transfers:
                raise ValueError("Unmatched GDI transfer in the staging timeline")
            transfers.append(tuple(map(int, frame.groups()[4:8])))
            continue
        if not line.startswith("STAGING_"):
            continue
        if ended:
            raise ValueError("Staging continued after shutdown")
        if line == f"STAGING_END copies={len(mapping)}" and not transfers and reuse:
            ended = True
            continue
        match = COPY.fullmatch(line)
        if not match:
            raise ValueError("Invalid staging copy or final count")
        seq, reused, width, height, size, begin, prepared, map_begin, ready, returned, count = map(int, match.groups())
        if (seq != len(mapping) + 1 or reused != ((width, height) == previous_size)
                or not (0 < width <= 8192 and 0 < height <= 8192)
                or size != ((width * 4 + 255) // 256) * 256 * height or size > 32 * 1024 * 1024
                or not (0 < begin <= prepared <= map_begin <= ready <= returned)
                or (previous_return is not None and begin < previous_return) or count != len(transfers)
                or any(not (ready <= lo <= hi <= returned and (w, h) == (width, height))
                       for lo, hi, w, h in transfers)):
            raise ValueError("The staging allocation, layout or native call order differs from its frame")
        previous_size, previous_return = (width, height), returned
        (reuse if reused else allocation).append((prepared-begin) * 1000 / frequency)
        mapping.append((ready-map_begin) * 1000 / frequency)
        transfers.clear()
    if not ended:
        raise ValueError("Missing completed staging timeline")
    return dict(copies=len(mapping), allocations=len(allocation), reuses=len(reuse),
                allocationP95Ms=recorder.p95(allocation), checkoutP95Ms=recorder.p95(reuse),
                mapAndWaitP95Ms=recorder.p95(mapping))


def staging_records(out):
    frequency = json.loads((out / "rust-1-scan-requests.json").read_bytes())["frequency"]
    if type(frequency) != int or frequency <= 0:
        raise ValueError("Missing native QPC frequency")
    return {phase: staging_observation((out / name).read_text(encoding="utf-8"), frequency)
            for phase, name in (("idle", "rust-1.log"), ("scan", "rust-1-scan.log"),
                                ("edit", "retained-edit/subject.log"))}


def inside(frames, span):
    return sum(span[0] <= lo <= hi < span[1] for lo, hi in frames)


def check_requests(requests, root, frames, *, final_hidden_until=None):
    """Check all independently observed hidden intervals for intersection with an actual blit."""
    last = 0
    starts = [row[0] for row in frames]
    hidden = []
    for index, q in enumerate(requests):
        if (q["action"] != ("close", "reopen")[index % 2] or q["hwnd"] != root["hwnd"]
                or not last < q["issuedQpc"] <= q["responseQpc"]):
            raise ValueError("Invalid original visibility transition")
        if index % 2:
            hidden.append((last, q["issuedQpc"]))
        last = q["responseQpc"]
    if requests and requests[-1]["action"] == "close" and final_hidden_until is not None:
        if final_hidden_until <= last:
            raise ValueError("Invalid end of the final observed hidden interval")
        hidden.append((last, final_hidden_until))
    for lo, hi in hidden:
        i = bisect_left(starts, lo)
        if ((i and frames[i - 1][1] > lo) or (i < len(frames) and starts[i] < hi)):
            raise ValueError("The GDI control blitted during an independently observed hidden interval")
    return len(hidden)


def idle_observation(row, frames, etw):
    witness = row["frameWindows"]
    root, frequency = witness["root"], witness["frequency"]
    no_swapchain(etw, root["pid"], frequency)
    start, visible = witness["startupQpc"]
    if not 0 < start < visible or row["metrics"]["startup_ms"] != (visible - start) * 1000 / frequency:
        raise ValueError("Initial visibility differs from the original startup observation")
    requests = witness["requests"]
    if len(requests) != 4 + 2 * recorder.SWITCHES:
        raise ValueError("Missing an idle visibility transition")
    attempts = frames.attempts
    hidden = check_requests(requests, root, attempts)
    controls = witness["controls"]
    idle = witness["spans"]
    if (len(controls) != 2 or set(idle) != {"visible", "hidden"}
            or not 0 < controls[0][0] < controls[0][1] <= idle["visible"][0] < idle["visible"][1]
            <= requests[2]["issuedQpc"] <= requests[2]["responseQpc"] <= idle["hidden"][0]
            < idle["hidden"][1] <= controls[1][0] < controls[1][1] <= requests[4]["issuedQpc"]
            or any(span[0] != requests[i]["issuedQpc"] or span[1] <= requests[i]["responseQpc"] for span, i in zip(controls, (1, 3)))):
        raise ValueError("Incomplete independently timed idle calibration windows")
    counts = [inside(frames.complete, [requests[i]["responseQpc"], span[1]]) for i, span in zip((1, 3), controls)]
    if (not all(counts) or not inside(frames.complete, [1, requests[0]["issuedQpc"]])
            or row["termination"] != {"method":"control-Q", "exitCode":0} or row["controls"]["successfulVisibilityCycles"] != recorder.SWITCHES):
        raise ValueError("Missing initial visible frame, real reopened frames, visibility cycles or clean exit")
    tree = {int(k): v for k, v in row["controls"]["wholeProcessTree"].items()}
    if (tree[root["pid"]]["creation100ns"] != witness["guiCreation100ns"]
            or not any(p["parent"] == root["pid"] and p["image"].lower() == "ifw-performance-worker.exe" for p in tree.values())):
        raise ValueError("Idle resources were sampled on a different process tree")
    measured, positive_counts = {}, {}
    for action in ("close", "reopen"):
        durations = [(q["responseQpc"] - q["issuedQpc"]) * 1000 / frequency for q in requests[4:] if q["action"] == action]
        if durations != row["idleVisibilityMs"][action] or recorder.p95(durations) != row["metrics"][f"idle_{action}_p95_ms"]:
            raise ValueError("Idle latency differs from the original transition clock")
    for mode, (lo, hi) in idle.items():
        sample = row["idleSamples"][mode]
        if (sample["seconds"] != (hi - lo) / frequency or sample["seconds"] < recorder.IDLE_SECONDS
                or sample["working_set_mib"] != median(sample["samples"])
                or any(row["metrics"][mode + "_" + k] != sample[k] for k in ("cpu_one_core_pct", "working_set_mib"))):
            raise ValueError("Idle samples differ from the original resource observations")
        # Include even flushed zero-line requests in the conservative drawing rate.
        count = sum(lo <= end < hi for _, end in attempts)
        positive_counts[mode] = sum(lo <= end < hi for _, end in frames.positive)
        measured[mode + "_present_per_second"] = count / sample["seconds"]
    return dict(fullFrames=len(frames.complete), positiveTransfers=len(frames.positive), zeroLineCalls=len(frames.empty),
                reopenControls=counts, hiddenIntervals=hidden, idlePositiveTransfers=positive_counts, rates=measured)


def trace_scan(api, executable, root, stack, proc, area, output):
    handle = recorder.checked(api.open(0x1000, False, proc.pid))
    stack.callback(api.close, handle)
    identity = api.process_identity(handle)
    if identity != api.process_identity(proc._handle):
        raise ValueError("The trace does not belong to the suspended GUI process")
    start = api.clock()
    log = output / (area.name + "-presents.log")
    finish, _ = recorder.trace_start(stack, executable, proc.pid, area, timed_log=log)

    def collect(_work):
        finish()
        end = api.clock()
        recorder.wait_running(proc)
        if api.process_identity(handle) != identity or root["pid"] != proc.pid:
            raise ValueError("The measured GUI process changed during the inventory")
        no_swapchain(log.read_text(encoding="ascii"), proc.pid, api.frequency)
        return dict(guiCreation100ns=identity, root=dict(root), traceBoundsQpc=[start, end], decodedEventsSha256=sha(log))

    return collect


def scan_observation(out, row, frames):
    scan = row["scan"]
    meta = json.loads((out / "rust-1-scan-requests.json").read_bytes())
    text = (out / "rust-1-scan.log").read_text(encoding="utf-8")
    files = (out / "rust-1-scan-files.log").read_text(encoding="ascii")
    presentation = scan["presentation"]
    etw = out / "rust-1-scan-presents.log"
    root = presentation["root"]
    pid, worker, clock = meta["guiPid"], meta["inventoryPid"], meta["frequency"]
    requests = meta["requests"]
    if (root["pid"] != pid or pid != scan["guiPid"] or worker != scan["inventoryPid"] or root["pid"] == worker
            or scan["inventoryCreation100ns"] <= 0 or presentation["guiCreation100ns"] <= 0
            or re.findall(r"^INVENTORY_WORKER pid=(\d+)$", text, re.M) != [str(worker)]
            or requests != scan["allRequests"] or sha(etw) != presentation["decodedEventsSha256"]
            or not scan["unchangedWorker"] or scan["completedPasses"] != 2 or scan["termination"]["exitCode"] != 0
            or completion_count(text, "rust", None) != 2):
        raise ValueError("Unverified GUI, worker, request clocks or native process completion")
    no_swapchain(etw.read_text(encoding="ascii"), pid, clock)
    work = coverage(files, requests, meta["firstCompleteQpc"], meta["secondCompleteQpc"], clock, worker, "rust")
    if any(scan[k] != v for k, v in work.items()):
        raise ValueError("The measured file activity differs from the original ETW records")
    hidden = check_requests(requests, root, frames.attempts, final_hidden_until=meta["secondCompleteQpc"])
    first = work["passes"][0]
    begin, end = first["firstFileQpc"], first["lastFileQpc"]
    if not presentation["traceBoundsQpc"][0] <= begin < end <= meta["secondCompleteQpc"] <= presentation["traceBoundsQpc"][1]:
        raise ValueError("Inventory was outside the independent graphics trace")
    active = [f for f in frames.complete if begin <= f[0] <= f[1] <= end]
    # coverage() requires independently observed file opens near both timestamps. Each
    # candidate is a complete post-reopen frame, before any following close was issued.
    visible = [(r["responseQpc"], s["issuedQpc"]) for r, s in zip(requests, requests[1:]) if r["action"] == "reopen"]
    starts = [lo for lo, _ in visible]
    by_window = {}
    for lo, hi in active:
        index = bisect_left(starts, lo + 1) - 1
        if index >= 0 and hi < visible[index][1] and starts[index] not in by_window:
            by_window[starts[index]] = dict(action="reopen", issuedQpc=lo, responseQpc=hi, hwnd=root["hwnd"])
    # Preserve the original two action classes in coverage's positive controls.
    # Substitute frames for reopens only when they fit wholly between their response and the next close.
    frame_probes = []
    for q in requests:
        if q["action"] == "close":
            frame_probes.append(q)
        elif sample := by_window.get(q["responseQpc"]):
            frame_probes.append(sample)
    replay = coverage(files, frame_probes, meta["firstCompleteQpc"], meta["secondCompleteQpc"], clock, worker, "rust")
    eligible_reopens = {q["responseQpc"]: q for q in work["eligibleResponses"] if q["action"] == "reopen"}
    eligible_frames = {q["issuedQpc"] for q in replay["eligibleResponses"] if q["action"] == "reopen"}
    delays = [{"hwndVisibleQpc": visible_qpc, "fullBlitStartQpc": frame["issuedQpc"], "flushReturnedQpc": frame["responseQpc"],
               "ms": (frame["responseQpc"] - visible_qpc) * 1000 / clock}
              for visible_qpc, frame in by_window.items() if visible_qpc in eligible_reopens and frame["issuedQpc"] in eligible_frames]
    if len(delays) < 5:
        raise ValueError("Fewer than five full post-reopen blits coincided with original file activity")
    for action in ("close", "reopen"):
        name = "scan_" + action + "_p95_ms"
        values = [(q["responseQpc"] - q["issuedQpc"]) * 1000 / clock for q in work["eligibleResponses"] if q["action"] == action]
        if recorder.p95(values) != scan["metrics"][name] or row["metrics"][name] != scan["metrics"][name]:
            raise ValueError("The scan latency differs from independently timed eligible responses")
    return dict(fullFrames=len(frames.complete), positiveTransfers=len(frames.positive), zeroLineCalls=len(frames.empty),
                firstPassFullFrames=len(active), workQualifiedReopensWithFrame=len(delays), hiddenIntervals=hidden,
                workQualifiedResponses=len(work["eligibleResponses"]), firstFullBlitAfterObservedReopen=delays,
                firstFullBlitAfterObservedReopenP95Ms=recorder.p95([r["ms"] for r in delays]))


def edit_observation(out, row):
    base = out / "retained-edit"
    edit = visible_edit(base, row, 1, device_observer=generation)
    before, after = row["beforeFrameWindow"], row["afterFrameWindow"]
    root = before["root"]
    transition, = row["transitions"]
    if (root != after["root"] or root["pid"] != edit["pid"] or root["hwnd"] != edit["hwnd"]
            or not 0 < before["qpc"][0] < before["qpc"][1] <= transition["hiddenQpc"]
            < transition["reopenIssuedQpc"] <= transition["visibleQpc"] <= after["qpc"][0] < after["qpc"][1]):
        raise ValueError("The edit did not preserve the observed native window and independent clock")
    frames = frame_spans((base / "subject.log").read_text(encoding="utf-8"), root)
    hidden = (transition["hiddenQpc"], transition["reopenIssuedQpc"])
    if (any(lo < hidden[1] and hi > hidden[0] for lo, hi in frames.attempts)
            or not all(inside(frames.complete, x["qpc"]) for x in (before, after))):
        raise ValueError("Missing visible GDI edits or a GDI frame overlapped the hidden interval")
    return dict(**edit, fullFrames=len(frames.complete), positiveTransfers=len(frames.positive), zeroLineCalls=len(frames.empty),
                firstEditorFrames=inside(frames.complete, before["qpc"]), reopenedEditorFrames=inside(frames.complete, after["qpc"]))


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget):
    if not files or not present or sha(gui) != record["binary"]:
        raise ValueError("The staged full GDI renderer and native observers are required")
    shutil.copyfile(budget, out / "reference-budget.json")
    observe_root = native_root()
    row = recorder.trial(api, fixture, "rust", gui, present, area / "rust-1", endpoint, user_sid, 0x8664,
                         out / "rust-1.log", token, frame_observer=observe_root)
    shutil.copyfile(area / "rust-1/present.log", out / "rust-1-idle-presents.log")
    record["trial"] = row
    idle = idle_observation(row, frame_spans((out / "rust-1.log").read_text(encoding="utf-8"), row["frameWindows"]["root"]),
                            (out / "rust-1-idle-presents.log").read_text(encoding="ascii"))
    row["presentation"] = idle
    row["metrics"].update(idle["rates"])
    recorder.write(out / "result.json", record)
    root = {}

    def witness(_phase, _action, hwnd, pid):
        actual = observe_root(hwnd, pid)
        if root and root != actual:
            raise ValueError("The scan changed the original GUI thread, HWND, PID or dimensions")
        root.update(actual)

    row["scan"] = recorder.measure_scan(api, fixture, "rust", gui, files, area / "rust-1-scan", endpoint, user_sid,
                                       out, recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                       presentation_trace=partial(trace_scan, api, present, root), visibility_witness=witness)
    row["metrics"].update(row["scan"]["metrics"])
    record["edit"] = {}
    record["editObservers"] = observer_inputs()
    recorder.write(out / "result.json", record)
    drive(api, fixture, gui, out / "retained-edit", "retained-edit", evidence=record["edit"], gdi_frame_observer=observe_root)
    record["nativeTraces"] = {name: sha(out / name) for name in TRACE_FILES}
    record["gdiObserver"] = sha(Path(__file__))
    record["staging"] = staging_records(out)
    recorder.write(out / "result.json", record)
    record["checks"] = readback(out, record)


TRACE_FILES = ("rust-1.log", "rust-1-idle-presents.log", "rust-1-scan.log", "rust-1-scan-requests.json",
               "rust-1-scan-files.log", "rust-1-scan-presents.log", "retained-edit/subject.log")


def readback(out, record):
    if staging_records(out) != record["staging"]:
        raise ValueError("The original GDI buffer timings or allocation counts changed")
    base = out.parent
    load = lambda path: json.loads(path.read_bytes())
    paired = load(base / "measured/result.json")
    observed = load(base / "observed/result.json")
    ordinary = load(base / "build.json")
    receipt = load(out / "gdi-build.json")
    limits = load(out / "reference-budget.json")
    reference_dir = base.parent.parent / "windows-performance" / ("native-" + TARGET)
    wpf = load(reference_dir / "result.json")
    inputs = load(reference_dir / "inputs.json")
    if (sha(reference_dir / "reference-budget.json") != record["referenceBudgetSha256"]
            or wpf["budgetSha256"] != record["referenceBudgetSha256"] or wpf["target"] != TARGET
            or any(wpf["host"][k] != record[k] for k in ("run", "attempt"))
            or inputs["candidateRevision"] != record["revision"] or inputs["target"] != TARGET
            or limits["sourceInputsSha256"] != sha(reference_dir / "inputs.json")
            or inputs["drivers"]["run.py"] != sha(Path(recorder.__file__))
            or limits["reference"] != recorder.summarize(wpf["trials"]["wpf"])):
        raise ValueError("Could not reproduce the same runner's WPF reference and its 11 original limits")
    same_run = ("revision", "target", "run", "attempt")
    if (record["target"] != TARGET or record["presentMode"] != "GDI" or record["desiredMaximumFrameLatency"] is not None
            or not record["diagnosticControl"] or paired["diagnosticControl"] or paired["presentMode"] != "Mailbox"
            or any(record[k] != paired[k] for k in (*same_run, "baseline", "baselineReceipt", "buildReceipt", "referenceBudgetSha256", "observerInputs"))
            or any(receipt[k] != record[k] or observed[k] != record[k] for k in same_run)
            or record["editObservers"] != observed["observerInputs"] or record["editObservers"] != observer_inputs()
            or record["gdiObserver"] != sha(Path(__file__))
            or record["nativeTraces"] != {name: sha(out / name) for name in TRACE_FILES}
            or sha(out / "gdi-build.json") != record["gdiBuild"] or sha(out / "compiler.jsonl") != receipt["compiler"]
            or sha(out / "source.zip") != receipt["sources"]["archive"]
            or sha(out / "gdi.exe") != record["binary"] or receipt["application"]["sha256"] != record["binary"]
            or recorder.pe_machine(out / "gdi.exe") != 0x8664 or record["binary"] == record["pairedBinary"]
            or record["pairedBinary"] != receipt["ordinaryBinary"] or record["pairedBinary"] != ordinary["binary"]
            or record["pairedBinary"] != paired["binary"] or record["pairedBinary"] != observed["binary"]
            or record["buildReceipt"] != sha(base / "build.json") or receipt["ordinaryBuild"] != record["buildReceipt"]
            or record["inputs"]["inventory"]["gui"] != record["binary"] or record["inputs"]["workload"] != paired["inputs"]["workload"]
            or any(record["inputs"]["inventory"][k] != paired["inputs"]["inventory"][k] for k in ("compiledEntry", "approvedBundle", "packages", "sources"))
            or sha(out / "reference-budget.json") != record["referenceBudgetSha256"]
            or set(limits["maximums"]) != set(METRICS) or limits["maximums"] != recorder.budgets(limits["reference"])
            or len(paired["trials"]) != recorder.TRIALS
            or paired["comparison"] != recorder.comparison(limits["maximums"], recorder.summarize(paired["trials"]))):
        raise ValueError("The diagnostic and ordinary measurements do not share the expected source, native binaries and WPF limits")
    row = record["trial"]
    if set(row["metrics"]) != set(METRICS) or any(type(n) not in (float,int) or not isfinite(n) or n < 0 for n in row["metrics"].values()):
        raise ValueError("Expected all eleven measured native metrics")
    idle_log, scan_log = out / "rust-1.log", out / "rust-1-scan.log"
    generation(idle_log)
    generation(scan_log)
    idle_text = idle_log.read_text(encoding="utf-8")
    pid = row["frameWindows"]["root"]["pid"]
    workers = [str(k) for k, process in row["controls"]["wholeProcessTree"].items()
               if process["parent"] == pid and process["image"].lower() == "ifw-performance-worker.exe"]
    if (len(workers) != 1 or re.findall(r"^INVENTORY_WORKER pid=(\d+)$", idle_text, re.M) != workers
            or not recorder.idle_complete(idle_text)):
        raise ValueError("The GDI subject's original worker did not complete its two idle inventories")
    idle = idle_observation(row, frame_spans(idle_text, row["frameWindows"]["root"]),
                            (out / "rust-1-idle-presents.log").read_text(encoding="ascii"))
    if row["presentation"] != idle or any(row["metrics"][k] != value for k, value in idle["rates"].items()):
        raise ValueError("The archived idle rates differ from the actual GDI frames")
    scan = scan_observation(out, row, frame_spans(scan_log.read_text(encoding="utf-8"), row["scan"]["presentation"]["root"]))
    return dict(idle=idle, scan=scan, edit=edit_observation(out, record["edit"]),
                singleTrial={k:dict(wpfMaximum=limits["maximums"][k], ordinaryMedian=paired["comparison"][k]["candidate"],
                                    gdi=row["metrics"][k]) for k in METRICS})


if __name__ == "__main__":
    import gdi_build
    path = Path(sys.argv[1])
    saved = json.loads((path / "result.json").read_bytes())
    gdi_build.verify(path, saved)
    if readback(path, saved) != saved["checks"]:
        raise ValueError("Native GDI readback differs from the recorded full-view comparison")
    print(json.dumps(saved["checks"]["singleTrial"], indent=2))
