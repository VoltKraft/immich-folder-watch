"""Correlate successful DXGI calls from the owned GUI with the inventory worker's first pass."""
from bisect import bisect_left

from inputs import recorder, sha


def correlate(text, pid, frequency, bounds, inventory, mode):
    lines = text.splitlines()
    clocks = [line for line in lines if line.startswith("QPC ")]
    if (not lines or lines[0] != "READY" or lines[-1] != "COMPLETE"
            or clocks != [f"QPC {pid} {frequency}"] or frequency <= 0):
        raise ValueError("Incomplete DXGI trace or mismatched native PID/QPC clock")
    calls = []
    for line in lines:
        if not line.startswith("DXGI "):
            continue
        process, thread, interval, flags, start, end = map(int, line.split()[1:])
        if process != pid or thread <= 0 or flags & 1 or not bounds[0] <= start <= end <= bounds[1]:
            raise ValueError("Invalid process identity, test present or time in the native DXGI trace")
        calls.append((interval, flags, start, end))
    requests = inventory["eligibleResponses"]
    first = inventory["passes"][0]
    # Skip initial configuration. The first completed, work-qualified reopen establishes a live HWND.
    start = max(first["firstFileQpc"], next(q["responseQpc"] for q in requests if q["action"] == "reopen"))
    end = first["lastFileQpc"]
    active = [c for c in calls if start <= c[2] <= c[3] <= end]
    expected = {"Fifo": 1, "Mailbox": 0}[mode]
    if len(active) < 5 or any(interval != expected or flags & 0x200 for interval, flags, _, _ in active):
        raise ValueError(f"Insufficient successful non-tearing DXGI {mode} calls in the verified first inventory")
    report = dict(guiPid=pid, qpcFrequency=frequency, traceBoundsQpc=bounds, firstPassBoundsQpc=[start, end],
                  successfulPresents=len(active), syncInterval=expected,
                  presentP95Ms=recorder.p95([(b - a) * 1000 / frequency for _, _, a, b in active]), actions={})
    eligible = [q for q in requests if start <= q["issuedQpc"] <= q["responseQpc"] <= end]
    responses = [q["responseQpc"] for q in eligible]
    longest = [0] * len(eligible)
    for _, _, begin, finish in active:
        index = bisect_left(responses, begin)
        while index < len(eligible) and eligible[index]["issuedQpc"] < finish:
            overlap = min(responses[index], finish) - max(eligible[index]["issuedQpc"], begin)
            longest[index] = max(longest[index], overlap)
            index += 1
    for action in ("close", "reopen"):
        longest_overlap = [ticks * 1000 / frequency for ticks, q in zip(longest, eligible, strict=True)
                           if q["action"] == action]
        if len(longest_overlap) < 5:
            raise ValueError(f"Insufficient independently timed first-pass {action} responses")
        report["actions"][action] = dict(requests=len(longest_overlap),
                                          requestsIntersectingPresent=sum(value > 0 for value in longest_overlap),
                                          longestPresentOverlapP95Ms=recorder.p95(longest_overlap))
    return report


def start(api, executable, mode, stack, proc, area, output):
    recorder.wait_running(proc)
    handle = recorder.checked(api.open(0x1000, False, proc.pid))
    stack.callback(api.close, handle)
    identity = api.process_identity(handle)
    if identity != api.process_identity(proc._handle):
        raise ValueError("The DXGI subject differs from the retained GUI process")
    before = api.clock()
    log = output / (area.name + "-presents.log")
    finish, _ = recorder.trace_start(stack, executable, proc.pid, area, timed_log=log)

    def collect(inventory):
        finish()
        after = api.clock()
        recorder.wait_running(proc)
        if api.process_identity(handle) != identity:
            raise ValueError("The native GUI identity changed during its DXGI trace")
        report = correlate(log.read_text(encoding="ascii"), proc.pid, api.frequency, [before, after], inventory, mode)
        report.update(guiCreation100ns=identity, decodedEventsSha256=sha(log))
        return report

    return collect
