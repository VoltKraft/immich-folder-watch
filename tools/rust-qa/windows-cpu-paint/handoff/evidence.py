"""Check the three visible textures against the original native blit and DXGI calls."""
from collections import Counter
import importlib.util
import re

from fixture_build import HERE, sha
import pixels

CPU_MEASURE = importlib.util.spec_from_file_location("ifw_texture_cpu_observer", HERE.parent / "measure.py")
cpu = importlib.util.module_from_spec(CPU_MEASURE)
CPU_MEASURE.loader.exec_module(cpu)

DRAW = re.compile(r"HANDOFF_DRAW ([012]) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)")
SWITCH = "CPU_PAINT_FALLBACK reason=sampler"


def drawings(text):
    for line in text.splitlines():
        if line.startswith("HANDOFF_DRAW"):
            match = DRAW.fullmatch(line)
            if not match:
                raise ValueError("Invalid texture draw receipt")
            phase, texture, *coords = map(int, match.groups())
            yield phase, texture, [list(pair) for pair in zip(coords[::2], coords[1::2], strict=True)]


def scene(text):
    actions, progress = [], []
    for line in text.splitlines():
        if line == SWITCH:
            actions.append(("fallback", None))
            continue
        if not line.startswith("HANDOFF_"):
            continue
        if line.startswith("HANDOFF_DRAW"):
            phase, texture, centers = next(drawings(line))
            if not progress or progress[-1] != phase:
                actions.append(("draw", phase))
                progress.append(phase)
            continue
        m = re.fullmatch(r"HANDOFF_(FULL|PARTIAL|NEAREST) id=(\d+)", line)
        if not m:
            raise ValueError("Unknown texture operation")
        actions.append((m[1], int(m[2])))
    if len(actions) != 7:
        raise ValueError("Missing, repeated or re-ordered texture update, draw or device transition")
    original, nearest = actions[0][1], actions[4][1]
    if (not isinstance(original, int) or original <= 0 or nearest in (None, 0, original)
            or actions != [("FULL", original), ("draw", 0), ("PARTIAL", original), ("draw", 1),
                           ("NEAREST", nearest), ("draw", 2), ("fallback", None)]
            or any(texture != original for _, texture, _ in drawings(text))):
        raise ValueError("The fallback did not preserve the original managed texture")
    return original, nearest


def dxgi_calls(text, root, hz, bounds, switch, observed):
    rows = text.splitlines()
    if len(rows) < 5 or rows[:2] != ["READY", f"QPC {root['pid']} {hz}"] or rows[-1] != "COMPLETE":
        raise ValueError("Incomplete external DXGI observation")
    reported, stops, eligible = [], [], []
    for line in rows[2:-1]:
        if hit := re.fullmatch(r"P DXGI (\d+)", line):
            reported.append(int(hit[1]))
            continue
        match = re.fullmatch(r"DXGI (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", line)
        if not match:
            raise ValueError("Unexpected DXGI provider or decoder output")
        pid, tid, interval, flags, start, end = map(int, match.groups())
        if (pid != root["pid"] or tid != root["tid"] or flags & 1 or interval > 4 or
                not bounds[0] <= switch <= start <= end <= bounds[1]):
            raise ValueError("DXGI present predates the handoff or belongs to another native root thread")
        stops.append(end)
        if end <= observed:
            eligible.append((start, end))
    if Counter(stops) != Counter(reported) or not eligible:
        raise ValueError("No original-thread DXGI present completed before the changed pixels")
    return eligible


def check(out, record):
    root, hz = record["root"], record["frequency"]
    samples = record["phases"]
    text = (out / "subject.log").read_text(encoding="utf-8")
    lines = text.splitlines()
    cpu.check_device_lifetime(lines)
    if ([s for s in lines if s.startswith("CPU_PAINT_FALLBACK")] != [SWITCH]
            or [s for s in lines if s.startswith("ADAPTER ")] != ["ADAPTER Dx12 Cpu Microsoft Basic Render Driver"]
            or len([s for s in lines if re.fullmatch(r"DRAINED passes=[1-9][0-9]*", s)]) != 1):
        raise ValueError("The CPU-to-wgpu switch or ordinary GUI drain is missing")
    before, after = text.split(SWITCH)
    if (not before.rstrip().splitlines()[-1].startswith("GDI_PRESENT_END ") or
            any(s.startswith(("CPU_", "GDI_")) for s in after.splitlines())):
        raise ValueError("CPU did not permanently retire its GDI presenter at the sampler transition")
    original, nearest = scene(text)
    frames, _ = cpu.frames(before, root, hz)
    lower, upper = record["traceBoundsQpc"]
    if (hz <= 0 or not 0 < lower < upper or len(samples) != 3 or record["exitCode"] != 0
            or record["emptyJob"] is not True or record["profileRemoved"] is not True
            or record["creation100ns"] <= 0 or record["quitQpc"] < upper):
        raise ValueError("Incomplete capture or original GUI lifetime")
    events = [action for window, action, _tick in record["windowLifetime"] if window == root["hwnd"]]
    if events != ["create", "destroy"]:
        raise ValueError("The original retained HWND was recreated or not destroyed at Quit")
    previous = lower
    positions = list(drawings(text))
    for i, sample in enumerate(samples):
        lo, hi = sample["boundsQpc"]
        path = out / f"phase-{i}.ppm"
        centers = sample["clientCenters"]
        if (sample["phase"] != i or not previous <= sample["issuedQpc"] < lo <= hi <= upper or sample["root"] != root
                or sample["creation100ns"] != record["creation100ns"] or sample["jobPids"] != [root["pid"]]
                or any(len(pair) != 2 or not 2 <= pair[0] < root["width"]-2 or not 2 <= pair[1] < root["height"]-2 for pair in centers)
                or len(centers) != 3 or len({tuple(p) for p in centers}) != 3
                or sample["screenCenters"] != [[x+sample["origin"][0], y+sample["origin"][1]] for x,y in centers]
                or (i, original, centers) not in positions or sha(path) != sample["pixels"] or not pixels.colors(path.read_bytes(), i)):
            raise ValueError(f"Different native identity, phase, coordinates or displayed pixels in phase {i}")
        if i < 2 and not any(sample["issuedQpc"] <= a <= b <= lo for a,b in frames.complete):
            raise ValueError("No complete CPU-painted frame between the command and the pixel readback")
        previous = hi
    calls = dxgi_calls((out / "presents.log").read_text(encoding="ascii"), root, hz, (lower, upper), samples[2]["issuedQpc"], samples[2]["boundsQpc"][0])
    return dict(originalTexture=original, nearestTexture=nearest, fullCpuFrames=len(frames.complete),
                dxgiPresentsBeforeFinalPixels=len(calls), root=root, verifiedVisiblePhases=3)
