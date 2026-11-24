"""Bind both DX12 Mailbox depths to the same WPF budget, file workload and visible editor."""
import json
import math
import re
import struct

from inputs import TWO_FRAME_EDIT, recorder, sha
from metrics import METRICS
from scan import completion_count, coverage
from scan_present import correlate


HOST_BUILD = ("target", "run", "attempt", "revision", "binary", "buildReceipt", "baseline", "baselineReceipt")


def measured_generation(log, mode, *, frame_latency=1, dispatch_trace=False, wait_policy="Wait"):
    rows = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if not dispatch_trace and any(row.startswith(("DISPATCH", "WINDOW_WAKE ", "WINDOW_HIDDEN_PAINT ")) for row in rows):
        raise ValueError("The ordinary measurement used a diagnostic dispatch path")
    if ([r for r in rows if r.startswith("GRAPHICS_MEMORY ")] != ["GRAPHICS_MEMORY generation=1 hint=MemoryUsage"]
            or [r for r in rows if r.startswith("GRAPHICS_READY ")] != ["GRAPHICS_READY generation=1"]
            or any(r.startswith("WGPU_ALLOCATOR ") for r in rows)):
        raise ValueError("Expected a single warm MemoryUsage device and a measurement without allocator sampling")
    offered = [re.fullmatch(r"GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=\[([A-Za-z, ]+)\]", row)
               for row in rows if row.startswith("GRAPHICS_SURFACE ")]
    selection = f"GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode={mode} latency=Some({frame_latency})"
    if (len(offered) != 1 or not offered[0] or mode not in offered[0].group(1).split(", ")
            or [row for row in rows if row.startswith("GRAPHICS_PRESENT ")] != [selection]):
        raise ValueError("Expected the supported presentation mode and selected frame latency on the DX12 CPU device")
    if wait_policy not in ("Wait", "DontWait") or [row for row in rows if row.startswith("GRAPHICS_DX12_WAIT ")] != [f"GRAPHICS_DX12_WAIT generation=1 policy={wait_policy}"]:
        raise ValueError(f"The actual DX12 instance descriptor must select the {wait_policy} policy for the frame latency waitable object")
    return dict(generation=1, memoryHint="MemoryUsage", presentMode=mode, offered=offered[0].group(1).split(", "),
                desiredMaximumFrameLatency=frame_latency, waitPolicy=wait_policy)


def replay_scan(folder, name, trial):
    """Derive the two pass boundaries, eligible window responses and successful presents from the original observers."""
    scan = trial["scan"]
    timings = json.loads((folder / (name + "-scan-requests.json")).read_bytes())
    pid, worker, clock = timings["guiPid"], timings["inventoryPid"], timings["frequency"]
    requests = timings["requests"]
    subject_log = (folder / (name + "-scan.log")).read_text(encoding="utf-8")
    if (pid != scan["guiPid"] or worker != scan["inventoryPid"] or pid == worker or min(pid, worker) <= 0
            or requests != scan["allRequests"] or len({r["hwnd"] for r in requests}) != 1
            or scan["unchangedWorker"] is not True or scan["completedPasses"] != 2
            or completion_count(subject_log, "rust", None) != 2):
        raise ValueError("The original window requests, inventory worker or completed passes differ")
    files = (folder / (name + "-scan-files.log")).read_text(encoding="ascii")
    work = coverage(files, requests, timings["firstCompleteQpc"], timings["secondCompleteQpc"], clock, worker, "rust")
    if any(scan[k] != v for k, v in work.items()):
        raise ValueError("The native two-pass inventory differs from the original file-activity record")
    dxgi = folder / (name + "-scan-presents.log")
    saved = scan["presentation"]
    presentation = correlate(dxgi.read_text(encoding="ascii"), pid, clock, saved["traceBoundsQpc"], work, "Mailbox")
    if any(saved[k] != v for k, v in presentation.items()) or sha(dxgi) != saved["decodedEventsSha256"]:
        raise ValueError("The DXGI report differs from the original successful native presentations")
    for action in ("close", "reopen"):
        key = "scan_" + action + "_p95_ms"
        values = [(r["responseQpc"] - r["issuedQpc"]) * 1000 / clock for r in work["eligibleResponses"] if r["action"] == action]
        if recorder.p95(values) != scan["metrics"][key] or scan["metrics"][key] != trial["metrics"][key]:
            raise ValueError("The scan response p95 differs from its original native timestamps")


def paired_frame_latency(base, two, limits):
    one_path = base / "measured/result.json"
    one = json.loads(one_path.read_bytes())
    if (any(one[k] != two[k] for k in (*HOST_BUILD, "referenceBudgetSha256", "observerInputs"))
            or one["inputs"]["workload"] != two["inputs"]["workload"]
            or any(one["inputs"]["inventory"][k] != two["inputs"]["inventory"][k]
                   for k in ("compiledEntry", "approvedBundle", "packages", "sources", "gui"))):
        raise ValueError("The one- and two-frame measurements use different native inputs")
    for depth, data, folder in ((1, one, "measured"), (2, two, "measured-mailbox-two")):
        if (data["presentMode"] != "Mailbox" or data["desiredMaximumFrameLatency"] != depth
                or data["diagnosticControl"] != (depth == 2) or data["inputs"]["inventory"]["gui"] != data["binary"]
                or data["comparison"] != recorder.comparison(limits, recorder.summarize(data["trials"]))
                or any(data["comparison"][k]["passed"] is None for k in METRICS)):
            raise ValueError("Both Mailbox depths require three complete trials against the same eleven WPF limits")
        for index, trial in enumerate(data["trials"], 1):
            name = f"rust-{index}"
            for suffix, observed in ((".log", trial), ("-scan.log", trial["scan"])):
                if measured_generation(base / folder / (name + suffix), "Mailbox", frame_latency=depth) != observed["device"]:
                    raise ValueError("The original device log differs from its Mailbox trial")
            replay_scan(base / folder, name, trial)
    return {"mailboxOneResultSha256": sha(one_path),
            "metrics": {k: {"wpfMaximum": limits[k], "mailboxOne": one["comparison"][k]["candidate"],
                            "mailboxTwo": two["comparison"][k]["candidate"]} for k in METRICS}}


def visible_edits(base, measurement):
    """Reopen the field captures made by the independent observer on the selected input desktop."""
    root = base / "observed"
    report_path = root / "result.json"
    report = json.loads(report_path.read_bytes())
    if any(report[k] != measurement[k] for k in HOST_BUILD):
        raise ValueError("The edit observer used a different retained build or native runner")
    edits = {}
    for depth, name in ((1, "retained-edit"), (2, TWO_FRAME_EDIT)):
        trial, folder = report["controls"][name], root / name
        edits[name] = visible_edit(folder, trial, depth)
    return dict(observerResultSha256=sha(report_path), controls=edits)


def visible_edit(folder, trial, depth, wait_policy="Wait", *, device_observer=None):
    """Replay the two real input-desktop edits and retained native window from one trial."""
    if trial.get("error"):
        raise ValueError(f"The {depth}-frame edit observation failed: {trial['error']}")
    transition, = trial["transitions"]
    hwnd, pid = transition["hidden"], trial["pid"]
    if (trial["case"] != "retained-edit" or not pid or not hwnd or trial["creation100ns"] <= 0
            or hwnd != transition["reopened"] or trial["exitCode"] != 0 or trial["singleWake"]
            or transition["generationBefore"] != transition["generationAfter"]
            or transition["generationBefore"] != ["GRAPHICS_READY generation=1"]
            or sha(folder / "subject.log") != trial["subjectLog"]):
        raise ValueError("The edit observer did not retain its original HWND and renderer")
    if device_observer is None:
        device = measured_generation(folder / "subject.log", "Mailbox", frame_latency=depth, wait_policy=wait_policy)
    else:
        device = device_observer(folder / "subject.log")
    images = {}
    for phase, draft in (("before", "recoverydraft"), ("after", "recoverydraftafter")):
        path = folder / f"field-{phase}.json"
        field = json.loads(path.read_text(encoding="utf-8-sig"))
        if (sha(path) != trial[phase + "Field"] or field["windowHandle"] != hwnd or field["processId"] != pid
                or field["status"] != "passed" or field["foreground"] is not True or field["onInputDesktop"] is not True
                or field["draft"] != draft or (phase == "after" and field["focusBeforeActivation"] != "Dateiname")):
            raise ValueError("The native editor did not preserve its owned field, text or focus")
        captures = ("edited",) if phase == "before" else ("restored", "edited")
        for kind in captures:
            image = folder / (path.name + "." + kind + ".png")
            frame = field[kind + "Frame"]
            with image.open("rb") as stream:
                header = stream.read(24)
            if (sha(image) != frame["sha256"] or frame["colors"] < 5
                    or not (10 <= frame["width"] <= 1024 and 5 <= frame["height"] <= 128)
                    or header != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + struct.pack(">II", frame["width"], frame["height"])):
                raise ValueError("The native edit capture differs from its observed screen pixels")
            images[f"{phase}-{kind}"] = frame["sha256"]
    difference = field["difference"]
    restored, edited = field["restoredFrame"], field["editedFrame"]
    dpi = field["dpi"]
    if (images["after-edited"] == images["after-restored"]
            or any(restored[k] != edited[k] for k in ("x", "y", "width", "height"))
            or dpi <= 0 or difference["textChanged"] is not True
            or not math.ceil(6 * dpi / 96) <= difference["columns"] <= edited["width"]
            or not math.ceil(3 * dpi / 96) <= difference["rows"] <= edited["height"]
            or not max(difference["columns"], difference["rows"]) <= difference["pixels"] <= difference["columns"] * difference["rows"]):
        raise ValueError("The reopened editor did not display the changed text")
    return dict(hwnd=hwnd, pid=pid, creation100ns=trial["creation100ns"], subjectLogSha256=trial["subjectLog"],
                device=device, frames=images, pixelDifference=difference)
