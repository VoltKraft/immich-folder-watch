"""Measure native HWND visibility and changed screen pixels with the same host's WPF reference."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
from statistics import median
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
sys.path.insert(0, str(QA / "windows-warm-window"))
from inputs import TARGETS, recorder, sha, subjects
from measure import reference
from native import owned_directory, pin_path, start_owned_subject
from scan import MIN_RESPONSES, coverage
from window_lifetime import WindowLifetime
from witness import Witness

NAMES = ("idle_close_p95_ms", "idle_reopen_p95_ms", "scan_close_p95_ms", "scan_reopen_p95_ms")


def visible_frames_during_work(scan, trace, frequency):
    requests = scan["allRequests"]
    witness = scan["nativeWitness"]
    by_issue = {r["issuedQpc"]: n for n, r in enumerate(requests)}
    qualified = {by_issue[r["issuedQpc"]] for r in scan["eligibleResponses"]}
    frame_samples, screen_samples = [], []
    for n, r in enumerate(requests):
        close = r["action"] == "close"
        visible = witness["observations"][2 * n + (0 if close else 1)]
        frame = witness["frames"][visible["generation"] - 1]
        lo, hi = (r["issuedQpc"], r["responseQpc"]) if close else frame[2:4]
        frame_samples.append(dict(r, index=n, issuedQpc=lo, responseQpc=hi))
        lo, hi = visible["pixelQpc"]
        screen_samples.append(dict(r, index=n, issuedQpc=lo, responseQpc=hi))
    for series in (frame_samples, screen_samples):
        replay = coverage(trace, series, scan["passes"][0]["observedCompleteQpc"], scan["passes"][1]["observedCompleteQpc"],
                          frequency, scan["inventoryPid"], "rust")
        qualified &= {r["index"] for r in replay["eligibleResponses"]}
    observed = {action: [n for n in sorted(qualified) if requests[n]["action"] == action] for action in ("close", "reopen")}
    if any(len(indices) < MIN_RESPONSES for indices in observed.values()):
        raise ValueError("Too few transitions with independently witnessed changed pixels during actual file work")
    return observed


def idle(api, fixture, gui, trial, endpoint, out, token, machine):
    trial.mkdir()
    empty = trial / "empty"
    empty.mkdir()
    env = recorder.environment(trial, endpoint, True, empty, token)
    log = out / (trial.name + ".log")
    requests = []
    with ExitStack() as scope:
        stream = scope.enter_context(log.open("wb"))
        proc = start_owned_subject(scope, api, gui, trial, env, stream, True, recorder.stop_subject)
        windows = fixture.Windows(proc.pid)
        scope.callback(windows.close)
        api.resume_owned_process(proc.pid)
        worker = recorder.owned_worker(api, proc, log, recorder.await_value)
        handle = recorder.checked(api.open(0x0410, False, worker))
        scope.callback(api.close, handle)
        if api.machine(handle) != (machine, machine):
            raise ValueError("The GDI control worker is not native")
        identity = api.process_identity(handle)
        proc.stdin.write(b"T")
        proc.stdin.flush()
        hwnd = recorder.await_value(windows.visible, "Initial GDI HWND missing")
        recorder.await_value(lambda: recorder.wait_running(proc) or recorder.idle_complete(log.read_text(encoding="utf-8")),
                             "Two empty worker inventories were required")
        witness = Witness(api, fixture, WindowLifetime, scope, recorder.await_value, token, log)
        def transition(action):
            witness("before", action, hwnd, proc.pid)
            issued = api.clock()
            if action == "close":
                current = recorder.await_value(lambda: recorder.wait_running(proc) or windows.visible(), "Missing GDI HWND")
                if current != hwnd:
                    raise ValueError("The idle control's root HWND changed")
                windows.close_window(current)
                recorder.await_value(lambda: recorder.wait_running(proc) or not windows.visible(), "GDI HWND stayed visible")
            else:
                proc.stdin.write(b"O")
                proc.stdin.flush()
                recorder.await_value(lambda: recorder.wait_running(proc) or windows.visible() == hwnd, "GDI HWND stayed hidden")
            requests.append(dict(action=action, issuedQpc=issued, responseQpc=api.clock(), hwnd=hwnd))
            witness("after", action, hwnd, proc.pid)

        # Use the original WPF runner's visible/hidden settling, sampling and two calibration reopens.
        tree = recorder.SubjectTree(api, scope, proc.pid, {proc.pid, worker})
        transition("close")
        transition("reopen")
        time.sleep(.75)
        for visible in (True, False):
            if not visible:
                transition("close")
            time.sleep(recorder.SETTLE_SECONDS)
            recorder.sample_idle(api, proc, tree, windows, visible)
        transition("reopen")
        time.sleep(.75)
        warmup = len(requests)
        for _ in range(recorder.SWITCHES):
            for action in ("close", "reopen"):
                transition(action)
                time.sleep(.1)
        if api.process_identity(handle) != identity or api.processes().get(worker, (None,))[0] != proc.pid:
            raise ValueError("The idle inventory worker changed during close and reopen")
        windows.pump()
        for action in ("show", "hide"):
            if sum(row["hwnd"] == hwnd and row["root"] and row["event"] == action for row in windows.events) < recorder.SWITCHES:
                raise ValueError("Missing visibility events for the retained GDI window")
        recorder.stop_subject(proc, True)
        if proc.returncode:
            raise RuntimeError("GDI process failed to drain its worker")
        observed = witness.finish(requests)
        metrics = {"idle_" + kind + "_p95_ms": recorder.p95([
            (row["responseQpc"] - row["issuedQpc"]) * 1000 / api.frequency for row in requests[warmup:] if row["action"] == kind
        ]) for kind in ("close", "reopen")}
        return dict(metrics=metrics, nativeWitness=observed, allRequests=requests, worker=worker,
                    workerCreation100ns=identity, warmupRequests=warmup, rootWindowEvents=windows.events)


def assess(target):
    if (os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise RuntimeError("Use the nonpublishing rewrite assessment")
    api, _, _, _, metadata = subjects(target)
    if os.getenv("GITHUB_SHA") != metadata["revision"]:
        raise ValueError("The checkout differs from this assessment run")
    budget, frozen, original, _ = reference(target, metadata)
    fixed_digest = sha(budget)
    measured = ROOT / "artifacts/rust/windows-warm-window" / target / "measured/result.json"
    retained = json.loads(measured.read_bytes())
    if (any(retained[key] != metadata[key] for key in ("target", "revision", "run", "attempt", "binary", "buildReceipt"))
            or retained["referenceBudgetSha256"] != fixed_digest or retained["diagnosticControl"]
            or retained["presentMode"] != "Mailbox" or len(retained["trials"]) != recorder.TRIALS):
        raise ValueError("A completed retained Mailbox reference on this host is required")
    if any(retained["comparison"][key]["maximum"] != frozen["maximums"][key]
           or retained["comparison"][key]["passed"] is None for key in NAMES):
        raise ValueError("Incomplete retained-window response measurements")
    out = ROOT / "artifacts/rust/windows-gdi-control" / target
    out.mkdir(parents=True, exist_ok=False)
    paths = [HERE / name for name in ("main.rs", "win32.rs", "assess.py", "witness.py", "test_witness.py")]
    paths += [QA / name for name in ("gui/src/windows_worker.rs", "windows-warm-window/inputs.py",
                                    "windows-warm-window/measure.py", "windows-warm-window/window_lifetime.py",
                                    "check-toolchain.py")]
    sources = {}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        checked_out = subprocess.check_output(["git", "cat-file", "--filters", metadata["revision"] + ":" + relative], cwd=ROOT)
        if checked_out != path.read_bytes():
            raise ValueError(f"Unrecorded fixture source: {relative}")
        sources[relative] = sha(path)
    record = dict(format="ifw-rw02-gdi-control-v1", status="running", target=target, revision=metadata["revision"],
                  run=metadata["run"], attempt=metadata["attempt"], referenceBudgetSha256=fixed_digest,
                  retainedResultSha256=sha(measured), renderer="Win32 640x400 32-bit DIB / BitBlt / GdiFlush",
                  sources=sources, trials=[])
    recorder.write(out / "result.json", record)
    try:
        machine = 0xaa64 if target.startswith("aarch64-") else 0x8664
        with ExitStack() as scope:
            area = scope.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
            entry = area / "gdi-control.exe"
            with (out / "native-compiler.log").open("wb") as log:
                subprocess.run([sys.executable, str(QA / "check-toolchain.py"), target], check=True, stdout=log,
                               stderr=subprocess.STDOUT)
                subprocess.run(["rustc", "--edition=2024", "-Dwarnings", "-Copt-level=3", "--target", target,
                                str(HERE / "main.rs"), "-o", str(entry)], check=True, stdout=log, stderr=subprocess.STDOUT)
            gui, files, inventory = recorder.build_subject(area, out, entry, target, recorder.pe_machine)
            if (not files or sha(entry) != inventory["gui"]
                    or any(inventory[key] != original["inventory"][key] for key in ("compiledEntry", "approvedBundle", "packages", "sources"))):
                raise ValueError("GDI control and WPF use different measured inventory inputs")
            for name in ("run.py", "native.py", "metrics.py"):
                if original["drivers"][name] != sha(QA / "windows-performance" / name):
                    raise ValueError("The original visibility or timing observer changed")
            for name, digest in original["sharedDrivers"].items():
                if sha(QA / name) != digest:
                    raise ValueError("The original shared observer changed")
            images = {gui: inventory["gui"], gui.with_name("ifw-performance-worker.exe"): inventory["worker"],
                      files: inventory["fileObserver"]}
            for folder in {path.parent for path in images}:
                scope.enter_context(pin_path(api, folder, True))
            for path, digest in images.items():
                scope.enter_context(pin_path(api, path, False))
                if sha(path) != digest or recorder.pe_machine(path) != machine:
                    raise ValueError("The pinned GDI control inputs must match their native executables")
            token, workload = recorder.create_fixture(area, scope, api)
            scope.enter_context(pin_path(api, area / "files", True))
            if any(original["workload"].get(key) != value for key, value in workload.items()):
                raise ValueError("Different synthetic inventory")
            fixture = recorder.load_windows_fixture()
            record.update(inventory=inventory, workload=workload, frequency=api.frequency)
            recorder.write(out / "result.json", record)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline:
                offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                offline.bind(("127.0.0.1", 0))
                endpoint = "http://127.0.0.1:" + str(offline.getsockname()[1])
                for number in range(1, recorder.TRIALS + 1):
                    name = f"rust-{number}"
                    row = dict(idle=idle(api, fixture, gui, area / name, endpoint, out, token, machine))
                    with ExitStack() as observation:
                        witness = Witness(api, fixture, WindowLifetime, observation, recorder.await_value, token,
                                          out / (name + "-scan.log"))
                        row["scan"] = recorder.measure_scan(api, fixture, "rust", gui, files, area / (name + "-scan"),
                                                            endpoint, None, out, recorder.await_value, recorder.stop_subject,
                                                            recorder.p95, token, visibility_witness=witness)
                        row["scan"]["nativeWitness"] = witness.finish(row["scan"]["allRequests"])
                        trace = (out / (name + "-scan-files.log")).read_text(encoding="ascii")
                        row["scan"]["visibleFrameWorkIndices"] = visible_frames_during_work(row["scan"], trace, api.frequency)
                    row["metrics"] = {**row["idle"]["metrics"], **row["scan"]["metrics"]}
                    record["trials"].append(row)
                    recorder.write(out / "result.json", record)
        if sha(budget) != fixed_digest or sha(measured) != record["retainedResultSha256"]:
            raise ValueError("Reference inputs changed during the GDI trial")
        record["comparison"] = {key: dict(wpf=frozen["reference"][key], maximum=frozen["maximums"][key],
                                         retained=retained["comparison"][key]["candidate"],
                                         gdi=median(row["metrics"][key] for row in record["trials"])) for key in NAMES}
        record["status"] = "observed"
    except Exception as error:
        record.update(status="incomplete", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        recorder.write(out / "result.json", record)
        recorder.write(out / "evidence-hashes.json", {p.name: sha(p) for p in sorted(out.iterdir())
                                                       if p.is_file() and p.name != "evidence-hashes.json"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    assess(parser.parse_args().target)
