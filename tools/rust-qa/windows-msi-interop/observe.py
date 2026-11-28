"""Observe the original installed WPF process delivering SHOW_GUI to the same Rust HWND."""
from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from common import AREA, TARGETS, launcher, read, sha, write


def verify_suspended_secondary(api, second):
    if second.poll() is not None or api.job_pids(second.benchmark_job) != {second.pid}:
        raise ValueError("The installed secondary did not remain suspended as the sole member of its job")


@contextmanager
def file_trace(recorder, helper, trial, out, worker, record, *, independent):
    name = "IFW-Files-" + uuid.uuid4().hex
    etl = trial / "files.etl"
    path = out / "files.log"
    with path.open("xb", buffering=0) as stream:
        subject = "msi-rust" if independent else "rust"
        child = subprocess.Popen([helper, str(worker), name, etl, trial / "empty", subject], cwd=trial,
                                 stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        try:
            recorder.await_value(lambda: child.poll() is not None or f"READY {worker} rust".encode() in path.read_bytes().splitlines(),
                                 "The worker file observer did not attach", timeout=25, delay=.02)
            if child.poll() is not None:
                raise ValueError("The worker file observer exited before the challenge")
            yield
        finally:
            recorder.finish_owned_trace(child, helper, trial, etl, name, 45)
            record["traceExit"] = child.returncode
            if etl.is_file():
                record.update(etlBytes=etl.stat().st_size, etlSha256=sha(etl))
        if child.returncode or not record.get("etlBytes"):
            raise ValueError(f"The original worker file trace was incomplete (decoder exit {child.returncode})")
        etl.unlink()


def exercise(launch, desk, api, gui, trial, env, image, work, out, row):
    recorder = launch.recorder
    desk_handle = launch.check(desk.thread_desktop(desk.thread()), "GetThreadDesktop")
    name = desk.name(desk_handle)
    row["desktopBefore"] = desk.context()
    if name != "Default" or not launch.ordinary_console(row["desktopBefore"], name):
        raise ValueError("The original unlocked runner desktop is required")
    sid = recorder.sid()
    api.ensure_no_primary(sid)
    env["IFW_QA_MSI_PRIMARY"] = "1"
    fixture = recorder.load_windows_fixture()
    fixture.TITLE = "Desktop input probe"
    logpath = out / "primary.log"
    log = lambda: logpath.read_text(encoding="utf-8")
    console = launch.system_console_path(api.kernel)
    with ExitStack() as stack:
        stack.enter_context(recorder.pin_path(api, image, False))
        original = read(out / "installed.json")
        payload = read(out / "payload-installed.json")["entries"]["AppExecutableFile"]
        if (Path(original["exe"]) != image or original["exeSha256"] != sha(image)
                or original["exeSha256"] != payload["sha256"] or payload["path"] != image.name):
            raise ValueError("The installed executable differs from the original cabinet")
        primary_log = stack.enter_context(logpath.open("xb"))
        proc, job, _ = stack.enter_context(launch.child(api, desk, name, gui, [], trial, env, primary_log, True, private=False))
        windows = fixture.Windows(proc.pid, desk_handle)
        stack.callback(windows.close)
        retained = launch.RetainedWindow(desk, windows, fixture.TITLE, name, row.setdefault("root", {}))
        stack.callback(retained.close)
        def wait(get, label):
            def poll():
                windows.pump()
                recorder.wait_running(proc)
                return get()
            return recorder.await_value(poll, label, delay=.02)

        row["primary"] = [proc.pid, api.process_identity(int(proc._handle))]
        proc.stdin.write(b"T")
        proc.stdin.flush()
        hwnd = wait(lambda: windows.visible(waiting_for_first=True), "Rust did not show its original HWND")
        retained.first(hwnd, log, wait)
        wait(lambda: recorder.idle_complete(log()), "Both initial empty Rust inventories are required")
        worker = recorder.owned_worker(api, proc, logpath, recorder.await_value)
        held = api.open_job_member(job, worker)
        stack.callback(api.close, held)
        def members(phase):
            api.verify_job_member(job, worker, held)
            return launch.primary_job_members(api, desk, job, proc.pid, worker, gui, console, row.setdefault(phase, {}))
        row["worker"] = members("before")
        # A pure reference to the just-elected mutex also keeps WPF secondary if Rust exits unexpectedly.
        hold_mutex = recorder.bind(api.kernel, "OpenMutexW", w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
        mutex = recorder.checked(hold_mutex(0x100000, False, "Local\\ImmichFolderWatch-" + sid))
        stack.callback(api.close, mutex)
        retained.close_window()
        wait(lambda: retained.hidden(log()), "Rust did not hide its retained HWND")
        with ExitStack() as secondary:
            stream = secondary.enter_context((out / "secondary.log").open("xb"))
            # Keep the actual WPF KnownFolders, its pre-seeded profile and this process's closed loopback proxy.
            second = recorder.start_owned_subject(secondary, api, image, work, dict(os.environ), stream, False, recorder.stop_subject)
            record = row["secondary"] = dict(pid=second.pid, created=api.process_identity(int(second._handle)),
                                             executable=str(image), arguments=[], sha256=original["exeSha256"])
            from native import pin_new_marker
            pin_new_marker(secondary, api, trial.parent / "msi-secondary.pid", f"{second.pid:032x}")
            verify_suspended_secondary(api, second)
            if not retained.hidden(log()) or proc.poll() is not None:
                raise ValueError("The original GUI changed before release")
            tick = recorder.bind(api.kernel, "GetTickCount64", c.c_uint64)
            cursor, earliest = len(windows.events), tick()
            record["releasedAfterQpc"] = api.clock()
            api.resume_owned_process(second.pid)
            released_by = tick()
            record["exit"] = launch.wait_for_exit(second, windows.pump, 12)
            if not api.wait_job_empty(second.benchmark_job, 3):
                raise ValueError("The installed WPF secondary left a running job member")
            counts = api.job_accounting(second.benchmark_job)
            record["totalProcesses"], record["activeAfter"] = counts.total, counts.active
            if record["exit"] or counts.total != 1 or counts.active:
                raise ValueError("The installed WPF secondary did not exit as the sole member of its job")
            wait(lambda: f"LAUNCHER_OPEN client={second.pid}" in log().splitlines(), "Missing native WPF pipe client")
            opened = wait(windows.visible, "The installed secondary did not reopen the Rust HWND")
            retained.opened(opened, log, wait)
            if not retained.activated_show(cursor, earliest, tick(), "msiShow", released_by=released_by):
                raise ValueError("The native SHOW timing did not establish activation after the MSI secondary resumed")
            row["reopenedByQpc"] = api.clock()

        challenge = row["challenge"] = {}
        helper = work / "subject/file-observer.exe"
        stack.enter_context(recorder.pin_path(api, helper, False))
        with file_trace(recorder, helper, trial, out, worker, challenge,
                        independent=original["target"] == "x86_64-pc-windows-msvc"):
            staged = trial / "new-file"
            staged.mkdir()
            path = staged / "f0000.jpg"
            data = uuid.uuid4().bytes
            path.write_bytes(data)
            with (out / "challenge.jpg").open("xb") as copy:
                copy.write(data)
            challenge["sha256"] = sha(path)
            challenge["introducedAfterQpc"] = api.clock()
            staged.rename(trial / "empty/d0000")
            wait(lambda: re.search(r"^INVENTORY_COMPLETE files=1 changed=1 pass=\d+$", log(), re.M),
                 "The original inventory did not see the newly introduced file")
            wait(lambda: re.search(r"^INVENTORY_COMPLETE files=1 changed=0 pass=\d+$", log(), re.M),
                 "The original worker did not complete the next reconciliation")
            challenge["observedByQpc"] = api.clock()
            if (trial / "empty/d0000/f0000.jpg").read_bytes() != data or members("after") != row["worker"]:
                raise ValueError("The challenge object or the original inventory process changed")
        retained.check_visible(log, "afterInventory")
        row["quit"] = recorder.stop_subject(proc, True, drain_log=logpath)
        if not api.wait_job_empty(job, 5):
            raise ValueError("Rust did not drain its process job after Quit")
        launch.retained_graphics(log(), row["root"], before_quit=False)
        row["jobDrained"] = True
    api.ensure_no_primary(sid)
    row["desktopAfter"] = desk.context()
    if not launch.ordinary_console(row["desktopAfter"], name):
        raise ValueError("The ordinary input desktop changed")


def run(target, out, work, image):
    if out != AREA / target or not work.is_relative_to(Path(os.environ["RUNNER_TEMP"]).resolve()):
        raise ValueError("Unexpected installed observation paths")
    launch = launcher()
    if not launch.recorder.hosted() or os.environ.get("GITHUB_REF") != "refs/heads/rewrite/rust":
        raise ValueError("The installed launcher requires the disposable rewrite runner")
    build = read(out / "build.json")
    staged = work / "subject"
    if (build["target"] != target or build["source"] != os.environ["GITHUB_SHA"]
            or any(sha(staged / n) != digest for n, digest in build["assets"].items())):
        raise ValueError("The observer inputs differ from their own native compiler")
    row = dict(status="incomplete", session="ordinary", frequency=None)
    try:
        api, desk = launch.recorder.Win32(), launch.Desktop()
        if api.machine(-1) != (TARGETS[target][1], TARGETS[target][1]):
            raise ValueError("The recorder and operating system must match the native target")
        row["frequency"] = api.frequency
        inventory = dict(build["base"]["inventory"], gui=build["assets"]["native-gui-assessment.exe"])
        with launch.staged_profile(row, api, staged / "native-gui-assessment.exe", inventory) as (gui, trial, env):
            exercise(launch, desk, api, gui, trial, env, image, work, out, row)
        row["status"] = "observed"
    finally:
        write(out / "activation.json", row)


if __name__ == "__main__":
    target, out, work, image = sys.argv[1:]
    run(target, Path(out).resolve(), Path(work).resolve(), Path(image).resolve())
