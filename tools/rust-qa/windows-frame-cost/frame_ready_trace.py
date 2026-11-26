"""Join one-shot registrations and actual WM_CLOSE delivery to external native clocks."""
from bisect import bisect_left, bisect_right
import re

HEADER = re.compile(r"FRAME_READY_BEGIN pid=(\d+) tid=(\d+) hz=(\d+) count=(\d+) dropped=(\d+)")
EVENT = re.compile(r"FRAME_READY (arm|reuse|input|close|signal|consume|present|cancel|discard) (\d+) (\d+) (\d+) (\d+) (\d+)")
END = re.compile(r"FRAME_READY_END immediate=(\d+)")


def read_trace(text, root, frequency):
    lines = [line for line in text.splitlines() if line.startswith("FRAME_READY")]
    head = HEADER.fullmatch(lines[0]) if lines else None
    tail = END.fullmatch(lines[-1]) if lines else None
    if not head or not tail:
        raise ValueError("Incomplete native readiness trace")
    pid, tid, hz, count, dropped = map(int, head.groups())
    if (min(pid, tid, hz, root["hwnd"]) <= 0 or (pid, tid, hz) != (root["pid"], root["tid"], frequency)
            or dropped or not 0 <= count <= 65_536 or len(lines) != count + 2):
        raise ValueError("Wrong owner, clock or incomplete readiness trace")
    last_end = last_token = last_generation = 0
    cycles = []
    grant = None
    active = None
    state = None
    for line in lines[1:-1]:
        m = EVENT.fullmatch(line)
        if not m:
            raise ValueError("Unknown frame-ready event")
        name = m[1]
        gen, token, hwnd, begin, end = map(int, m.groups()[1:])
        if (min(gen, token, begin) <= 0 or hwnd != root["hwnd"] or not last_end <= begin <= end
                or (name != "present" and begin != end)):
            raise ValueError("Unexpected original window, event order or native timing")
        last_end = end
        if name in ("arm", "reuse"):
            if active is not None or token <= last_token or gen < last_generation or token <= gen:
                raise ValueError("An overlapping or stale frame-ready registration was armed")
            if name == "reuse" and (not grant or grant["generation"] != gen):
                raise ValueError("A reused slot has no retained grant for the same surface generation")
            if name == "arm" and grant and grant["generation"] == gen:
                raise ValueError("The same surface attempted a second wait on an unspent frame slot")
            active = dict(generation=gen, token=token, begin=begin, source=name, inputs=[], closes=[])
            if name == "reuse":
                active["originalGrant"] = grant["token"]
                active["originalSignal"] = grant["signal"]
            grant = None
            last_token, last_generation, state = token, gen, "armed" if name == "arm" else "drawing"
            continue
        if active is None or (gen, token) != (active["generation"], active["token"]):
            raise ValueError("Event from a replaced registration or generation")
        if name in ("input", "close") and state == "armed":
            active["inputs" if name == "input" else "closes"].append(begin)
        elif name == "signal" and state == "armed":
            active["signal"], state = begin, "ready"
        elif name == "consume" and state == "ready":
            active["consume"], state = begin, "drawing"
        elif ((name == "present" or name == "discard") and state == "drawing") or (name == "cancel" and state in ("armed", "ready")):
            active["end"] = end
            active["result"] = name
            if name == "present":
                active["present"] = [begin, end]
            elif "signal" in active or "originalGrant" in active:
                grant = dict(generation=gen, token=active.get("originalGrant", token),
                             signal=active["originalSignal"] if "originalGrant" in active else active["signal"])
            cycles.append(active)
            active = state = None
        else:
            raise ValueError("Unexpected one-shot state transition")
    if active:
        raise ValueError("A native registration survived the original subject")
    return dict(immediate=int(tail[1]), cycles=cycles)


def intervals(cycles, frames, bounds, requests, eligible):
    """Compare only completed ETW-recorded presents. Keep unavailable natural input opportunities explicit."""
    starts = [begin for begin, _, _ in frames]
    begins = [cycle["begin"] for cycle in cycles]
    accepted = {q["issuedQpc"] for q in eligible}
    closes, serviced = [], []
    for q in requests:
        if q["action"] != "close" or q["issuedQpc"] not in accepted:
            continue
        issued, hidden = q["issuedQpc"], q["responseQpc"]
        idx = bisect_left(begins, issued) - 1
        if idx < 0:
            continue
        cycle = cycles[idx]
        if cycle["source"] != "arm" or issued >= cycle.get("signal", cycle["end"]):
            continue
        closes.append(dict(token=cycle["token"], issuedQpc=issued, hiddenQpc=hidden))
        # Native dispatch entered WM_CLOSE before the pending registration was granted.
        # The independent observer then saw the original HWND hidden before issuing another request.
        hooks = [tick for tick in cycle["closes"] if issued < tick <= hidden]
        if (len(hooks) == 1 and cycle["result"] == "cancel" and "signal" not in cycle
                and hooks[0] <= cycle["end"] <= hidden):
            serviced.append(dict(closes[-1], nativeCloseQpc=hooks[0], cancelledQpc=cycle["end"]))
    windows = [(q["responseQpc"], next_q["issuedQpc"]) for q, next_q in zip(requests, requests[1:])
               if q["action"] == "reopen" and next_q["action"] == "close" and q["issuedQpc"] in accepted]
    shown = [lo for lo, _ in windows]
    hidden = [q["responseQpc"] for q in requests if q["action"] == "close"]
    resumes = []
    reused = []
    for cycle in cycles:
        if cycle["result"] != "present":
            continue
        lo, hi = cycle["present"]
        if not (bounds[0] <= lo and hi <= bounds[1]):
            continue
        i = bisect_left(starts, lo)
        if (i == len(frames) or frames[i][1] > hi or frames[i][2] != 0
                or (i + 1 < len(starts) and starts[i + 1] <= hi)):
            raise ValueError("The resumed submission does not enclose a unique successful Mailbox present")
        ready = cycle.get("signal", cycle["begin"])
        vis = bisect_right(shown, ready) - 1
        if vis >= 0 and hi < windows[vis][1] and windows[vis][0] < frames[i][0]:
            proof = dict(token=cycle["token"], visibleQpc=windows[vis][0], beginQpc=frames[i][0], endQpc=frames[i][1])
            if cycle["source"] == "reuse":
                preceding = bisect_left(hidden, proof["visibleQpc"]) - 1
                if preceding >= 0 and cycle["originalSignal"] < hidden[preceding]:
                    reused.append(dict(proof, reuseQpc=ready, originalGrant=cycle["originalGrant"],
                                       originalSignalQpc=cycle["originalSignal"], hiddenQpc=hidden[preceding]))
            else:
                resumes.append(dict(proof, signalQpc=ready))
    return dict(opportunities=closes, serviced=serviced, visibleResumes=resumes, visibleReuse=reused)
