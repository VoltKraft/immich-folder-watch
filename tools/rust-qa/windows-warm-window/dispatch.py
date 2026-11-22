"""Measure activation dispatch and presentations between verified hide and show transitions."""
from bisect import bisect_left, bisect_right
from collections import Counter
from contextlib import ExitStack
from functools import partial
from itertools import accumulate
import json
import os
from statistics import median

from inputs import HERE, recorder, sha
from metrics import METRICS
from scan_present import start as trace_presentation

CALLBACKS = {"close-event", "redraw-event", "resize-event", "focus-event", "occlusion-event",
             "focus-gained-event", "focus-lost-event", "modifiers-empty-event", "modifiers-changed-event",
             "window-event", "user-event", "new-events", "about-to-wait"}
OPERATIONS = {"pipe-open", "open-dequeued", "show", "hide", "focus", "request-redraw", "private-wake"}


def occupied_ticks(spans, start, end):
    cursor, total = start, 0
    for span in spans:
        right = min(span["end"], end)
        total += max(0, right - max(cursor, span["start"]))
        cursor = max(cursor, right)
    return total


def parse(text, pid, frequency, single):
    lines = [line for line in text.splitlines() if line.startswith("DISPATCH")]
    if not lines or lines[-1] != "DISPATCH_END":
        raise ValueError("The owned process did not flush its dispatch trace")
    head = lines[0].split()
    if (len(head) != 6 or head[:4] != ["DISPATCH_BEGIN", str(pid), str(frequency), str(int(single))]
            or not 0 < int(head[4]) <= 65536 or int(head[4]) != len(lines) - 2 or head[5] != "0"):
        raise ValueError("The dispatch PID, clock, mode or complete bounded span count differs")
    spans = []
    for line in lines[1:-1]:
        tag, label, thread, start, end, hwnd, before, after, sampled = line.split()
        thread, start, end, hwnd, before, after, sampled = map(int, (thread, start, end, hwnd, before, after, sampled))
        if tag != "DISPATCH" or label not in CALLBACKS | OPERATIONS or thread <= 0 or not 0 < start <= end:
            raise ValueError("Invalid native dispatch span")
        if label in ("show", "hide"):
            if hwnd <= 0 or before not in (0, 1) or after not in (0, 1) or sampled < end:
                raise ValueError("Missing Win32 before/after visibility or invalid sample clock")
        elif hwnd or sampled or (label != "resize-event" and (before, after) != (-1, -1)):
            raise ValueError("Unexpected window data in a dispatch span")
        spans.append(dict(label=label, thread=thread, start=start, end=end, hwnd=hwnd, before=before,
                          after=after, sampled=sampled))
    return sorted(spans, key=lambda s: s["start"])


def hidden_presents(spans, reopens, presentations, bounds):
    changes = [s for s in spans if s["label"] in ("hide", "show")]
    transitions = [s["start"] for s in changes]
    presentations = sorted(presentations)
    present_starts = [p[0] for p in presentations]
    inputs = [s for s in spans if s["label"] in CALLBACKS]
    input_starts = [s["start"] for s in inputs]
    verified = 0
    hidden_starts = 0
    completed = Counter()
    callbacks = Counter()
    for show in reopens:
        index = bisect_left(transitions, show["start"])
        if index == 0 or changes[index - 1]["label"] != "hide":
            continue
        hide = changes[index - 1]
        start, end = hide["sampled"], show["start"]
        if ((hide["before"], hide["after"], show["before"], show["after"]) != (1, 0, 0, 1)
                or not bounds[0] <= start < end <= bounds[1]):
            continue
        verified += 1
        for _, finish, label in presentations[bisect_left(present_starts, start):bisect_left(present_starts, end)]:
            hidden_starts += 1
            if finish <= end:
                completed[label] += 1
        for event in inputs[bisect_left(input_starts, start):bisect_left(input_starts, end)]:
            if event["end"] <= end:
                callbacks[event["label"]] += 1
    return dict(eligibleReopens=len(reopens), verifiedHiddenIntervals=verified,
                presentCallsStarted=hidden_starts, completedPresentsByCallback=dict(completed),
                completedWindowAndLoopCallbacks=dict(callbacks))


def correlate(text, native_dxgi, inventory, single):
    presentation = inventory["presentation"]
    frequency, pid = presentation["qpcFrequency"], presentation["guiPid"]
    spans = parse(text, pid, frequency, single)
    hwnd_set = {q["hwnd"] for q in inventory["allRequests"]}
    owners = {(s["hwnd"], s["thread"]) for s in spans if s["label"] in ("show", "hide")}
    if len(owners) != 1 or {hwnd for hwnd, _ in owners} != hwnd_set or pid != inventory["guiPid"]:
        raise ValueError("The external HWND or PID differs from the traced UI")
    hwnd, ui = next(iter(owners))
    pipe = {s["thread"] for s in spans if s["label"] == "pipe-open"}
    if (len(pipe) != 1 or ui in pipe or any(s["thread"] != ui for s in spans if s["label"] != "pipe-open")
            or any(s["label"] == "private-wake" for s in spans) != single):
        raise ValueError("Unexpected private pipe reader, UI thread or private wake delivery")
    groups = {label: [s for s in spans if s["label"] == label] for label in CALLBACKS | OPERATIONS}
    ticks = {label: [s["start"] for s in rows] for label, rows in groups.items()}
    def one(label, a, b):
        lo, hi = bisect_left(ticks[label], a), bisect_right(ticks[label], b)
        if hi != lo + 1:
            raise ValueError(f"Expected exactly one native {label} in the external request")
        return groups[label][lo]
    factor = 1000 / frequency
    results = {"close": [], "reopen": []}
    states = {"close": Counter(), "reopen": Counter()}
    callbacks = [s for s in spans if s["label"] in CALLBACKS]
    starts = [s["start"] for s in callbacks]
    latest_end = list(accumulate((s["end"] for s in callbacks), max))
    commands_by_callback = Counter()
    reopens = []
    def callback_at(start, end):
        enclosing = callbacks[bisect_left(latest_end, end):bisect_right(starts, start)]
        return next((s["label"] for s in reversed(enclosing) if end <= s["end"]), "outside-recorded-callback")
    for q in inventory["eligibleResponses"]:
        a, b, opening = q["issuedQpc"], q["responseQpc"], q["action"] == "reopen"
        native = one("show" if opening else "hide", a, b)
        states[q["action"]][f'{native["before"]}-to-{native["after"]}'] += 1
        delivery = one("pipe-open" if opening else "close-event", a, native["start"])
        row = dict(issuedToInputMs=(delivery["start"] - a) * factor,
                   inputToVisibilityCallMs=(native["start"] - delivery["start"]) * factor,
                   visibilityCallMs=(native["end"] - native["start"]) * factor,
                   externalMinusVisibilitySampleMs=(b - native["sampled"]) * factor,
                   externalResponseMs=(b - a) * factor)
        active = callbacks[bisect_left(latest_end, a):bisect_left(starts, b)]
        row.update(uiCallbackWallMs=occupied_ticks(active, a, b) * factor,
                   redrawCallbackWallMs=occupied_ticks((s for s in active if s["label"] == "redraw-event"), a, b) * factor,
                   resizeCallbackWallMs=occupied_ticks((s for s in active if s["label"] == "resize-event"), a, b) * factor)
        if opening:
            reopens.append(native)
            dequeued = one("open-dequeued", delivery["start"], native["start"])
            commands_by_callback[callback_at(dequeued["start"], dequeued["end"])] += 1
            row.update(pipeWakeCallMs=(delivery["end"] - delivery["start"]) * factor,
                       pipeToUiDequeueMs=(dequeued["start"] - delivery["start"]) * factor,
                       dequeueToVisibilityCallMs=(native["start"] - dequeued["start"]) * factor)
            # A caller can observe WS_VISIBLE before the UI thread returns from ShowWindow.
            # Focus and the explicit redraw still belong to this activation, even after the response.
            position = bisect_right(ticks["show"], native["start"])
            until = ticks["show"][position] - 1 if position < len(ticks["show"]) else spans[-1]["end"]
            for label, key in (("focus", "focusCallMs"), ("request-redraw", "explicitRedrawCallMs")):
                op = one(label, native["sampled"], until)
                row[key] = (op["end"] - op["start"]) * factor
        results[q["action"]].append(row)
    by_callback = Counter()
    threads = Counter()
    first, last = presentation["firstPassBoundsQpc"]
    all_presents = []
    for line in native_dxgi.splitlines():
        if not line.startswith("DXGI "):
            continue
        process, thread, interval, flags, start, end = map(int, line.split()[1:])
        if process != pid or thread <= 0 or end < start or flags & 1:
            raise ValueError("The DXGI call does not belong to this process and clock")
        label = callback_at(start, end) if thread == ui else "other-owned-thread"
        all_presents.append((start, end, label))
        if not first <= start <= end <= last:
            continue
        if (process, interval, flags & 0x201) != (pid, 0, 0) or thread <= 0:
            raise ValueError("The native presentation does not belong to the owned Mailbox process")
        threads[thread] += 1
        by_callback[label] += 1
    if sum(by_callback.values()) != presentation["successfulPresents"]:
        raise ValueError("The number of successful, attributable scan presents differs")
    actions = {}
    for action, rows in results.items():
        if len(rows) < 5:
            raise ValueError(f"Insufficient real {action} observations")
        actions[action] = dict(requests=len(rows), nativeVisibilityBeforeAfter=dict(states[action]), durations={name: {
            "median": median(row[name] for row in rows), "p95": recorder.p95([row[name] for row in rows])}
            for name in rows[0]},
            responseBeforeNativeVisibilitySample=sum(row["externalMinusVisibilitySampleMs"] < 0 for row in rows))
    return dict(guiPid=pid, hwnd=hwnd, uiThread=ui, pipeThread=pipe.pop(), frequency=frequency, singleWake=single,
                privateWakeCallbacks=len(groups["private-wake"]), activationsByUiCallback=dict(commands_by_callback),
                presentationThreads=dict(threads), presentsByUiCallback=dict(by_callback), actions=actions,
                hidden=hidden_presents(spans, reopens, all_presents, presentation["traceBoundsQpc"]))


def run(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, primary, check_device):
    baseline = json.loads(primary.read_text(encoding="utf-8"))
    if (baseline["presentMode"] != "Mailbox" or baseline["diagnosticControl"]
            or any(baseline["comparison"][key]["passed"] is None for key in METRICS)
            or any(record[k] != baseline[k] for k in ("revision", "target", "run", "attempt", "binary",
                                                       "baselineReceipt", "buildReceipt", "referenceBudgetSha256"))
            or record["inputs"]["workload"] != baseline["inputs"]["workload"]):
        raise ValueError("The ordinary retained comparison differs from the dispatch diagnostic")
    record["primaryResultSha256"] = sha(primary)
    record["dispatchObserverSha256"] = sha(HERE / "dispatch.py")
    record["cases"] = {}
    failures = []
    for index, name in enumerate(("root-repaint", "single-wake", "original-hidden-paint"), 1):
        trial = f"rust-{index}-scan"
        single = name == "single-wake"
        original = name == "original-hidden-paint"
        with ExitStack() as env:
            for key, value in (("IFW_QA_WINDOWS_DISPATCH", "1"), ("IFW_QA_WINDOWS_SINGLE_WAKE", str(int(single))),
                               ("IFW_QA_WINDOWS_HIDDEN_PAINT_CONTROL", str(int(original)))):
                os.environ[key] = value
                env.callback(os.environ.pop, key)
            observed = recorder.measure_scan(api, fixture, "rust", gui, files, area / trial, endpoint, user_sid,
                                             out, recorder.await_value, recorder.stop_subject, recorder.p95, token,
                                             presentation_trace=partial(trace_presentation, api, present, "Mailbox"))
        native_log, dxgi = out / (trial + ".log"), out / (trial + "-presents.log")
        if sha(dxgi) != observed["presentation"]["decodedEventsSha256"]:
            raise ValueError("Decoded DXGI events changed after their native observation")
        observed["device"] = check_device(native_log, "Mailbox")
        observed["subjectLogSha256"] = sha(native_log)
        record["cases"][name] = observed
        recorder.write(out / "result.json", record)
        log_text = native_log.read_text(encoding="utf-8")
        wakes = [s for s in log_text.splitlines() if s.startswith("WINDOW_WAKE ")]
        if wakes != (["WINDOW_WAKE mode=single"] if single else []):
            raise ValueError("The owned process started a different wake policy")
        controls = [s for s in log_text.splitlines() if s.startswith("WINDOW_HIDDEN_PAINT ")]
        if controls != (["WINDOW_HIDDEN_PAINT mode=original"] if original else []):
            raise ValueError("The owned process started a different hidden-root paint policy")
        observed["dispatch"] = correlate(log_text, dxgi.read_text(encoding="ascii"),
                                         observed, single)
        recorder.write(out / "result.json", record)
        hidden = observed["dispatch"]["hidden"]
        if hidden["verifiedHiddenIntervals"] < 5:
            failures.append(f"{name} has fewer than five verified hidden intervals")
        if not original and hidden["presentCallsStarted"]:
            failures.append(f"{name} presented to a confirmed hidden root window")
    if failures:
        raise ValueError(". ".join(failures))
