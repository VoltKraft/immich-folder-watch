"""Capture a CPU-to-DXGI handoff on one native, disposable Windows x64 worker."""
import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import uuid

import fixture_build as build
from evidence import check, drawings
import pixels
from inputs import DX12_WAIT_OPTION, recorder, subjects
from native import bind, checked, owned_directory, pin_path, start_owned_subject
from window_lifetime import WindowLifetime
from gdi_case import native_root


def observe(api, binary, out, record):
    fixture = recorder.load_windows_fixture()
    with ExitStack() as scope:
        area = scope.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
        env = {k: v for k, v in os.environ.items() if not k.startswith("IFW_QA_")}
        env.update(IFW_QA_ISOLATED="1", TEMP=str(area), TMP=str(area), WGPU_DX12_COMPILER="Fxc")
        env[DX12_WAIT_OPTION] = "Wait"
        for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME"):
            (area / k).mkdir()
            env[k] = str(area / k)
        present = out / "present.exe"
        cpp = build.prepare.QA / "windows-performance/present.cpp"
        with (out / "present-build.log").open("xb") as log:
            subprocess.run(["cl.exe", "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/utf-8", "/DUNICODE",
                            "/D_UNICODE", str(cpp), "/link", "/OUT:" + str(present), "advapi32.lib", "tdh.lib"],
                           cwd=area, stdout=log, stderr=subprocess.STDOUT, check=True)
        scope.enter_context(pin_path(api, out, True))
        for path in (present, binary):
            scope.enter_context(pin_path(api, path, False))
            if recorder.pe_machine(path) != 0x8664:
                raise ValueError("The subject and observer must be native x64")
        record["presentObserver"] = build.sha(present)
        if build.sha(binary) != record["build"]["binary"]:
            raise ValueError("The held example is not the just-built PE")
        set_dpi = bind(c.WinDLL("user32", use_last_error=True), "SetThreadDpiAwarenessContext", w.HANDLE, w.HANDLE)
        old = checked(set_dpi(c.c_void_p(-4)))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        scope.callback(lambda: checked(set_dpi(old)))
        log = out / "subject.log"
        stream = scope.enter_context(log.open("xb"))
        proc = start_owned_subject(scope, api, binary, area, env, stream, True, recorder.stop_subject)
        identity = api.process_identity(proc._handle)
        if api.machine(proc._handle) != (0x8664, 0x8664):
            raise ValueError("The running example does not have the native x64 architecture")
        windows = fixture.Windows(proc.pid)
        scope.callback(windows.close)
        lifetime = WindowLifetime(proc.pid)
        scope.callback(lifetime.close)
        start = api.clock()
        finish, trace = recorder.trace_start(scope, present, proc.pid, area, timed_log=out / "presents.log")
        if not trace.read_bytes().startswith(b"READY"):
            raise ValueError("ETW did not admit the original GUI PID")
        record.update(frequency=api.frequency, creation100ns=identity, phases=[])
        api.resume_owned_process(proc.pid)
        identify = native_root()
        root = None
        for phase, cmd in enumerate((b"T", b"1", b"2")):
            issued = api.clock()
            proc.stdin.write(cmd)
            proc.stdin.flush()

            def capture():
                nonlocal root
                recorder.wait_running(proc)
                hwnd = windows.visible()
                if root and (hwnd != root["hwnd"] or identify(hwnd, proc.pid) != root):
                    raise ValueError("The original visible HWND or client changed")
                if not hwnd:
                    return None
                current = identify(hwnd, proc.pid)
                complete_lines = log.read_bytes().rpartition(b"\n")[0]
                known = list(drawings(complete_lines.decode("utf-8")))
                if not known or known[-1][0] != phase:
                    return None
                data, metadata = pixels.sample(api, windows, current, known[-1][2])
                (out / f"phase-{phase}.ppm").write_bytes(data)
                if not pixels.colors(data, phase):
                    return None
                # Start the retained sample only after a complete independent read saw the new colors.
                data, metadata = pixels.sample(api, windows, current, known[-1][2])
                (out / f"phase-{phase}.ppm").write_bytes(data)
                if not pixels.colors(data, phase) or identify(hwnd, proc.pid) != current:
                    return None
                root = current
                if api.process_identity(proc._handle) != identity or api.job_pids(proc.benchmark_job) != {proc.pid}:
                    raise ValueError("The original process/job identity changed")
                return dict(phase=phase, issuedQpc=issued, root=root.copy(), creation100ns=identity,
                            jobPids=[proc.pid], pixels=build.sha(out / f"phase-{phase}.ppm"), **metadata)

            row = recorder.await_value(capture, f"Original visible texture phase {phase}", timeout=40, delay=.025)
            record["phases"].append(row)
        record["root"] = root
        finish()
        record["traceBoundsQpc"] = [start, api.clock()]
        recorder.wait_running(proc)
        if windows.visible() != root["hwnd"] or identify(root["hwnd"], proc.pid) != root:
            raise ValueError("The visible root was replaced before normal Quit")
        record["quitQpc"] = api.clock()
        proc.stdin.write(b"Q")
        proc.stdin.flush()
        record["exitCode"] = proc.wait(timeout=15)
        if not api.wait_job_empty(proc.benchmark_job, 3):
            raise ValueError("The GUI left its owned process job active after Quit")

        def destroyed():
            windows.pump()
            return any(hwnd == root["hwnd"] and tag == "destroy" for hwnd, tag, _ in lifetime.events)

        recorder.await_value(destroyed, "Original HWND destruction at normal Quit", timeout=4)
        record.update(windowLifetime=list(lifetime.events), emptyJob=True)
    record["profileRemoved"] = not os.path.lexists(area)


def main(cpu):
    api, _, _, target, host = subjects(build.prepare.TARGET)
    if cpu != target / "cpu-paint":
        raise ValueError("Expected the native retained x64 CPU diagnostic output")
    out = cpu / "handoff"
    out.mkdir()
    record = {key: host[key] for key in ("revision", "run", "attempt", "target")}
    try:
        base = build.read(cpu / "cpu-build.json")
        if any(base[k] != v for k, v in record.items()) or build.sha(cpu / "cpu.exe") != base["application"]["sha256"]:
            raise ValueError("Unrelated staged CPU build")
        record["sources"] = build.observer_sources(record["revision"])
        record["build"] = build.build(cpu, out)
        observe(api, out / "handoff.exe", out, record)
        record["raw"] = {name: build.sha(out / name) for name in ("subject.log", "presents.log", "present-build.log")}
        record["verified"] = check(out, record)
        record["status"] = "passed"
    except Exception as error:
        record.update(status="incomplete", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (out / "result.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu_paint", type=Path)
    main(parser.parse_args().cpu_paint.resolve())
