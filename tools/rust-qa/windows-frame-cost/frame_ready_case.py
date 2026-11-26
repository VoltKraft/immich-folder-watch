"""Record and replay one native Windows x64 scan on the original frame-ready root."""
import argparse
from collections import Counter
import ctypes as c
from ctypes import wintypes as w
import json
from math import isfinite
from pathlib import Path
import re
from statistics import median
import shutil
import subprocess

import frame_ready_build as build
from frame_ready_trace import intervals, read_trace
import dwm_transitions as dwm
from frame_latency import measured_generation, replay_scan, visible_edit
from inputs import recorder, sha
from metrics import METRICS
from scan import coverage
from scan_present import start
from window_lifetime import WindowLifetime


def native_window():
    user = c.WinDLL("user32", use_last_error=True)
    owner = recorder.bind(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, c.POINTER(w.DWORD))
    ancestor = recorder.bind(user, "GetAncestor", w.HWND, w.HWND, w.UINT)
    visible = recorder.bind(user, "IsWindowVisible", w.BOOL, w.HWND)

    def read(hwnd, pid):
        actual = w.DWORD()
        tid = owner(hwnd, c.byref(actual))
        if not tid or pid != actual.value or ancestor(hwnd, 2) != hwnd:
            raise ValueError("The frame-ready HWND is no longer the original root")
        return dict(hwnd=int(hwnd), tid=tid, pid=pid)
    return read, visible


def summary(capture):
    cycles = capture["cycles"]
    return dict(immediateAttempts=capture["immediate"], registrations=sum(c["source"] == "arm" for c in cycles),
                reusedSlots=sum(c["source"] == "reuse" for c in cycles),
                results=dict(Counter(c["result"] for c in cycles)), grants=sum("signal" in c for c in cycles),
                messageReturns=sum(len(c["inputs"]) for c in cycles), armedCloseDispatches=sum(len(c["closes"]) for c in cycles))


def device(log):
    rows = log.read_text(encoding="utf-8").splitlines()
    if ([s for s in rows if s.startswith("ADAPTER ")] != ["ADAPTER Dx12 Cpu Microsoft Basic Render Driver"]
            or any(s.startswith(("DWM_TRANSITIONS", "DEFERRED_FRAME", "GDI_PRESENT_MODE")) for s in rows)):
        raise ValueError("An unexpected private control or graphics adapter was selected")
    return measured_generation(log, "Mailbox", wait_policy="DontWait")


def measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget):
    if not files:
        raise ValueError("Both native file and presentation observers are required")
    record["scanObserver"] = {n: sha(dwm.HERE / n) for n in dwm.INPUTS}
    dwm.references(out, record, budget.parent, separate_gui=True)
    shutil.copyfile(budget, out / "reference-budget.json")
    owner, is_visible = native_window()
    row = recorder.trial(api, fixture, "rust", gui, present, area / "rust-1", endpoint, user_sid,
                         0x8664, out / "rust-1.log", token, frame_observer=owner)
    idle_path = out / "rust-1-idle-presents.log"
    shutil.copyfile(area / "rust-1/present.log", idle_path)
    frame = row["frameWindows"]
    rates, row["presentation"] = recorder.present_counts(idle_path.read_text(encoding="ascii"), frame["spans"],
                                                        frame["controls"], frame["frequency"])
    row["metrics"].update(rates)
    record["trial"] = row
    recorder.write(out / "result.json", record)
    lifetime = None
    scan_root = {}
    views = []

    def trace(stack, proc, scan_area, output):
        nonlocal lifetime
        lifetime = WindowLifetime(proc.pid)
        stack.callback(lifetime.close)
        return start(api, present, "Mailbox", stack, proc, scan_area, output)

    def view(phase, action, hwnd, pid):
        actual = owner(hwnd, pid)
        if scan_root and scan_root != actual:
            raise ValueError("The inventory changed frame-ready root, PID or UI thread")
        scan_root.update(actual)
        views.append(dict(phase=phase, action=action, hwnd=hwnd, visible=bool(is_visible(hwnd)), qpc=api.clock()))

    def editor(*args):
        try:
            return dwm.capture_editor(api, fixture, out / "scan-editor", lifetime, *args)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    scan = recorder.measure_scan(api, fixture, "rust", gui, files, area / "rust-1-scan", endpoint, user_sid, out,
                                 recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                 presentation_trace=trace, visibility_witness=view, after_inventory=editor)
    scan["editor"].update(exitCode=scan["termination"]["exitCode"], subjectLog=sha(out / "rust-1-scan.log"))
    row.update(scan=scan, scanRoot=scan_root, views=views)
    row["metrics"].update(scan["metrics"])
    recorder.write(out / "result.json", record)
    if "error" in scan["editor"]:
        raise ValueError("Frame-ready editor observation failed: " + scan["editor"]["error"])
    record["raw"] = {n: sha(out / n) for n in RAW}
    record["checks"] = readback(out, record)


RAW = ("rust-1.log", "rust-1-idle-presents.log", "rust-1-scan.log", "rust-1-scan-files.log",
       "rust-1-scan-presents.log", "rust-1-scan-requests.json", "scan-editor/hosts.json")


def scan_views(views, requests, hwnd):
    if len(views) != 2 * len(requests):
        raise ValueError("Missing external HWND visibility observations")
    last = 0
    for i, q in enumerate(requests):
        a, b = views[2*i:2*i+2]
        if (a["phase"] != "before" or b["phase"] != "after" or a["action"] != q["action"] or b["action"] != q["action"]
                or a["hwnd"] != hwnd or b["hwnd"] != hwnd or q["hwnd"] != hwnd
                or a["visible"] is not (q["action"] == "close") or b["visible"] is not (q["action"] == "reopen")
                or not last <= a["qpc"] <= q["issuedQpc"] <= q["responseQpc"] <= b["qpc"]):
            raise ValueError("An original visibility sample differs from the native close/reopen")
        last = b["qpc"]


def job_resources(sample, gui, worker, known):
    points = sample["jobSamples"]
    if len(points) != len(sample["samples"]) + 1 or len(points) < 2:
        raise ValueError("Missing native job samples")
    previous = total = 0
    for i, point in enumerate(points):
        memory = {int(pid): n for pid,n in point["workingSetBytes"].items()}
        if (not {gui, worker} <= memory.keys() <= known or any(type(n) is not int or n <= 0 for n in memory.values())
                or type(point["cpu100ns"]) is not int or point["cpu100ns"] < previous
                or not 1 <= point["membershipAttempts"] <= 8 or point["totalProcesses"] < max(len(memory), total)
                or (i and sample["samples"][i-1] != sum(memory.values()) / 1_048_576)):
            raise ValueError("The PID-bound working sets or cumulative job CPU differ")
        previous, total = point["cpu100ns"], point["totalProcesses"]
    delta = previous / 10_000_000 - points[0]["cpu100ns"] / 10_000_000
    if sample["cpu_one_core_pct"] != delta * 100 / sample["seconds"]:
        raise ValueError("The native job CPU differs from its two measured endpoints")


def resource_metrics(row):
    metrics = row["metrics"]
    controls = row["presentation"]["reopenControls"]
    if (len(controls) != 2 or any(type(n) is not int or n < 1 for n in controls)
            or row["controls"]["successfulVisibilityCycles"] != recorder.SWITCHES
            or row["termination"] != {"method": "control-Q", "exitCode": 0}
            or set(metrics) != set(METRICS) or any(type(n) not in (int, float) or not isfinite(n) or n < 0 for n in metrics.values())):
        raise ValueError("Incomplete native idle control, termination or comparison metric")
    for action in ("close", "reopen"):
        values = row["idleVisibilityMs"][action]
        if len(values) != recorder.SWITCHES or recorder.p95(values) != metrics["idle_" + action + "_p95_ms"]:
            raise ValueError("A native idle p95 differs from its eight externally observed requests")
    for mode in ("visible", "hidden"):
        sample = row["idleSamples"][mode]
        if (sample["seconds"] < recorder.IDLE_SECONDS or sample["working_set_mib"] != median(sample["samples"])
                or any(metrics[mode + "_" + k] != sample[k] for k in ("cpu_one_core_pct", "working_set_mib"))):
            raise ValueError("The native resource metrics differ from the measured interval and job samples")


def verify_idle(out, row):
    frame = row["frameWindows"]
    root, hz = frame["root"], frame["frequency"]
    log = out / "rust-1.log"
    source = log.read_text(encoding="utf-8")
    capture = read_trace(source, root, hz)
    text = (out / "rust-1-idle-presents.log").read_text(encoding="ascii")
    frames = dwm.native_frames(text, root, hz, (0, 2**63 - 1))
    rates, presents = recorder.present_counts(text, frame["spans"], frame["controls"], hz)
    tree = {int(k): v for k, v in row["controls"]["wholeProcessTree"].items()}
    worker, = re.findall(r"^INVENTORY_WORKER pid=(\d+)$", source, re.M)
    start_qpc, visible_qpc = frame["startupQpc"]
    if (any(pid <= 0 or p["creation100ns"] <= 0 or not p["image"] for pid,p in tree.items())
            or tree[root["pid"]]["creation100ns"] != frame["guiCreation100ns"] or tree[int(worker)]["parent"] != root["pid"]
            or tree[int(worker)]["image"].lower() != "ifw-performance-worker.exe" or not 0 < start_qpc <= visible_qpc
            or row["metrics"]["startup_ms"] != (visible_qpc-start_qpc)*1000/hz
            or frame["spans"]["visible"][1] > frame["spans"]["hidden"][0] or row["presentation"] != presents
            or any(row["metrics"][k] != v for k,v in rates.items())):
        raise ValueError("The original idle job, GUI lifetime, startup or presentation inputs differ")
    for mode in ("visible", "hidden"):
        job_resources(row["idleSamples"][mode], root["pid"], int(worker), tree.keys())
        lo, hi = frame["spans"][mode]
        if not 0 < lo < hi or row["idleSamples"][mode]["seconds"] != (hi-lo)/hz:
            raise ValueError("The native idle interval differs from its resource sample")
    for action, values in row["idleVisibilityMs"].items():
        tail = frame["requests"][-2*recorder.SWITCHES:]
        if values != [(r["responseQpc"] - r["issuedQpc"])*1000/hz for r in tail if r["action"] == action and r["hwnd"] == root["hwnd"]]:
            raise ValueError("Idle close/reopen durations differ from the external root timeline")
    resource_metrics(row)
    return dict(root=root, device=device(log), presents=len(frames), idlePresentCounts=presents["idleCounts"], **summary(capture))


def readback(out, record):
    baseline = out.parents[2] / "windows-performance" / ("native-" + dwm.TARGET)
    refs = dwm.references(out, record, baseline, separate_gui=True)
    build.verify(out, record)
    fixed = build.read(out / "reference-budget.json")
    if sha(out / "reference-budget.json") != record["referenceBudgetSha256"] or record["raw"] != {n: sha(out / n) for n in RAW}:
        raise ValueError("The original native budget or file, input, pixel-host and presentation evidence changed")
    row = record["trial"]
    idle = verify_idle(out, row)
    replay_scan(out, "rust-1", row)
    scan, root = row["scan"], row["scanRoot"]
    edit = scan["editor"]
    meta = build.read(out / "rust-1-scan-requests.json")
    scan_views(row["views"], meta["requests"], root["hwnd"])
    hz = meta["frequency"]
    log = out / "rust-1-scan.log"
    text = log.read_text(encoding="utf-8")
    capture = read_trace(text, root, hz)
    if (root != edit["root"] or root["pid"] != meta["guiPid"] or edit["creation100ns"] != scan["presentation"]["guiCreation100ns"]
            or scan["inventoryCreation100ns"] <= 0 or row["frameWindows"]["guiCreation100ns"] >= edit["creation100ns"]
            or re.findall(r"^INVENTORY_WORKER pid=(\d+)$", text, re.M) != [str(meta["inventoryPid"])]
            or scan["termination"] != {"method": "control-Q", "exitCode": 0}
            or [e[1] for e in edit["rootLifetimes"] if e[0] == root["hwnd"]] != ["create"]
            or [(e["event"], e["hwnd"], e["root"]) for e in edit["rootEvents"]] != [
                ("hide", root["hwnd"], True), ("show", root["hwnd"], True)]):
        raise ValueError("The frame-ready root, owner, worker identity or edit lifetime changed")
    bounds = scan["presentation"]["traceBoundsQpc"]
    a, b, c_, d = edit["editorClocks"]
    if not bounds[1] <= a < b < c_ < d:
        raise ValueError("The editor did not follow the two original inventory passes")
    pixels = visible_edit(out / "scan-editor", edit, 1, device_observer=device, subject_log=log)
    files = (out / "rust-1-scan-files.log").read_text(encoding="ascii")
    gfx = (out / "rust-1-scan-presents.log").read_text(encoding="ascii")
    visible = dwm.visible_frames(scan, meta, files, gfx, root)
    frames = dwm.native_frames(gfx, root, hz, bounds)
    joined = intervals(capture["cycles"], frames, bounds, meta["requests"], scan["eligibleResponses"])
    extras = [dict(action="reopen", issuedQpc=r["beginQpc"], responseQpc=r["endQpc"], hwnd=root["hwnd"])
              for r in [*joined["visibleResumes"], *joined["visibleReuse"]]]
    request_probes = sorted([*meta["requests"], *extras], key=lambda p: p["issuedQpc"])
    active = coverage(files, request_probes, meta["firstCompleteQpc"], meta["secondCompleteQpc"], hz, meta["inventoryPid"], "rust")
    eligible = {r["issuedQpc"] for r in active["eligibleResponses"]}
    resumed = [r for r in joined["visibleResumes"] if r["beginQpc"] in eligible]
    reused = [r for r in joined["visibleReuse"] if r["beginQpc"] in eligible]
    ordinary = build.read(out.parent / "measured/result.json")["comparison"]
    metrics = {k: dict(wpfMaximum=fixed["maximums"][k], ordinaryMedian=ordinary[k]["candidate"], candidate=row["metrics"][k],
                       passed=row["metrics"][k] <= fixed["maximums"][k]) for k in METRICS}
    mechanism = "observed" if resumed and joined["serviced"] else "unobserved"
    return dict(references=refs, idle=idle, scan=summary(capture), editor=pixels, visible=visible,
                mechanism=dict(status=mechanism, closeOpportunities=joined["opportunities"], closeWhileArmed=joined["serviced"],
                               fileQualifiedResumedPresents=resumed, fileQualifiedReusedPresents=reused),
                resources=dict(status="within-limits" if all(r["passed"] for r in metrics.values()) else "over-limit", metrics=metrics))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output.resolve()
    report = build.read(out / "result.json")
    if report["status"] != "frame-ready-recorded" or readback(out, report) != report["checks"]:
        raise ValueError("The recorded one-shot experiment differs from the original native evidence")
    checks = report["checks"]
    print(json.dumps({k: checks[k] for k in ("mechanism", "resources")}, indent=2))
    raise SystemExit(0 if checks["mechanism"]["status"] == "observed" else 2)
