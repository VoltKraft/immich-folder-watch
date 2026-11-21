"""Observe warm HWND reuse, independent hidden dispatcher wake, device replacement and resident pages."""
import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from inputs import HERE, QA, ROOT, TARGETS, recorder, sha, subjects
from native import owned_directory, pin_path
from residency import sample


class WindowLifetime:
    def __init__(self, pid):
        from native import bind, checked
        user = c.WinDLL("user32", use_last_error=True)
        callback_type = c.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)
        hook = bind(user, "SetWinEventHook", w.HANDLE, w.DWORD, w.DWORD, w.HMODULE, callback_type,
                    w.DWORD, w.DWORD, w.DWORD)
        self.unhook = bind(user, "UnhookWinEvent", w.BOOL, w.HANDLE)
        self.events = []
        @callback_type
        def callback(_hook, event, hwnd, object_id, child, _thread, tick):
            if hwnd and object_id == 0 and child == 0:
                self.events.append((int(hwnd), "create" if event == 0x8000 else "destroy", tick))
        self.callback = callback
        self.hook = checked(hook(0x8000, 0x8001, None, callback, pid, 0, 0))

    def close(self):
        recorder.checked(self.unhook(self.hook))


def drive(api, fixture, binary, output, name):
    background = name.startswith("background") or name == "absent-tray"
    warm = name != "cold-residency"
    has_tray = name != "absent-tray"
    recovery = name in ("visible-loss", "edited-loss", "hidden-loss")
    result = dict(case=name, transitions=[], samples={})
    log = output / "subject.log"
    output.mkdir()
    with ExitStack() as stack:
        root = stack.enter_context(owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + uuid.uuid4().hex))
        env = {k: v for k, v in os.environ.items() if not k.startswith("IFW_QA_")}
        env.update(IFW_QA_ISOLATED="1", WGPU_DX12_COMPILER="Fxc", TEMP=str(root), TMP=str(root))
        for key in ("APPDATA", "LOCALAPPDATA", "HOME", "USERPROFILE"):
            folder = root / key
            folder.mkdir()
            env[key] = str(folder)
        if recovery:
            env["IFW_QA_GRAPHICS"] = "recover"
        if warm and name.endswith("residency"):
            env["IFW_QA_WINDOWS_RESIDENCY"] = "performance-control" if name == "performance-residency" else "1"
        stream = stack.enter_context(log.open("wb"))
        proc = subprocess.Popen([binary, *(["--background"] if background else [])], cwd=root, env=env,
                                stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        stack.callback(recorder.stop_subject, proc, True)
        observer = fixture.Windows(proc.pid)
        stack.callback(observer.close)
        lifetime = WindowLifetime(proc.pid)
        stack.callback(lifetime.close)
        handle = recorder.checked(api.open(0x0410, False, proc.pid))
        stack.callback(api.close, handle)
        result.update(pid=proc.pid, creation100ns=api.process_identity(handle))

        def send(data):
            proc.stdin.write(data)
            proc.stdin.flush()

        def logs():
            return log.read_text(encoding="utf-8", errors="replace").splitlines()

        def wait(check, label):
            def poll():
                recorder.wait_running(proc)
                observer.pump()
                return check()
            return recorder.await_value(poll, f"{name}: {label}", timeout=35, delay=.005)

        def still_owned(hwnd):
            pid = w.DWORD()
            caption = c.create_unicode_buffer(256)
            return (observer.owner(hwnd, c.byref(pid)) and pid.value == proc.pid
                    and observer.caption(hwnd, caption, len(caption)) and caption.value == fixture.TITLE)

        def residency_at(phase):
            time.sleep(3)
            snapshot = sample(api, handle)
            if warm:
                def reports():
                    return [s for s in logs() if s.startswith("WGPU_ALLOCATOR ")]
                previous = len(reports())
                send(b"M")
                line = wait(lambda: rows[-1] if len(rows := reports()) == previous + 1 else None,
                            "device allocator report")
                if line == "WGPU_ALLOCATOR unavailable":
                    snapshot["deviceAllocator"] = {"status": "unavailable"}
                else:
                    fields = re.fullmatch(r"WGPU_ALLOCATOR allocated=(\d+) reserved=(\d+) blocks=(\d+) allocations=(\d+)", line)
                    if not fields:
                        raise ValueError("Invalid device allocator report")
                    snapshot["deviceAllocator"] = dict(zip(("allocatedBytes", "reservedBytes", "blocks", "allocations"),
                                                           map(int, fields.groups()), strict=True))
            result["samples"][phase] = snapshot

        def ready(retiring=None):
            hwnd = observer.visible(retiring)
            return hwnd if hwnd and any(line.startswith("ADAPTER Dx12 ") for line in logs()) else None

        def quiet_hidden(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                recorder.wait_running(proc)
                if observer.visible() is not None:
                    raise RuntimeError("Unexpected window on hidden startup")
                time.sleep(.005)
            observer.pump()
            if any(e["event"] == "show" for e in observer.events) or any(s.startswith("GRAPHICS_ATTEMPT ") for s in logs()):
                raise ValueError("Observed a native show or renderer allocation before activation")

        def cycle(hwnd, *, quit_hidden=False):
            observer.pump()
            start = len(observer.events)
            lifetime_start = len(lifetime.events)
            generations = [s for s in logs() if s.startswith("GRAPHICS_READY ")]
            observer.close_window(hwnd)
            wait(lambda: not observer.visible() and any(e["event"] == "hide" and e["hwnd"] == hwnd
                 for e in observer.events[start:]), "owned hide event")
            if warm and (not still_owned(hwnd) or observer.is_visible(hwnd)):
                raise ValueError("The hidden HWND lost its owner or title")
            if not warm:
                wait(lambda: any(s.startswith("WINDOW_RELEASED ") for s in logs()), "cold graphics teardown")
            if name.endswith("residency"):
                residency_at("hidden")
            result["transitions"].append(dict(hidden=hwnd, generationBefore=generations))
            if quit_hidden:
                return
            start = len(observer.events)
            send(b"O")
            actual = wait(lambda: ready(), "visible after activation")
            wait(lambda: any(e["event"] == "show" and e["hwnd"] == actual for e in observer.events[start:]), "reopen show event")
            now = [s for s in logs() if s.startswith("GRAPHICS_READY ")]
            if warm and (hwnd != actual or now != generations or not still_owned(hwnd)):
                raise ValueError("Ordinary activation replaced the HWND or DX12 generation")
            if warm and any(item[0] == hwnd for item in lifetime.events[lifetime_start:]):
                raise ValueError("A native creation or destruction occurred for the retained HWND")
            if not warm and len(now) != len(generations) + 1:
                raise ValueError("Cold control did not replace its DX12 generation")
            result["transitions"][-1].update(reopened=actual, generationAfter=now)
            return actual

        def field(hwnd, phase):
            shell, attempts = fixture.select_powershell(root, "accessibility")
            recorder.write(output / ("hosts-" + phase + ".json"), attempts)
            if not shell:
                raise RuntimeError("The independent UI Automation observer is unavailable")
            evidence = output / ("field-" + phase + ".json")
            with (output / ("field-" + phase + ".log")).open("wb") as trace:
                subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
                                "-File", str(QA / "observe-windows-input.ps1"), "-SubjectId", str(proc.pid),
                                "-WindowHandle", str(hwnd), "-SubjectLog", str(log), "-OutputFile", str(evidence),
                                "-RecoveryPhase", phase], cwd=root, env=env, stdin=subprocess.DEVNULL,
                               stdout=trace, stderr=subprocess.STDOUT, check=True, timeout=85)
            found = json.loads(evidence.read_text(encoding="utf-8-sig"))
            if found.get("status") != "passed" or found.get("processId") != proc.pid:
                raise ValueError("Unverified owned HWND editing observation")
            result[phase + "Field"] = sha(evidence)

        send(b"T" if has_tray else b"N")
        hidden = background and has_tray
        status = "READY " + ("BackgroundStartup" if hidden else "Visible") + (" Available" if has_tray else " Unavailable")
        wait(lambda: status in logs(), "supervisor startup")
        if hidden:
            quiet_hidden(1)
            if name != "background-quit":
                send(b"O")
        if name != "background-quit":
            hwnd = wait(ready, "first DX12 HWND")
            if name.endswith("residency"):
                residency_at("visible")
            if name in ("retained-edit", "edited-loss"):
                field(hwnd, "before")
            if recovery:
                if name == "hidden-loss":
                    cycle(hwnd, quit_hidden=True)
                send(b"G")
                wait(lambda: "GRAPHICS_LOST generation=1 reason=Destroyed" in logs(), "first device loss")
                if name == "hidden-loss":
                    wait(lambda: any(s.startswith("WINDOW_RELEASED ") for s in logs()) and not observer.visible(),
                         "hidden lost device disposed")
                    since = len(observer.events)
                    end = time.monotonic() + .5
                    while time.monotonic() < end:
                        recorder.wait_running(proc)
                        if observer.visible() or any(line.startswith("GRAPHICS_ATTEMPT generation=2 ") for line in logs()):
                            raise ValueError("The failed hidden renderer reopened before user activation")
                        time.sleep(.005)
                    observer.pump()
                    if any(e["event"] == "show" and e["root"] for e in observer.events[since:]):
                        raise ValueError("The failed hidden renderer showed an unrequested window")
                    send(b"O")
                def replacement():
                    new = ready(hwnd)
                    return new if (new and new != hwnd and "GRAPHICS_READY generation=2" in logs()
                                   and "GRAPHICS_ATTEMPT generation=2 policy=cpu" in logs()) else None
                new = wait(replacement, "a replacement HWND after device destruction")
                result["replacement"] = dict(old=hwnd, new=new)
                if name == "edited-loss":
                    field(new, "after")
                hwnd = new
            normal = cycle(hwnd)
            if name == "retained-edit":
                field(normal, "after")
            if name.endswith("residency"):
                residency_at("reopened")
            if name == "background-open":
                cycle(normal, quit_hidden=True)
        send(b"Q")
        proc.wait(timeout=20)
        observer.pump()
        if proc.returncode or not any(s.startswith("DRAINED passes=") for s in logs()):
            raise ValueError("The native subject failed to drain")
        if name == "background-quit" and ("DRAINED passes=0" not in logs()
                or any(line.startswith("GRAPHICS_ATTEMPT ") for line in logs())
                or any(e["event"] == "show" for e in observer.events)):
            raise ValueError("Quitting the never-shown supervisor allocated or displayed a window")
        if warm and name != "background-quit":
            hint = "Performance" if name == "performance-residency" else "MemoryUsage"
            hints = [s for s in logs() if s.startswith("GRAPHICS_MEMORY ")]
            expected = [f"GRAPHICS_MEMORY generation={number} hint={hint}" for number in range(1, 3 if recovery else 2)]
            if hints != expected:
                raise ValueError(f"Unexpected actual native device descriptor: {hints}")
            result["actualDeviceDescriptors"] = hints
        result.update(exitCode=proc.returncode, windowEvents=observer.events, objectLifetimes=lifetime.events, subjectLog=sha(log))
    return result


def main(target):
    api, cold, warm, output, record = subjects(target)
    out = output / "observed"
    out.mkdir()
    record["controls"] = {}
    files = [HERE / s for s in ("observe.py", "inputs.py", "residency.py")]
    files.extend(QA / s for s in ("observe-windows-gui.py", "observe-windows-input.ps1", "windows_observer.py",
                                  "windows-performance/native.py", "windows-performance/run.py"))
    record["observerInputs"] = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    fixture = recorder.load_windows_fixture()
    for name in ("background-quit", "background-open", "absent-tray", "retained-edit", "visible-loss", "edited-loss", "hidden-loss",
                 "cold-residency", "performance-residency", "warm-residency"):
        binary = cold if name == "cold-residency" else warm
        try:
            with pin_path(api, binary, False):
                if sha(binary) != record["baseline" if binary == cold else "binary"]:
                    raise ValueError("The pinned executable changed")
                record["controls"][name] = drive(api, fixture, binary, out / name, name)
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, TimeoutError) as exc:
            record["controls"][name] = {"error": f"{type(exc).__name__}: {exc}"}
            if recorder.CleanupUnconfirmed.in_chain(exc):
                recorder.write(out / "result.json", record)
                raise
        recorder.write(out / "result.json", record)
    return int(any("error" in value for value in record["controls"].values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    raise SystemExit(main(parser.parse_args().target))
