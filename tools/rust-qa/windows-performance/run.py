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
import tempfile
import time
import uuid

from build import HERE, ROOT, build, sha, write
from metrics import IDLE_SECONDS, SETTLE_SECONDS, SWITCHES, TRIALS, budgets, comparison, p95, summarize
from native import Win32, checked, hosted, sid, wpf_profile


def await_value(get, label, timeout=35, delay=.002):
    end = time.monotonic() + timeout
    while True:
        if value := get():
            return value
        if time.monotonic() >= end:
            raise TimeoutError(label)
        time.sleep(delay)


def trace_start(stack, observer, pid, area):
    log = area / "present.log"
    if observer is None:
        log.write_text("The Windows SDK observer did not compile; see observer-build.log.\n")
        return lambda: None, log
    stream = stack.enter_context(log.open("wb", buffering=0))
    helper = subprocess.Popen([observer, str(pid), area / "subject.etl", "IFW-RW02-" + uuid.uuid4().hex],
                              stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT, cwd=area)
    def finish():
        if helper.poll() is None:
            helper.stdin.close()
            helper.wait(timeout=30)
        elif not helper.stdin.closed:
            helper.stdin.close()
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


def sample_idle(api, proc, handle, windows, visible):
    memory = []
    start = api.clock()
    cpu = api.usage(handle)[0]
    while True:
        wait_running(proc)
        if bool(windows.visible()) != visible:
            raise ValueError("The measured window changed visibility during the idle interval")
        now_cpu, working = api.usage(handle)
        memory.append(working)
        now = api.clock()
        if now - start >= IDLE_SECONDS * api.frequency:
            break
        time.sleep(.25)
    seconds = (now - start) / api.frequency
    return [start, now], {"cpu_one_core_pct": (now_cpu - cpu) * 100 / seconds,
                          "working_set_mib": median(memory), "samples": memory, "seconds": seconds}


def load_windows_fixture():
    sys.path.insert(0, str(HERE.parent))
    spec = importlib.util.spec_from_file_location("native_gui_observer", HERE.parent / "observe-windows-gui.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stop_subject(proc, rust):
    if proc.poll() is None:
        if rust:
            try:
                proc.stdin.write(b"Q")
                proc.stdin.flush()
                proc.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        else:
            # The shipping WPF host has no quit CLI. All measurements precede terminating this owned process.
            proc.terminate()
    proc.wait(timeout=15)
    if proc.stdin:
        proc.stdin.close()


def trial(api, windows_fixture, subject, exe, observer, area, endpoint, user_sid, expected_machine, phase_log):
    rust = subject == "rust"
    area.mkdir()
    media = area / "empty"
    media.mkdir()
    env = {**os.environ, "TEMP": str(area), "TMP": str(area), "IFW_QA_ISOLATED": "1", "WGPU_DX12_COMPILER": "Fxc",
           "HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "ALL_PROXY": endpoint, "NO_PROXY": "localhost,127.0.0.1,::1",
           "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    env.pop("IFW_QA_GRAPHICS", None)
    env.pop("IFW_QA_BENCHMARK", None)
    if rust:
        for key in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
            folder = area / key
            folder.mkdir()
            env[key] = str(folder)
    result = {"metrics": {}, "idleSamples": {}, "controls": {}}
    with ExitStack() as stack:
        if not rust:
            api.ensure_no_primary(user_sid)
        profile = None if rust else stack.enter_context(wpf_profile(media, endpoint))
        log = stack.enter_context(phase_log.open("wb"))
        windows_fixture.TITLE = "Desktop input probe" if rust else "Immich Folder Watch"
        start = api.clock()
        proc = subprocess.Popen([exe], cwd=area, env=env, stdin=subprocess.PIPE if rust else subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
        stack.callback(stop_subject, proc, rust)
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
        visible(True)
        result["metrics"]["startup_ms"] = (api.clock() - start) * 1000 / api.frequency
        handle = checked(api.open(0x0410, False, proc.pid))
        stack.callback(api.close, handle)
        if api.machine(handle) != (expected_machine, expected_machine):
            raise ValueError("Subject process is emulated or belongs to a different native target")
        if rust:
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
        finish, trace = trace_start(stack, observer, proc.pid, area)

        def reopen():
            if rust:
                proc.stdin.write(b"O")
                proc.stdin.flush()
            else:
                api.activate_wpf(user_sid, proc.pid)
            return visible(True)

        def close():
            windows.close_window(visible(True))
            visible(False)

        def calibrate():
            tick = api.clock()
            reopen()
            time.sleep(.75)
            return [tick, api.clock()]

        close()
        controls = [calibrate()]
        spans = {}
        for name in ("visible", "hidden"):
            if name == "hidden":
                close()
            time.sleep(SETTLE_SECONDS)
            spans[name], samples = sample_idle(api, proc, handle, windows, name == "visible")
            result["idleSamples"][name] = samples
            for key in ("cpu_one_core_pct", "working_set_mib"):
                result["metrics"][name + "_" + key] = samples[key]
        controls.append(calibrate())
        close_ms, open_ms = [], []
        for _ in range(SWITCHES):
            tick = api.clock()
            close()
            close_ms.append((api.clock() - tick) * 1000 / api.frequency)
            time.sleep(.1)
            tick = api.clock()
            reopen()
            open_ms.append((api.clock() - tick) * 1000 / api.frequency)
            time.sleep(.1)
        result["idleVisibilityMs"] = {"close": close_ms, "reopen": open_ms}
        result["metrics"].update(idle_close_p95_ms=p95(close_ms), idle_reopen_p95_ms=p95(open_ms))
        finish()
        present, result["presentation"] = present_counts(trace.read_text(errors="replace"), spans, controls, api.frequency)
        result["metrics"].update(present)
        result["controls"]["windowEvents"] = {name: sum(e["event"] == name and e["root"] for e in windows.events)
                                               for name in ("show", "hide")}
        result["controls"]["successfulVisibilityCycles"] = SWITCHES
        stop_subject(proc, rust)
        result["termination"] = {"method": "control-Q" if rust else "owned process terminated after sampling",
                                 "exitCode": proc.returncode}
        if rust and (proc.returncode or "DRAINED passes=" not in phase_log.read_text(errors="replace")):
            raise RuntimeError("The native Rust GUI did not drain")
    return result


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
        with tempfile.TemporaryDirectory(prefix="ifw-rw02-", dir=os.environ["RUNNER_TEMP"]) as temp:
            area = Path(temp)
            wpf, rust, observer, facts = build(area, output, args.target)
            write(output / "inputs.json", facts)
            api = Win32()
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
                                            user_sid, expected, output / (name + ".log"))
                        report["trials"][subject].append(observation)
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
        report["outstanding"] = ["Candidate inventory ownership and UI latency during a real Windows scan",
                                 "Physical display scanout and on-screen response during a scan"]
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
