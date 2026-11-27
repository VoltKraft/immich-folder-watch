"""Destroy only the owned GUI's WARP device and observe the same worker through reconstruction."""
import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
from hashlib import sha256
import os
from pathlib import Path
import runpy
import shutil
import socket
import sys
import uuid

from device_recovery import QA, WORKER, check, check_members, completed, read, recorder, sha, sources
from inputs import DX12_WAIT_OPTION, subjects
from native import checked, owned_directory, pin_new_marker, pin_path, start_owned_subject
from observe import capture_field
from window_lifetime import WindowLifetime
from gdi_case import native_root


def observe(cpu, api, out, record):
    fixture = recorder.load_windows_fixture()
    sys.path.append(str(QA / "windows-launcher"))
    launcher = runpy.run_path(str(QA / "windows-launcher/observe.py"))
    desktop = launcher["Desktop"]()
    console = launcher["system_console_path"](api.kernel)
    with ExitStack() as scope:
        area = scope.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
        token = uuid.uuid4().hex
        pin_new_marker(scope, api, area / "inventory.owner", token)
        stage = area / "subject"
        stage.mkdir()
        scope.enter_context(pin_path(api, stage, True))
        for name, expected in zip(("cpu.exe", WORKER), record["images"], strict=True):
            src, dest = cpu / name, stage / name
            scope.enter_context(pin_path(api, src, False))
            shutil.copyfile(src, dest)
            scope.enter_context(pin_path(api, dest, False))
            if sha(src) != expected or sha(dest) != expected or recorder.pe_machine(dest) != 0x8664:
                raise ValueError("The held executable differs from the original native CPU measurement")
        # The reviewed idle worker accepts this trial name and sibling empty inventory.
        trial = area / "rust-1"
        media = trial / "empty"
        media.mkdir(parents=True)
        offline = scope.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        offline.bind(("127.0.0.1", 0))
        endpoint = "http://127.0.0.1:" + str(offline.getsockname()[1])
        generated = recorder.environment(trial, endpoint, True, media, token)
        inventory_keys = {"IFW_QA_ISOLATED", "IFW_QA_BENCHMARK", "IFW_QA_INVENTORY_ROOT", "IFW_QA_INVENTORY_TOKEN",
                          "IFW_QA_INVENTORY_TRIAL", "IFW_QA_INVENTORY_PORT"}
        env = {key: value for key, value in generated.items() if not key.startswith("IFW_QA_") or key in inventory_keys}
        env.update(IFW_QA_GRAPHICS="recover")
        env[DX12_WAIT_OPTION] = "Wait"
        shell, attempts = fixture.select_powershell(trial, "accessibility", env)
        recorder.write(out / "hosts.json", attempts)
        if not shell:
            raise RuntimeError("The independent Windows UI Automation observer is unavailable")
        log = out / "subject.log"
        stream = scope.enter_context(log.open("xb"))
        proc = start_owned_subject(scope, api, stage / "cpu.exe", trial, env, stream, True, recorder.stop_subject)
        windows = fixture.Windows(proc.pid)
        scope.callback(windows.close)
        lifetime = WindowLifetime(proc.pid)
        scope.callback(lifetime.close)
        api.resume_owned_process(proc.pid)
        worker = recorder.owned_worker(api, proc, log, recorder.await_value)
        handle = api.open_job_member(proc.benchmark_job, worker)
        scope.callback(api.close, handle)
        handles = (proc._handle, handle)
        if any(api.machine(h) != (0x8664, 0x8664) for h in handles):
            raise ValueError("The running GUI and worker must both be native x64 images")
        record.update(pids=[proc.pid, worker], creation100ns=[api.process_identity(h) for h in handles],
                      fields=[], workers=[], frequency=api.frequency)
        identify = native_root()

        def text():
            # Ignore a possibly incomplete last write while the worker is logging.
            data = log.read_bytes()
            return data[:data.rfind(b"\n") + 1]

        def live():
            recorder.wait_running(proc)
            windows.pump()
            job = {}
            try:
                launcher["primary_job_members"](api, desktop, proc.benchmark_job, proc.pid, worker, stage / "cpu.exe",
                                                console, job)
                check_members(job, record["pids"], record["creation100ns"])
            except (OSError, ValueError) as error:
                record["failedJobObservation"] = job
                raise ValueError(f"Recovery job membership: {error}") from error
            return job

        def window(generation, previous):
            live()
            hwnd = windows.visible(retiring=previous)
            if (hwnd and hwnd != previous and f"GRAPHICS_READY generation={generation}".encode() in text().splitlines()
                    and any(e["hwnd"] == hwnd and e["event"] == "show" for e in windows.events)):
                return hwnd

        def snapshot():
            job = live()
            raw = text()
            return dict(qpc=api.clock(), logBytes=len(raw), logSha256=sha256(raw).hexdigest(),
                        passes=completed(raw.decode()), job=job)

        def command(value):
            proc.stdin.write(value)
            proc.stdin.flush()

        live()
        command(b"T")
        previous = None
        for number, phase in enumerate(("before", "after"), 1):
            hwnd = recorder.await_value(lambda: window(number, previous), phase + " visible WARP generation", timeout=40)
            root = identify(hwnd, proc.pid)
            started = api.clock()
            digest = capture_field(shell, trial, env, out, hwnd, proc.pid, log, phase)
            ended = api.clock()
            live()
            if windows.visible() != hwnd or identify(hwnd, proc.pid) != root:
                raise ValueError("The visible editor or worker changed during the field observation")
            record["fields"].append(dict(root=root, field=digest, qpc=[started, ended]))
            recorder.await_value(lambda: live() and completed(text().decode()) >= 2, "Initial empty inventories", timeout=20)
            record["workers"].append(snapshot())
            if phase == "before":
                record["destroyQpc"] = api.clock()
                command(b"G")
            previous = hwnd
        last = record["workers"][-1]["passes"]
        recorder.await_value(lambda: live() and completed(text().decode()) > last, "Next original worker inventory", timeout=20)
        record["workers"].append(snapshot())
        record["quitQpc"] = api.clock()
        record["termination"] = recorder.stop_subject(proc, True, drain_log=log)
        if not api.wait_job_empty(proc.benchmark_job, 4):
            raise ValueError("Normal Quit left a running member in the GUI job")
        code = w.DWORD()
        checked(api.exit_code(handle, c.byref(code)))
        record.update(workerExit=code.value, emptyJob=True)

        def destroyed():
            windows.pump()
            return any(hwnd == previous and action == "destroy" for hwnd, action, _ in lifetime.events)

        recorder.await_value(destroyed, "Replacement HWND destruction", timeout=5)
        record.update(lifetimes=list(lifetime.events), windowEvents=windows.events, subjectLog=sha(log))
    record["profileRemoved"] = not os.path.lexists(area)


def main(cpu):
    api, _, _, base, host = subjects("x86_64-pc-windows-msvc")
    if cpu != base / "cpu-paint":
        raise ValueError("Use the CPU measurement folder on the native x64 Windows runner")
    out = cpu / "recovery"
    out.mkdir()
    record = {k: host[k] for k in ("revision", "run", "attempt", "target")}
    try:
        timing = read(cpu / "result.json")
        worker = timing["inputs"]["inventory"]
        if (any(timing[k] != value for k, value in record.items()) or sha(cpu / "cpu.exe") != timing["binary"]
                or timing["binary"] != worker["gui"] or sha(cpu / WORKER) != worker["worker"]
                or sha(cpu / "cpu-build.json") != timing["cpuBuild"]):
            raise ValueError("The recovery inputs differ from the timed CPU build on this host")
        record.update(sources=sources(record["revision"]), measurement=sha(cpu / "result.json"),
                      images=[timing["binary"], worker["worker"]])
        observe(cpu, api, out, record)
        record["verified"] = check(out, record)
        record["status"] = "passed"
    except Exception as error:
        record.update(status="incomplete", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        recorder.write(out / "result.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu_paint", type=Path)
    main(parser.parse_args().cpu_paint.resolve())
