"""Compare the staged warm GUI with the complete WPF trials on this very same runner."""
import argparse
from contextlib import ExitStack
from functools import partial
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import uuid

from inputs import DX12_WAIT_OPTION, HERE, QA, ROOT, TARGETS, recorder, sha, subjects
from frame_latency import measured_generation, paired_frame_latency, visible_edits
from build import REFERENCE, REFERENCE_SOURCE_SHA256
from metrics import METRICS
from native import CleanupUnconfirmed, owned_directory, pin_path
from scan_present import start as trace_presentation
import dispatch


def reference(target, metadata):
    root = ROOT / "artifacts/rust/windows-performance" / ("native-" + target)
    report = json.loads((root / "result.json").read_text(encoding="utf-8"))
    inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    path = root / "reference-budget.json"
    fixed = json.loads(path.read_text(encoding="utf-8"))
    host = report["host"]
    if (not metadata["run"] or host["run"] != metadata["run"] or host["attempt"] != metadata["attempt"]
            or host["computerIdSha256"] != hashlib.sha256(os.environ["COMPUTERNAME"].encode()).hexdigest()
            or host["runnerImage"] != os.getenv("ImageVersion") or inputs["candidateRevision"] != metadata["revision"]
            or inputs["guiBinarySha256"] != metadata["baseline"] or inputs["target"] != target
            or inputs["guiReceiptSha256"] != metadata["baselineReceipt"] or inputs["referenceRevision"] != REFERENCE
            or inputs["referenceSourceSha256"] != REFERENCE_SOURCE_SHA256
            or report["budgetSha256"] != sha(path) or fixed["sourceInputsSha256"] != sha(root / "inputs.json")
            or recorder.summarize(report["trials"]["wpf"]) != fixed["reference"]
            or recorder.budgets(fixed["reference"]) != fixed["maximums"]):
        raise ValueError("No matching frozen WPF budget on this runner and revision")
    return path, fixed, inputs, report.get("comparison", {})


def paired_scan(mailbox_path, fifo):
    mailbox = json.loads(mailbox_path.read_text(encoding="utf-8"))
    if (mailbox["presentMode"] != "Mailbox" or mailbox["diagnosticControl"] or fifo["presentMode"] != "Fifo"
            or any(mailbox[key] != fifo[key] for key in
                   ("target", "run", "attempt", "revision", "binary", "buildReceipt", "referenceBudgetSha256", "observerInputs"))
            or mailbox["inputs"]["workload"] != fifo["inputs"]["workload"]):
        raise ValueError("The two DXGI presentation measurements use different inputs")
    measurements = {}
    for mode, data in (("Mailbox", mailbox), ("Fifo", fifo)):
        if (len(data["trials"]) != recorder.TRIALS
                or any(data["comparison"][name]["passed"] is None for name in METRICS)):
            raise ValueError("The DXGI comparison needs all eleven measured metrics from each mode")
        metrics = {}
        for name in ("scan_close_p95_ms", "scan_reopen_p95_ms"):
            sample = data["comparison"][name]
            if sample["maximum"] != fifo["comparison"][name]["maximum"]:
                raise ValueError("The two presentation measurements use different WPF maximums")
            metrics[name] = sample
        measurements[mode] = metrics
    return dict(mailboxResultSha256=sha(mailbox_path), metrics=measurements)


def main(target, variant="mailbox"):
    api, _, binary, base, record = subjects(target)
    folder, mode, frames = {
        "mailbox": ("measured", "Mailbox", 1),
        "fifo": ("measured-fifo", "Fifo", 1),
        "dispatch": ("dispatch", "Mailbox", 1),
        "dwm-transitions": ("dwm-transitions", "Mailbox", 1),
        "frame-cost": ("frame-cost", "Mailbox", 1),
        "frame-ready": ("frame-ready", "Mailbox", 1),
        "deferred-frame": ("deferred-frame", "Mailbox", 1),
        "gdi-present": ("gdi-present", "GDI", None),
        "cpu-paint": ("cpu-paint", "CPU-GDI", None),
        "mailbox-two": ("measured-mailbox-two", "Mailbox", 2),
    }[variant]
    out = base / folder
    out.mkdir()
    record.update(status="running", trials=[], presentMode=mode, desiredMaximumFrameLatency=frames,
                  diagnosticControl=variant != "mailbox",
                  observerInputs={n: sha(HERE / n) for n in ("measure.py", "frame_latency.py", "inputs.py", "scan_present.py")})
    try:
        if any(k in os.environ for k in ("IFW_QA_WINDOWS_RESIDENCY", "IFW_QA_WINDOWS_PRESENT_CONTROL",
                                         "IFW_QA_WINDOWS_DISPATCH", "IFW_QA_WINDOWS_SINGLE_WAKE",
                                         "IFW_QA_WINDOWS_HIDDEN_PAINT_CONTROL", "IFW_QA_WINDOWS_FRAME_COST",
                                         "IFW_QA_WINDOWS_GDI_PRESENT", "IFW_QA_CPU_PAINT", "IFW_QA_DWM_TRANSITIONS")):
            raise ValueError("Select the requested diagnosis using the recorder option")
        if variant == "dwm-transitions" and target != "x86_64-pc-windows-msvc":
            raise ValueError("The DWM comparison requires native Windows x64")
        budget, fixed, original, record["ordinaryComparison"] = reference(target, record)
        before = sha(budget)
        record["referenceBudgetSha256"] = before
        if variant == "cpu-paint":
            if target != "x86_64-pc-windows-msvc":
                raise ValueError("The CPU renderer comparison requires native Windows x64")
            directory = QA / "windows-cpu-paint"
            sys.path.insert(0, str(directory))
            import cpu_build
            spec = importlib.util.spec_from_file_location("ifw_cpu_measure", directory / "measure.py")
            cpu_case = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cpu_case)
            binary = cpu_build.build(out, base, record)
        if variant == "gdi-present":
            sys.path.insert(0, str(QA / "windows-gdi-present"))
            import gdi_build
            import gdi_case
            binary = gdi_build.build(out, base, record)
        if variant in ("deferred-frame", "frame-cost", "frame-ready"):
            sys.path.insert(0, str(QA / "windows-frame-cost"))
            if variant == "frame-ready":
                import frame_ready_build
                import frame_ready_case
                binary = frame_ready_build.build(out, base, record)
            elif variant == "deferred-frame":
                import deferred_build
                import deferred_case
                if target != "x86_64-pc-windows-msvc":
                    raise ValueError("Deferred frames require a native Windows x64 host")
                binary = deferred_build.build(out, base, record)
            else:
                import frame_case
                binary = frame_case.prepare_subject(base, out, budget, record)
        with ExitStack() as scope:
            if variant == "gdi-present":
                os.environ["IFW_QA_WINDOWS_GDI_PRESENT"] = "1"
                scope.callback(os.environ.pop, "IFW_QA_WINDOWS_GDI_PRESENT")
            if DX12_WAIT_OPTION in os.environ and os.environ[DX12_WAIT_OPTION].casefold() != "wait":
                raise ValueError("The native DX12 frame latency comparison requires Wait mode")
            if DX12_WAIT_OPTION not in os.environ:
                os.environ[DX12_WAIT_OPTION] = "Wait"
                scope.callback(os.environ.pop, DX12_WAIT_OPTION)
            if variant in ("fifo", "mailbox-two"):
                os.environ["IFW_QA_WINDOWS_PRESENT_CONTROL"] = variant
                scope.callback(os.environ.pop, "IFW_QA_WINDOWS_PRESENT_CONTROL")
            area = scope.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
            gui, files, sources = recorder.build_subject(area, out, binary, target, recorder.pe_machine)
            for key in ("compiledEntry", "approvedBundle", "packages", "sources"):
                if sources[key] != original["inventory"][key]:
                    raise ValueError(f"Different native inventory baseline input: {key}")
            if sources["gui"] != record["binary"]:
                raise ValueError("The staged warm executable differs from the native build")
            present = area / "present.exe"
            driver = QA / "windows-performance"
            for name in ("present.cpp", "etw-owned.h", "run.py", "metrics.py", "native.py"):
                if sha(driver / name) != original["drivers"][name]:
                    raise ValueError(f"Different native observer input: {name}")
            for name in ("observe-windows-gui.py", "windows_observer.py", "storage/evidence.py"):
                if sha(QA / name) != original["sharedDrivers"][name]:
                    raise ValueError(f"Different shared observer input: {name}")
            with (out / "present-build.log").open("wb") as log:
                subprocess.run(["cl.exe", "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/utf-8",
                                "/DUNICODE", "/D_UNICODE", str(driver / "present.cpp"), "/link", "advapi32.lib", "tdh.lib"],
                               cwd=area, stdout=log, stderr=subprocess.STDOUT, check=True)
            expected = 0xaa64 if target.startswith("aarch64-") else 0x8664
            if recorder.pe_machine(present) != expected:
                raise ValueError("Wrong presentation observer architecture")
            worker = gui.with_name("ifw-performance-worker.exe")
            images = {gui: sources["gui"], worker: sources["worker"], present: sha(present)}
            if files:
                images[files] = sources["fileObserver"]
            for folder in {p.parent for p in images}:
                scope.enter_context(pin_path(api, folder, True))
            for path, digest in images.items():
                scope.enter_context(pin_path(api, path, False))
                if sha(path) != digest:
                    raise ValueError("A pinned native measurement input changed")
            if variant == "cpu-paint":
                retained_worker = out / worker.name
                shutil.copyfile(worker, retained_worker)
                if sha(retained_worker) != sources["worker"]:
                    raise ValueError("The retained recovery worker differs from the measured worker")
            token, workload = recorder.create_fixture(area, scope, api)
            scope.enter_context(pin_path(api, area / "files", True))
            for key, value in workload.items():
                if original["workload"].get(key) != value:
                    raise ValueError("Different baseline workload")
            record["inputs"] = dict(inventory=sources, present=images[present], workload=workload)
            fixture, user_sid = recorder.load_windows_fixture(), recorder.sid()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline:
                offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                offline.bind(("127.0.0.1", 0))
                endpoint = "http://127.0.0.1:" + str(offline.getsockname()[1])
                if variant == "dwm-transitions":
                    import dwm_transitions
                    dwm_transitions.measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget)
                    if sha(budget) != before:
                        raise ValueError("The WPF budget changed during the DWM comparison")
                    record["status"] = "dwm-transitions-observed"
                    return 0
                if variant == "frame-ready":
                    frame_ready_case.measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget)
                    if sha(budget) != before:
                        raise ValueError("The WPF budget changed during the frame-ready trial")
                    record["status"] = "frame-ready-recorded"
                    return 0
                if variant in ("deferred-frame", "gdi-present", "cpu-paint"):
                    if variant == "cpu-paint":
                        case = cpu_case
                    else:
                        case = gdi_case if variant == "gdi-present" else deferred_case
                    case.measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record, budget)
                    if sha(budget) != before:
                        raise ValueError("The WPF budget changed during the renderer comparison")
                    record["status"] = variant + "-observed"
                    return 0
                if variant == "frame-cost":
                    frame_case.measure(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record)
                    if sha(budget) != before:
                        raise ValueError("The WPF budget changed during the frame diagnosis")
                    record["status"] = "frame-cost-observed"
                    return 0
                if variant == "dispatch":
                    if not files:
                        raise ValueError("The dispatch comparison requires the native inventory observer")
                    dispatch.run(api, fixture, gui, files, present, area, endpoint, user_sid, out, token, record,
                                 base / "measured/result.json", partial(measured_generation, dispatch_trace=True))
                    if sha(budget) != before:
                        raise ValueError("The WPF budget changed during the dispatch diagnosis")
                    record["status"] = "dispatch-observed"
                    return 0
                for number in range(1, recorder.TRIALS + 1):
                    name = "rust-" + str(number)
                    row = recorder.trial(api, fixture, "rust", gui, present, area / name, endpoint, user_sid,
                                         expected, out / (name + ".log"), token)
                    record["trials"].append(row)
                    row["device"] = measured_generation(out / (name + ".log"), mode, frame_latency=frames)
                    try:
                        if not files:
                            raise ValueError("File observer was not built")
                        row["scan"] = recorder.measure_scan(api, fixture, "rust", gui, files, area / (name + "-scan"),
                                                            endpoint, user_sid, out, recorder.await_value,
                                                            recorder.stop_subject, recorder.p95, token,
                                                            presentation_trace=partial(trace_presentation, api, present, mode))
                        row["scan"]["device"] = measured_generation(out / (name + "-scan.log"), mode, frame_latency=frames)
                        row["metrics"].update(row["scan"]["metrics"])
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                        if CleanupUnconfirmed.in_chain(exc):
                            raise
                        row["scan"] = {"error": f"{type(exc).__name__}: {exc}"}
                    recorder.write(out / "result.json", record)
        if sha(budget) != before:
            raise ValueError("The WPF budget changed during the warm comparison")
        rows = recorder.comparison(fixed["maximums"], recorder.summarize(record["trials"]))
        record["comparison"] = rows
        record["status"] = ("over-budget" if any(r["passed"] is False for r in rows.values()) else
                            "partial" if any(r["passed"] is None for r in rows.values()) else "measured-metrics-passed")
        if variant == "fifo":
            # A complete old-policy control records its genuine failures against the same WPF maximums.
            record["pairedScan"] = paired_scan(base / "measured/result.json", record)
            return 0
        if variant == "mailbox-two":
            record["pairedFrameLatency"] = paired_frame_latency(base, record, fixed["maximums"])
            record["visibleEdits"] = visible_edits(base, record)
        return int(record["status"] != "measured-metrics-passed")
    except Exception as exc:
        record.update(status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        recorder.write(out / "result.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    mode = parser.add_mutually_exclusive_group()
    parser.set_defaults(variant="mailbox")
    mode.add_argument("--fifo-control", dest="variant", action="store_const", const="fifo", help="measure the previous DXGI interval on this same executable")
    mode.add_argument("--mailbox-two", dest="variant", action="store_const", const="mailbox-two", help="compare one and two queued DX12 Mailbox frames on this executable")
    mode.add_argument("--dispatch", dest="variant", action="store_const", const="dispatch", help="trace Mailbox activation and compare hidden-root paint policies")
    mode.add_argument("--frame-cost", dest="variant", action="store_const", const="frame-cost",
                      help="build and trace the additional x64 root-repaint diagnostic after ordinary dispatch")
    mode.add_argument("--deferred-frame", dest="variant", action="store_const", const="deferred-frame",
                      help="compare one native x64 trial with timed redraws on an unready DX12 frame")
    mode.add_argument("--frame-ready", dest="variant", action="store_const", const="frame-ready",
                      help="compare a native one-shot frame-ready event with the ordinary Windows x64 GUI")
    mode.add_argument("--gdi-present", dest="variant", action="store_const", const="gdi-present",
                      help="measure the retained egui view rendering offscreen with WARP and presenting through GDI")
    mode.add_argument("--cpu-paint", dest="variant", action="store_const", const="cpu-paint",
                      help="rasterize the retained egui editor on the CPU and observe its native GDI transfers")
    mode.add_argument("--dwm-transitions", dest="variant", action="store_const", const="dwm-transitions",
                      help="compare two native Windows x64 inventories on the ordinary and transitions-disabled root")
    args = parser.parse_args()
    raise SystemExit(main(args.target, args.variant))
