"""Replay one native CPU device replacement against its original worker, windows and field captures."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import cpu_build
from inputs import recorder, sha
from frame_latency import visible_fields

spec = importlib.util.spec_from_file_location("cpu_paint_measurement", HERE.parent / "measure.py")
paint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paint)

WORKER = "ifw-performance-worker.exe"
ADAPTER = "ADAPTER Dx12 Cpu Microsoft Basic Render Driver"
LOSS = "GRAPHICS_LOST generation=1 reason=Destroyed"
RETRY = "GRAPHICS_ATTEMPT generation=2 policy=cpu"
PASS = re.compile(r"INVENTORY_COMPLETE files=0 changed=0 pass=(\d+)")


def read(path):
    return json.loads(path.read_bytes())


def sources(revision):
    result = paint.sources(revision)
    for path in (HERE / "run.py", HERE / "readback.py", Path(__file__).resolve(), HERE.parent / "cpu_build.py",
                 QA / "windows-warm-window/frame_latency.py", QA / "windows-launcher/observe.py", QA / "windows-desktop/win32.py"):
        relative = path.relative_to(QA.parents[1]).as_posix()
        committed = subprocess.check_output(["git", "show", revision + ":" + relative], cwd=QA.parents[1])
        if sha(path) != sha256(committed).hexdigest():
            raise ValueError("Recovery observer differs from its recorded source revision")
        result[relative] = sha(path)
    return result


def generations(text):
    lines = text.splitlines()
    tags = ("GRAPHICS_ATTEMPT ", "GRAPHICS_MEMORY ", "GRAPHICS_READY ", "GRAPHICS_DESTROY ", "GRAPHICS_LOST ",
            "GRAPHICS_ERROR ", "GRAPHICS_RETRY ", "GRAPHICS_UNAVAILABLE ", "ADAPTER ", "CPU_PAINT_FALLBACK")
    sequence = [line for line in lines if line.startswith(tags)]
    error = [line for line in sequence if line.startswith("GRAPHICS_ERROR ")]
    if (len(error) != 1 or not error[0].startswith("GRAPHICS_ERROR device_lost=true detail=")
            or sequence != ["GRAPHICS_ATTEMPT generation=1 policy=preferred", "GRAPHICS_MEMORY generation=1 hint=MemoryUsage",
                            "GRAPHICS_READY generation=1", ADAPTER, "GRAPHICS_DESTROY generation=1", LOSS, error[0],
                            "GRAPHICS_RETRY generation=1", RETRY, "GRAPHICS_MEMORY generation=2 hint=MemoryUsage",
                            "GRAPHICS_READY generation=2", ADAPTER]):
        raise ValueError("Expected exactly one real WARP loss and one successful CPU-policy recreation")
    return text.split(RETRY)


def completed(text):
    counts = []
    for line in text.splitlines():
        if line.startswith("INVENTORY_COMPLETE"):
            match = PASS.fullmatch(line)
            if not match or int(match[1]) != len(counts):
                raise ValueError("Unexpected synthetic inventory result or pass sequence")
            counts.append(int(match[1]))
    return len(counts)


def check_members(job, pids, creation):
    gui, worker = pids
    members = {row["pid"]: row for row in job["members"]}
    if (len(members) != len(job["members"]) or sorted(members) != job["pids"] or not {gui, worker} <= members.keys()
            or len(creation) != 2 or min(creation) <= 0):
        raise ValueError("Incomplete original GUI and inventory job membership")
    for pid, role, image, stamp in zip(pids, ("primary", "worker"), ("cpu.exe", WORKER), creation, strict=True):
        row = members[pid]
        if row["role"] != role or row["image"].casefold() != image or row["creation100ns"] != stamp:
            raise ValueError(f"The held {role} process changed in the recovery job")
    if members[worker]["parent"] != gui:
        raise ValueError("The held worker no longer belongs to the original GUI")
    parents = set()
    for pid in members.keys() - {gui, worker}:
        row = members[pid]
        if (pid <= 0 or row["role"] != "systemConsoleHost" or row["image"].casefold() != "conhost.exe"
                or row["parent"] not in pids or row["parent"] in parents or row["creation100ns"] <= 0):
            raise ValueError(f"Unexpected additional member {pid} in the recovery job")
        parents.add(row["parent"])


def check(out, record):
    raw = (out / "subject.log").read_bytes()
    text = raw.decode()
    first, second = generations(text)
    before, after = record["fields"]
    process, worker = record["pids"]
    low, high = before["qpc"]
    lower, upper = after["qpc"]
    quit_at = record["quitQpc"]
    if (record["subjectLog"] != sha(out / "subject.log") or worker == process or min(process, worker) <= 0
            or [line for line in text.splitlines() if line.startswith("INVENTORY_WORKER")] != [f"INVENTORY_WORKER pid={worker}"]
            or not 0 < low < high <= record["destroyQpc"] < lower < upper <= quit_at
            or before["root"]["hwnd"] == after["root"]["hwnd"]
            or any(row["root"]["pid"] != process for row in (before, after))
            or record["termination"] != {"method": "control-Q", "exitCode": 0}
            or record["workerExit"] != 0 or record["emptyJob"] is not True or record["profileRemoved"] is not True
            or len([line for line in text.splitlines() if re.fullmatch(r"DRAINED passes=[1-9][0-9]*", line)]) != 1):
        raise ValueError("Invalid GUI, inventory process, device fault or shutdown timeline")
    snapshots = record["workers"]
    if len(snapshots) != 3 or not (high <= snapshots[0]["qpc"] <= record["destroyQpc"] < lower <= upper <= snapshots[1]["qpc"]
                                   < snapshots[2]["qpc"] <= quit_at):
        raise ValueError("Missing process observations across device destruction and recovery")
    previous = 0
    for row in snapshots:
        check_members(row["job"], record["pids"], record["creation100ns"])
        length = row["logBytes"]
        prefix = raw[:length]
        if not previous <= length <= len(raw) or length <= 0:
            raise ValueError("Reordered observer log prefixes")
        previous = length
        if (sha256(prefix).hexdigest() != row["logSha256"] or not prefix.endswith(b"\n")
                or row["passes"] != completed(prefix.decode()) or row["passes"] < 2):
            raise ValueError("The held GUI or worker changed or lacks complete inventory reports")
    if (b"GRAPHICS_DESTROY " in raw[:snapshots[0]["logBytes"]] or
            b"GRAPHICS_READY generation=2" not in raw[:snapshots[1]["logBytes"]] or
            snapshots[2]["passes"] <= snapshots[1]["passes"] or completed(text) < snapshots[2]["passes"]):
        raise ValueError("The original worker did not finish another inventory after recovery")
    counts = []
    for row, chunk in ((before, first), (after, second)):
        hwnd = row["root"]["hwnd"]
        if ([event for h, event, _ in record["lifetimes"] if h == hwnd] != ["create", "destroy"]
                or not any(e["event"] == "show" and e["hwnd"] == hwnd for e in record["windowEvents"])):
            raise ValueError("Unobserved native window lifetime")
        series, _ = paint.frames(chunk, row["root"], record["frequency"])
        start, end = row["qpc"]
        count = sum(start <= a <= b <= end for a, b in series.complete)
        if not count:
            raise ValueError("No complete editor mesh and GDI flush during this visible field edit")
        counts.append(count)
    _, difference = visible_fields(out, process, (before["root"]["hwnd"], before["field"]),
                                   (after["root"]["hwnd"], after["field"]))
    return dict(gui=process, worker=worker, windows=[row["root"]["hwnd"] for row in (before, after)],
                meshFramesDuringEdits=counts, changedPixels=difference["pixels"],
                workerPassesAfterRecovery=snapshots[2]["passes"] - snapshots[1]["passes"])


def verify(cpu):
    out = cpu / "recovery"
    record = read(out / "result.json")
    if record["status"] != "passed":
        raise ValueError(f"Native device recovery {record['status']}: {record.get('error', 'no recorded diagnosis')}")
    timing = read(cpu / "result.json")
    cpu_build.verify(cpu, timing)
    source = timing["inputs"]["inventory"]
    baseline = cpu.parents[2] / "windows-performance" / ("native-" + timing["target"]) / "inputs.json"
    original = read(baseline)
    if (original["candidateRevision"] != timing["revision"] or original["target"] != timing["target"]
            or any(source[k] != original["inventory"][k] for k in ("compiledEntry", "approvedBundle", "packages", "sources"))):
        raise ValueError("The inventory worker and original baseline have different compiler inputs")
    if (any(record[k] != timing[k] for k in ("revision", "run", "attempt", "target"))
            or sources(record["revision"]) != record["sources"] or record["measurement"] != sha(cpu / "result.json")
            or record["images"] != [timing["binary"], source["worker"]] or sha(cpu / WORKER) != source["worker"]
            or recorder.pe_machine(cpu / WORKER) != 0x8664 or source["gui"] != timing["binary"]):
        raise ValueError("Unrelated native image, worker build or observation sources")
    result = check(out, record)
    if result != record["verified"]:
        raise ValueError("The detached recovery observation differs from the recorded result")
    return result
