"""Use the source-verified Windows renderer in the existing display observation."""
import ctypes as c
from ctypes import wintypes as w
from hashlib import sha256
import re
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QA = ROOT / "tools/rust-qa"
WARM = QA / "windows-warm-window"
sys.path.insert(0, str(WARM))
from frame_latency import measured_generation
from inputs import DX12_WAIT_OPTION
from window_lifetime import WindowLifetime


def subject(target, canonical_exe, folder, read, sha, report, isolated_vm):
    select = runpy.run_path(str(QA / "windows-launcher/retained_subject.py"))["select"]
    canonical = read(folder / "build.json")
    _, binary, paired = select(target, canonical_exe, canonical, folder / "graph.json", sha, isolated_vm=isolated_vm)
    warm = read(ROOT / "artifacts/rust/windows-warm-window" / target / "build.json")
    compiler = dict(row.split(": ", 1) for row in warm["nativeCompiler"].splitlines() if ": " in row)
    toolchain = read(ROOT / "rust/toolchain-inputs.json")
    if (paired["baselineReceipt"] != report["build"]["receiptSha256"] or warm["buildHost"] != report["host"]
            or compiler.get("host") != target or compiler.get("commit-hash") != toolchain["commit"]
            or compiler.get("release") != toolchain["version"]):
        raise ValueError("The display and retained native build do not share the expected host, compiler and canonical receipt")
    files = {**canonical["compilerSources"], **report["inputs"]}
    files.update({(WARM / name).relative_to(ROOT).as_posix(): digest for name, digest in paired["variantInputs"].items()})
    verify = runpy.run_path(str(QA / "windows-services/service_sources.py"))["verify_checkout"]
    if verify(ROOT, [ROOT / path for path in files], paired["revision"]) != files:
        raise ValueError("The observed display and its retained build differ from the Git sources")
    report["retainedBuild"] = {**paired, "nativeCompiler": warm["nativeCompiler"], "buildHost": warm["buildHost"]}
    return binary


def presentation(log, adapter):
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    def records(prefix):
        return [line for line in lines if line.startswith(prefix)]
    if (records("ADAPTER ") != [adapter] or not adapter.startswith("ADAPTER Dx12 ")
            or records("GRAPHICS_READY ") != ["GRAPHICS_READY generation=1"]
            or records("GRAPHICS_MEMORY ") != ["GRAPHICS_MEMORY generation=1 hint=MemoryUsage"]
            or records("GRAPHICS_DX12_WAIT ") != ["GRAPHICS_DX12_WAIT generation=1 policy=Wait"]
            or any(row.startswith(("GRAPHICS_LOST ", "GRAPHICS_ERROR ", "GRAPHICS_RETRY ", "GRAPHICS_UNAVAILABLE ",
                                   "WINDOW_RELEASED ")) for row in lines)):
        raise ValueError("The retained display did not keep its original DX12 device and Wait policy")
    surface = records("GRAPHICS_SURFACE ")
    if adapter.startswith("ADAPTER Dx12 Cpu "):
        if len(surface) != 1:
            raise ValueError("Missing native surface capability observation for the DX12 CPU adapter")
        match = re.fullmatch(r"GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=\[([A-Za-z, ]+)\]", surface[0])
        if match and "Mailbox" in match[1].split(", "):
            return {"adapter": adapter, **measured_generation(log, "Mailbox")}
        if not match and not surface[0].startswith("GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu error="):
            raise ValueError("Unrecognized CPU surface observation")
    elif surface:
        raise ValueError("The CPU surface observation does not belong to the selected DX12 adapter")
    if records("GRAPHICS_PRESENT "):
        raise ValueError("A presentation override was observed on the default adapter path")
    return dict(adapter=adapter, generation=1, waitPolicy="Wait", surface=surface,
                presentMode=None, desiredMaximumFrameLatency=None)


def archived_presenter(log, adapter, pid, hwnd, *, previous=None):
    """Identify the archived executable's route and last complete mesh transfer on the owned HWND."""
    raw = log.read_bytes()
    # The GUI can still be writing the next line while the field observer samples it.
    raw = raw[:raw.rfind(b"\n") + 1]
    if previous and (previous["logBytes"] > len(raw)
                     or sha256(raw[:previous["logBytes"]]).hexdigest() != previous["logSha256"]):
        raise ValueError("The live presenter log lost or changed the preceding observation")
    rows = raw.decode("utf-8", errors="replace").splitlines()
    if [line for line in rows if line.startswith("ADAPTER ")] != [adapter]:
        raise ValueError("The archived display adapter differs from its live subject")
    route = "wgpu-default"
    fallback = witness = transfer = None
    counts = {"GDI_PRESENT": 0, "GDI_PARTIAL": 0}
    finished = False
    for row in rows:
        if row.startswith("CPU_PAINT_MODE"):
            if (row != "CPU_PAINT_MODE backend=Dx12 device=Cpu selection=adapter" or route != "wgpu-default"
                    or adapter != "ADAPTER Dx12 Cpu Microsoft Basic Render Driver"):
                raise ValueError("Unexpected CPU painter selection")
            route = "cpu-gdi"
        elif row.startswith("CPU_PAINT_FALLBACK"):
            match = re.fullmatch(r"CPU_PAINT_FALLBACK reason=([a-z0-9-]+)", row)
            if not match or route != "cpu-gdi" or not finished:
                raise ValueError("Unexpected CPU painter fallback")
            route, fallback = "wgpu-fallback", match[1]
        elif row.startswith("GDI_PRESENT_END"):
            if (route != "cpu-gdi" or transfer is not None or finished
                    or row != f"GDI_PRESENT_END frames={counts['GDI_PRESENT']} partial={counts['GDI_PARTIAL']}"):
                raise ValueError("CPU painter final transfer counts differ")
            finished = True
        elif row.startswith(("GDI_", "CPU_FRAME")):
            if route != "cpu-gdi" or finished:
                raise ValueError("Transfer outside the selected CPU painter")
            kind, *fields = row.split()
            values = {key: int(value) for key, value in (pair.split("=", 1) for pair in fields)}
            if kind in counts:
                counts[kind] += 1
                if (transfer or values["frame"] != counts[kind] or values["hwnd"] != hwnd
                        or min(values[k] for k in ("tid", "width", "height", "start")) <= 0
                        or values["end"] < values["start"] or not 0 <= values["lines"] <= values["height"]
                        or (kind == "GDI_PRESENT" and values["lines"] != values["height"])):
                    raise ValueError("Invalid GDI transfer on the observed window")
                transfer = (kind, values)
            elif kind == "CPU_FRAME" and transfer:
                mode, dib = transfer
                if (values["pid"] != pid or values["seq"] != sum(counts.values()) or values["flushed"] != 1
                        or not 0 < values["begin"] <= values["rasterEnd"] <= dib["start"]
                        or any(values[k] != dib[k] for k in ("hwnd", "tid", "start", "end", "width", "height", "lines"))):
                    raise ValueError("CPU paint and GDI transfer have different owners, extents or timestamps")
                if mode == "GDI_PRESENT" and values["meshes"] > 0 and values["vertices"] >= 3 and values["indices"] >= 3:
                    witness = values
                transfer = None
            else:
                raise ValueError("Unmatched CPU paint or failed GDI transfer")
    if route == "cpu-gdi" and not witness:
        raise ValueError("No full mesh-bearing CPU frame on the observed window")
    return dict(route=route, fallbackReason=fallback, fullEditorFrame=witness,
                logBytes=len(raw), logSha256=sha256(raw).hexdigest())


def close(observer, lifetime, child, hwnd, log, adapter, wait, report, *, archived_cpu=False):
    record = report["retainedClose"] = dict(hwnd=hwnd, pid=child.pid)
    before = record["device"] = presentation(log, adapter)
    if archived_cpu:
        record["visiblePresenter"] = archived_presenter(log, adapter, child.pid, hwnd)
    observer.pump()
    first = record["visibilityStart"] = len(observer.events)
    observer.close_window(hwnd)

    def hidden():
        if child.poll() is not None:
            raise RuntimeError("The retained GUI exited during close")
        return observer.visible() is None and any(event["event"] == "hide" and event["hwnd"] == hwnd and event["root"]
                                                  for event in observer.events[first:])

    wait(hidden, "hide of the owned retained window")
    pid = w.DWORD()
    record["hideEvents"] = [e for e in observer.events[first:] if e["hwnd"] == hwnd]
    record["objectEvents"] = [row for row in lifetime.events if row[0] == hwnd]
    if archived_cpu:
        record["hiddenPresenter"] = archived_presenter(log, adapter, child.pid, hwnd, previous=record["visiblePresenter"])
    if (not observer.owner(hwnd, c.byref(pid)) or pid.value != child.pid or observer.is_visible(hwnd)
            or [row[1] for row in record["objectEvents"]] != ["create"] or child.poll() is not None
            or presentation(log, adapter) != before):
        raise ValueError("The hidden window or DX12 device lost its original owner or lifetime")
    return True
