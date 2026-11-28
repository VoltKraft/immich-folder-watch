"""Compare the shipping WPF and canonical Rust GUI on one disposable native Windows runner."""
import argparse
from contextlib import ExitStack
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
from statistics import median
import subprocess
import sys
import time
import uuid

from build import HERE, ROOT, build, pe_machine, sha, write
from metrics import IDLE_SECONDS, SETTLE_SECONDS, SWITCHES, TRIALS, budgets, comparison, p95, summarize
from native import (CleanupUnconfirmed, Win32, bind, checked, finish_owned_trace, hosted, observe_wpf_tray, owned_directory,
                    pin_path, sid, start_owned_subject, wpf_profile)

sys.path.insert(0, str(HERE.parent / "windows-inventory"))
from scan import SubjectTree, create_fixture, environment, measure as measure_scan, owned_worker
from subject import build_subject


def await_value(get, label, timeout=35, delay=.002):
    end = time.monotonic() + timeout
    while True:
        if value := get():
            return value
        if time.monotonic() >= end:
            raise TimeoutError(label)
        time.sleep(delay)


def trace_start(stack, observer, pid, area, *, timed_log=None):
    log = timed_log if timed_log is not None else area / "present.log"
    if observer is None:
        log.write_text("The Windows SDK observer did not compile; see observer-build.log.\n")
        return lambda: None, log
    stream = stack.enter_context(log.open("wb", buffering=0))
    etl, name = area / "subject.etl", "IFW-RW02-" + uuid.uuid4().hex
    command = [observer, str(pid), etl, name]
    if timed_log is not None:
        command.append("--timings")
    helper = subprocess.Popen(command,
                              stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT, cwd=area)
    finished = False
    def finish():
        nonlocal finished
        if not finished:
            finish_owned_trace(helper, observer, area, etl, name, 30)
            finished = True
    stack.callback(finish)
    await_value(lambda: log.read_bytes().startswith(b"READY") or helper.poll() is not None,
                "Windows presentation observer did not start", timeout=20, delay=.02)
    return finish, log


def present_counts(text, spans, controls, frequency):
    lines = text.splitlines()
    if not lines or lines[-1] != "COMPLETE":
        return {}, {"reason": "The filtered ETW session was unavailable or lost/failed to decode events",
                    "diagnostics": [s for s in lines if not s.startswith("P ")][:8]}
    events = [(int(p[2]), p[1]) for line in lines if line.startswith("P ") and len(p := line.split()) == 3]
    count = lambda span: sum(span[0] <= ts < span[1] for ts, _ in events)
    control_counts = [count(span) for span in controls]
    coverage = {"reopenControls": control_counts, "acceptedPresents": len(events),
                "providers": sorted({provider for _, provider in events})}
    if not control_counts or not all(control_counts):
        return {}, dict(coverage, reason="A deliberate reopen produced no successful target present")
    measured = {}
    for name, span in spans.items():
        measured[name + "_present_per_second"] = count(span) * frequency / (span[1] - span[0])
    return measured, dict(coverage, idleCounts={name: count(span) for name, span in spans.items()})


def wait_running(proc):
    if (status := proc.poll()) is not None:
        raise RuntimeError(f"The measured subject exited unexpectedly with {status}")


def sample_idle(api, proc, tree, windows, visible):
    memory = []
    first_sample = len(tree.samples)
    cpu = tree.usage()[0]
    start = api.clock()
    while True:
        wait_running(proc)
        if bool(windows.visible()) != visible:
            raise ValueError("The measured window changed visibility during the idle interval")
        now_cpu, working = tree.usage()
        memory.append(working)
        now = api.clock()
        if now - start >= IDLE_SECONDS * api.frequency:
            break
        time.sleep(.25)
    seconds = (now - start) / api.frequency
    return [start, now], {"cpu_one_core_pct": (now_cpu - cpu) * 100 / seconds,
                          "working_set_mib": median(memory), "samples": memory, "seconds": seconds,
                          "jobSamples": tree.samples[first_sample:]}


def load_windows_fixture():
    sys.path.insert(0, str(HERE.parent))
    spec = importlib.util.spec_from_file_location("native_gui_observer", HERE.parent / "observe-windows-gui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stop_subject(proc, rust, *, drain_log=None):
    """Reap the owned process and retain how it exited when qualifying a timed trial."""
    method = "already exited"
    if proc.poll() is None:
        if rust:
            try:
                method = "control-Q"
                proc.stdin.write(b"Q")
                proc.stdin.flush()
                proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                method = "control-Q timed out, forced cleanup"
                proc.kill()
            except OSError as exc:
                method = f"control-Q failed ({exc}), forced cleanup"
                proc.kill()
        else:
            # The shipping WPF host has no quit CLI. All measurements precede terminating this owned process.
            method = "owned process terminated after sampling"
            proc.terminate()
    code = proc.wait(timeout=15)
    if proc.stdin:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            # Flushing the already exited child's pipe again cannot change its exit status.
            pass
    if rust and drain_log is not None:
        drained = any(line.startswith("DRAINED passes=") for line in
                      drain_log.read_text(encoding="utf-8", errors="replace").splitlines())
        if method != "control-Q" or code or not drained:
            raise RuntimeError(f"{drain_log.name}: {method}, native exit 0x{code & 0xffffffff:08X}, "
                               f"DRAINED marker {drained}")
    return {"method": method, "exitCode": code}


def idle_complete(text):
    expected = ["INVENTORY_COMPLETE files=0 changed=0 pass=0", "INVENTORY_COMPLETE files=0 changed=0 pass=1"]
    rows = [line.rstrip("\r\n") for line in text.splitlines(keepends=True)
            if line.startswith("INVENTORY_COMPLETE ") and line.endswith("\n")]
    if rows[:2] != expected[:len(rows[:2])]:
        raise ValueError("The first two idle inventory reports must be the complete, consecutive passes 0 and 1")
    return len(rows) >= 2


def wpf_second_launch(api, windows, primary, exe, area, env, log, report):
    """Observe one ordinary launch after timing, using the same pinned WPF executable and profile."""
    foreground = bind(c.WinDLL("user32"), "GetForegroundWindow", c.c_void_p)
    uptime = bind(api.kernel, "GetTickCount64", c.c_uint64)
    hwnd = windows.visible()
    if not hwnd or primary.poll() is not None:
        raise ValueError("The WPF reference needs its original live window")
    report.update(primaryPid=primary.pid, hwnd=hwnd, initiallyForeground=foreground() == hwnd)
    windows.close_window(hwnd)
    await_value(lambda: wait_running(primary) or not windows.visible(), "The original WPF window did not hide")
    with ExitStack() as child:
        secondary = start_owned_subject(child, api, exe, area, env, log, False, stop_subject)
        report.update(secondaryPid=secondary.pid, secondaryArguments=[])
        wait_running(primary)
        if windows.visible() is not None or secondary.poll() is not None:
            raise ValueError("The WPF primary must remain hidden until its suspended secondary starts")
        cursor = len(windows.events)
        report["beforeResumeMs"] = uptime()
        api.resume_owned_process(secondary.pid)
        released = report["resumeReturnedMs"] = uptime()
        report["secondaryExit"] = secondary.wait(timeout=10)
        if report["secondaryExit"] != 0:
            raise ValueError("The ordinary WPF secondary did not exit successfully")
        reopened = await_value(lambda: wait_running(primary) or windows.visible(), "WPF did not reopen", timeout=5)
        report.update(reopenedHwnd=reopened, sameWindow=reopened == hwnd)
        if reopened != hwnd:
            raise ValueError("The ordinary WPF launch showed a different window")
        start = time.monotonic()
        samples = 0
        while True:
            wait_running(primary)
            if windows.visible() != hwnd:
                raise ValueError("The original WPF window did not remain visible")
            samples += 1
            focused = foreground() == hwnd
            if focused or time.monotonic() - start >= 2:
                report.update(foregroundObserved=focused, samples=samples,
                              elapsedMs=round((time.monotonic() - start) * 1000))
                break
            time.sleep(.05)
        windows.pump()
        observed = report["observationMs"] = uptime()
        shows = report["rootShowEvents"] = [e for e in windows.events[cursor:]
                                            if e["root"] and e["hwnd"] == hwnd and e["event"] == "show"]
        # WinEvent uses a 32-bit uptime. An equal tick cannot order the show and resume.
        elapsed = observed - released
        ordered = (len(shows) == 1 and 0 <= elapsed <= 35_000
                   and 0 < (shows[0]["winEventTimeMs"] - released) % (1 << 32) <= elapsed)
    wait_running(primary)
    report.update(secondaryJobDrained=True, status="observed" if ordered else "show-order-inconclusive")


def trial(api, windows_fixture, subject, exe, observer, area, endpoint, user_sid, expected_machine, phase_log, owner_token,
          *, compare_wpf_launch=False, frame_observer=None):
    rust = subject == "rust"
    area.mkdir()
    media = area / "empty"
    media.mkdir()
    env = environment(area, endpoint, rust, media, owner_token)
    result = {"metrics": {}, "idleSamples": {}, "controls": {}}
    with ExitStack() as stack:
        if not rust:
            api.ensure_no_primary(user_sid)
        profile = None if rust else stack.enter_context(wpf_profile(media, endpoint))
        log = stack.enter_context(phase_log.open("wb"))
        windows_fixture.TITLE = "Desktop input probe" if rust else "Immich Folder Watch"
        proc = start_owned_subject(stack, api, exe, area, env, log, rust, stop_subject)
        api.resume_owned_process(proc.pid)
        if rust:
            proc.stdin.write(b"T")
            proc.stdin.flush()
        windows = windows_fixture.Windows(proc.pid)
        stack.callback(windows.close)
        def visible(state):
            def poll():
                wait_running(proc)
                window = windows.visible()
                return window if state else not window
            return await_value(poll, f"{subject} did not become {'visible' if state else 'hidden'}")
        initial_window = visible(True)
        first_visible_qpc = api.clock()
        result["metrics"]["startup_ms"] = (first_visible_qpc - proc.benchmark_start_qpc) * 1000 / api.frequency
        if frame_observer:
            frame_window = frame_observer(initial_window, proc.pid)
            transitions = []
        handle = int(proc._handle)  # Popen owns the GUI's original process handle until teardown.
        api.verify_job_member(proc.benchmark_job, proc.pid, handle)
        if api.machine(handle) != (expected_machine, expected_machine):
            raise ValueError("Subject process is emulated or belongs to a different native target")
        required_handles = {proc.pid: handle}
        if rust:
            child = owned_worker(api, proc, phase_log, await_value)
            child_handle = api.open_job_member(proc.benchmark_job, child)
            stack.callback(api.close, child_handle)
            required_handles[child] = child_handle
            if api.machine(child_handle) != (expected_machine, expected_machine):
                raise ValueError("The comparison worker is not native to this runner")
            await_value(lambda: wait_running(proc) or idle_complete(phase_log.read_text(errors="replace")),
                        "The candidate did not finish both idle inventories")
            await_value(lambda: wait_running(proc) or "ADAPTER Dx12 " in phase_log.read_text(errors="replace"),
                        "The candidate did not report its native DX12 adapter")
        else:
            def engine_ready():
                wait_running(proc)
                logs = "".join(path.read_text(encoding="utf-8", errors="replace") for path in (profile / "engine-logs").glob("*.log"))
                return ((profile / "sync-state.db").is_file() and "Folder watcher started with 1 source(s)." in logs
                        and logs.count("Persistent reconciliation for uploadNew queued 0 changed file(s)") >= 2)
            await_value(engine_ready, "The real WPF host did not start its synthetic watcher", delay=.05)
            result["controls"]["realWpfWatcher"] = True
        if frame_observer:
            finish, trace = trace_start(stack, observer, proc.pid, area, timed_log=area / "present.log")
        else:
            finish, trace = trace_start(stack, observer, proc.pid, area)

        def reopen():
            if rust:
                proc.stdin.write(b"O")
                proc.stdin.flush()
            else:
                api.activate_wpf(user_sid, proc.pid)
            window = visible(True)
            if frame_observer and window != initial_window:
                raise ValueError("The retained frame controls reopened a different HWND")
            return window

        def close():
            windows.close_window(visible(True))
            visible(False)

        def transition(action):
            issued = api.clock()
            (close if action == "close" else reopen)()
            response = api.clock()
            if frame_observer:
                transitions.append(dict(action=action, issuedQpc=issued, responseQpc=response, hwnd=initial_window))
            return issued, response

        def calibrate():
            tick, _ = transition("reopen")
            time.sleep(.75)
            return [tick, api.clock()]

        transition("close")
        controls = [calibrate()]
        spans = {}
        tree = SubjectTree(api, stack, proc.benchmark_job, required_handles)
        for name in ("visible", "hidden"):
            if name == "hidden":
                transition("close")
            time.sleep(SETTLE_SECONDS)
            spans[name], samples = sample_idle(api, proc, tree, windows, name == "visible")
            result["idleSamples"][name] = samples
            for key in ("cpu_one_core_pct", "working_set_mib"):
                result["metrics"][name + "_" + key] = samples[key]
        controls.append(calibrate())
        close_ms, open_ms = [], []
        for _ in range(SWITCHES):
            tick, end = transition("close")
            close_ms.append((end - tick) * 1000 / api.frequency)
            time.sleep(.1)
            tick, end = transition("reopen")
            open_ms.append((end - tick) * 1000 / api.frequency)
            time.sleep(.1)
        result["idleVisibilityMs"] = {"close": close_ms, "reopen": open_ms}
        result["metrics"].update(idle_close_p95_ms=p95(close_ms), idle_reopen_p95_ms=p95(open_ms))
        finish()
        if frame_observer is None:
            present, result["presentation"] = present_counts(trace.read_text(errors="replace"), spans, controls, api.frequency)
            result["metrics"].update(present)
        result["controls"]["windowEvents"] = {name: sum(e["event"] == name and e["root"] for e in windows.events)
                                               for name in ("show", "hide")}
        result["controls"]["successfulVisibilityCycles"] = SWITCHES
        result["controls"]["wholeProcessTree"] = tree.records
        if frame_observer:
            if frame_observer(visible(True), proc.pid) != frame_window:
                raise ValueError("The original native client changed during the frame observations")
            result["frameWindows"] = dict(root=frame_window, guiCreation100ns=api.process_identity(handle),
                                          startupQpc=[proc.benchmark_start_qpc, first_visible_qpc], frequency=api.frequency,
                                          spans=spans, controls=controls, requests=transitions)
        if not rust:
            try:
                result["controls"]["shippingTrayLookup"] = observe_wpf_tray(api, proc, handle)
            except (OSError, ValueError) as exc:
                result["controls"]["shippingTrayLookup"] = dict(status="unavailable", reason=str(exc))
            if compare_wpf_launch:
                reference = result["controls"]["shippingSecondLaunch"] = {"status": "unavailable"}
                try:
                    wpf_second_launch(api, windows, proc, exe, area, env, log, reference)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
                    reference["error"] = f"{type(exc).__name__}: {exc}"
                    if CleanupUnconfirmed.in_chain(exc):
                        raise
                finally:
                    write(phase_log.with_suffix(".second-launch.json"), reference)
        result["termination"] = stop_subject(proc, rust, drain_log=phase_log)
    return result


def pin_images(stack, api, area, wpf, gui, observer, file_observer, facts):
    worker = gui.with_name("ifw-performance-worker.exe")
    images = {gui: facts["guiBinarySha256"], worker: facts["inventory"]["worker"], wpf: facts["wpfOutput"][wpf.name]}
    if observer:
        images[observer] = facts["observerSha256"]
    if file_observer:
        images[file_observer] = facts["inventory"]["fileObserver"]
    objects = {area, *(p.parent for p in images)}
    records = {}
    for path in [*sorted(objects), *images]:
        _, identity = stack.enter_context(pin_path(api, path, path in objects))
        records[path.relative_to(area).as_posix()] = dict(volumeSerial=identity[0], fileIndex=identity[1])
        if path in images and sha(path) != images[path]:
            raise ValueError("A pinned executable differs from its build receipt")
    return records


def run(args):
    if not hosted():
        raise ValueError("Run the paired executable only on a disposable GitHub-hosted native Windows runner")
    output = args.output.resolve()
    base = (ROOT / "artifacts/rust/windows-performance").resolve()
    if output.parent != base or output.name != "native-" + args.target:
        raise ValueError("Select the target-specific Windows performance evidence directory")
    output.mkdir(exist_ok=False, parents=True)
    report = {"target": args.target, "status": "running", "trials": {"wpf": [], "rust": []},
              "host": {"os": platform.platform(), "cores": os.cpu_count(), "runnerImage": os.getenv("ImageVersion"),
                       "run": os.getenv("GITHUB_RUN_ID"), "attempt": os.getenv("GITHUB_RUN_ATTEMPT")}}
    write(output / "result.json", report)
    try:
        api = Win32()
        with ExitStack() as resources:
            area = resources.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
            wpf, rust, observer, facts = build(area, output, args.target)
            rust, file_observer, facts["inventory"] = build_subject(area, output, rust, args.target, pe_machine)
            pinned = pin_images(resources, api, area, wpf, rust, observer, file_observer, facts)
            owner_token, facts["workload"] = create_fixture(area, resources, api)
            for child in ("inventory.owner", "files"):
                _, identity = resources.enter_context(pin_path(api, area / child, child == "files"))
                pinned[child] = dict(volumeSerial=identity[0], fileIndex=identity[1])
            facts["workload"]["pinnedObjects"] = pinned
            facts["drivers"]["etw-owned.h"] = sha(HERE / "etw-owned.h")
            write(output / "inputs.json", facts)
            user32 = c.WinDLL("user32")
            report["host"].update(qpcFrequency=api.frequency, computerIdSha256=hashlib.sha256(
                os.environ["COMPUTERNAME"].encode()).hexdigest(), observerMachine=api.machine(-1),
                screenPixels=[user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)], systemDpi=user32.GetDpiForSystem())
            windows_fixture, user_sid = load_windows_fixture(), sid()
            expected = 0xaa64 if args.target.startswith("aarch64-") else 0x8664
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline:
                offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                offline.bind(("127.0.0.1", 0))  # No listener can accept an update, transfer or reconnect.
                endpoint = "http://127.0.0.1:" + str(offline.getsockname()[1])
                for subject, exe in (("wpf", wpf), ("rust", rust)):
                    for n in range(TRIALS):
                        print(f"Measuring native {subject} trial {n + 1} of {TRIALS}", flush=True)
                        name = f"{subject}-{n + 1}"
                        observation = trial(api, windows_fixture, subject, exe, observer, area / name, endpoint,
                                            user_sid, expected, output / (name + ".log"), owner_token,
                                            compare_wpf_launch=subject == "wpf" and n == TRIALS - 1)
                        report["trials"][subject].append(observation)
                        write(output / "result.json", report)
                        if file_observer is None:
                            observation["scan"] = {"error": "File ETW observer build failed; see file-observer-build.log"}
                        else:
                            try:
                                observation["scan"] = measure_scan(api, windows_fixture, subject, exe, file_observer,
                                                                   area / (name + "-scan"), endpoint, user_sid, output,
                                                                   await_value, stop_subject, p95, owner_token)
                                observation["metrics"].update(observation["scan"]["metrics"])
                            except CleanupUnconfirmed:
                                raise
                            except (OSError, TimeoutError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                                if CleanupUnconfirmed.in_chain(exc):
                                    raise CleanupUnconfirmed("A scan resource could not be released safely") from exc
                                observation["scan"] = {"error": f"{type(exc).__name__}: {exc}"}
                                print(f"{name} scan observation incomplete: {type(exc).__name__}: {exc}", flush=True)
                        write(output / "result.json", report)
                    summary = summarize(report["trials"][subject])
                    if subject == "wpf":
                        fixed = {"reference": summary, "maximums": budgets(summary), "trials": TRIALS,
                                 "idleSeconds": IDLE_SECONDS, "settleSeconds": SETTLE_SECONDS,
                                 "sourceInputsSha256": sha(output / "inputs.json")}
                        write(output / "reference-budget.json", fixed)
                        report["budgetSha256"] = sha(output / "reference-budget.json")
                    else:
                        if sha(output / "reference-budget.json") != report["budgetSha256"]:
                            raise ValueError("The baseline budget changed during the candidate trials")
                        fixed = json.loads((output / "reference-budget.json").read_text())
                        report["comparison"] = comparison(fixed["maximums"], summary)
        rows = list(report["comparison"].values())
        report["status"] = ("over-budget" if any(r["passed"] is False for r in rows) else
                            "partial" if any(r["passed"] is None for r in rows) else "measured-metrics-passed")
        report["outstanding"] = [name for name, row in report["comparison"].items() if row["passed"] is None]
        report["outstanding"].append("Physical display scanout during a scan")
        return 0 if report["status"] == "measured-metrics-passed" else 1
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write(output / "result.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc"))
    parser.add_argument("--output", type=Path, required=True)
    sys.exit(run(parser.parse_args()))
