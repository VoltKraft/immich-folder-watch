"""Start the ordinary Windows GUI twice on an owned, non-input desktop and observe its launcher."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
sys.path[:0] = [str(QA / "windows-performance"), str(QA / "windows-desktop")]
import run as recorder
from native import CleanupUnconfirmed, JobAccounting, pin_new_marker
from win32 import Desktop, bind, check

TARGETS = {"x86_64-pc-windows-msvc": 0x8664, "aarch64-pc-windows-msvc": 0xaa64}
# Read, create windows/menus, observe events, enumerate and write this desktop's objects.
DESKTOP_RIGHTS = 0xCF


def qualify(secondary_lines, primary_lines, receipt):
    if secondary_lines != [f"LAUNCHER_SECONDARY server={receipt['primaryPid']}"]:
        raise ValueError("The no-argument secondary did not exit through the launcher")
    signals = [line for line in primary_lines if line.startswith("LAUNCHER_OPEN ")]
    if signals != [f"LAUNCHER_OPEN client={receipt['secondaryPid']}"]:
        raise ValueError("The primary did not receive the ordinary secondary's local request")
    if (receipt["primaryPid"] == receipt["secondaryPid"] or not receipt["hiddenBeforeLaunch"]
            or receipt["initialWindowPid"] != receipt["primaryPid"]
            or receipt["reopenedWindowPid"] != receipt["primaryPid"]
            or receipt["workerBefore"] != receipt["workerAfter"] or not receipt["workerBefore"]
            or receipt["secondaryExit"] != 0 or not receipt["secondaryJobEmpty"]
            or receipt["secondaryTotalProcesses"] != 1):
        raise ValueError("The observed window, worker or secondary process did not match")


@contextmanager
def child(api, desk, name, exe, arguments, area, env, stream, primary):
    job = api.new_job()
    proc = None
    try:
        inheritable = check(desk.open_named(name, 0, True, DESKTOP_RIGHTS), "OpenDesktopW")
        try:
            if desk.name(inheritable) != name or desk.receiving_input(inheritable) is not False:
                raise ValueError("Expected the original non-input desktop")
            startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [inheritable]})
            # The secondary inherits ordinary standard input and receives no private command pipe.
            inputs = {"stdin": subprocess.PIPE} if primary else {}
            proc = subprocess.Popen([exe, *arguments], cwd=area, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    startupinfo=startup, creationflags=4 | subprocess.CREATE_NO_WINDOW, **inputs)
        finally:
            check(desk.close(inheritable), "CloseDesktop(child inheritance)")
        api.assign_suspended(job, proc, exe)
        api.resume_owned_process(proc.pid)
        yield proc, job
    finally:
        try:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=8)
                if not api.wait_job_empty(job, 1):
                    check(api.terminate_job(job, 1), "TerminateJobObject(owned launcher fixture)")
                    if not api.wait_job_empty(job, 8):
                        raise CleanupUnconfirmed("Launcher-owned descendants could not be reaped")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CleanupUnconfirmed("Launcher-owned process did not exit") from exc
        finally:
            if proc is not None and proc.stdin:
                proc.stdin.close()
            check(api.close(job), "CloseHandle(launcher job)")


def cycle(api, desk, name, desktop, fixture, exe, trial, env, out, label, restart):
    primary_log = out / (label + "-primary.log")
    with ExitStack() as stack:
        stream = stack.enter_context(primary_log.open("xb"))
        args = [] if restart else ["--autostart"]
        proc, job = stack.enter_context(child(api, desk, name, exe, args, trial, env, stream, True))
        windows = fixture.Windows(proc.pid, desktop)
        stack.callback(windows.close)
        def log():
            return primary_log.read_text(encoding="utf-8", errors="replace")
        def wait(check_value, message):
            return recorder.await_value(lambda: recorder.wait_running(proc) or check_value(), message)
        def is_visible():
            return windows.visible(waiting_for_first=True)
        def verify_hwnd(hwnd):
            pid = w.DWORD()
            tid = windows.owner(hwnd, c.byref(pid))
            if pid.value != proc.pid or desk.name(desk.thread_desktop(tid)) != name:
                raise ValueError("The GUI window does not belong to the primary on its private desktop")
            return pid.value
        def command(data):
            proc.stdin.write(data)
            proc.stdin.flush()

        # The caller independently checked the private desktop for an actual notification area.
        command(b"N")
        initial = wait(is_visible, "No visible primary window on the private desktop")
        wait(lambda: "READY Visible Unavailable" in log() and "ADAPTER Dx12 " in log()
             and recorder.idle_complete(log()), "The primary did not finish its two empty inventories")
        worker = recorder.owned_worker(api, proc, primary_log, recorder.await_value)
        handle = recorder.checked(api.open(0x100000 | 0x1000, False, worker))
        stack.callback(api.close, handle)
        def worker_identity():
            status = w.DWORD()
            recorder.checked(api.exit_code(handle, c.byref(status)))
            if (status.value != 259 or api.processes().get(worker, (0, ""))[0] != proc.pid
                    or api.active_job_processes(job) != 2):
                raise ValueError("The primary and its original worker must be the two live job members")
            return [worker, api.process_identity(handle)]
        result = dict(primaryPid=proc.pid, primaryCreation100ns=api.process_identity(int(proc._handle)),
                      initialWindow=initial, initialWindowPid=verify_hwnd(initial), workerBefore=worker_identity())
        if not restart:
            windows.close_window(initial)
            wait(lambda: windows.visible() is None and "WINDOW_RELEASED " in log(), "The primary window did not close")
            result["hiddenBeforeLaunch"] = True
            second_log = out / (label + "-secondary.log")
            with second_log.open("xb") as second_stream, child(api, desk, name, exe, [], trial, env,
                                                                second_stream, False) as (second, second_job):
                result.update(secondaryPid=second.pid, secondaryCreation100ns=api.process_identity(int(second._handle)),
                              secondaryExit=second.wait(timeout=12), secondaryJobEmpty=api.wait_job_empty(second_job, 3))
                counts = JobAccounting()
                recorder.checked(api.query_job(second_job, 1, c.byref(counts), c.sizeof(counts), None))
                result["secondaryTotalProcesses"] = counts.total
            reopened = wait(is_visible, "The ordinary secondary did not reopen the primary GUI")
            wait(lambda: log().count("ADAPTER Dx12 ") >= 2, "The reopened GUI did not acquire its DX12 adapter")
            result.update(reopenedWindow=reopened, reopenedWindowPid=verify_hwnd(reopened),
                          primaryForeground=desk.foreground() == reopened, workerAfter=worker_identity())
            qualify(second_log.read_text(encoding="utf-8").splitlines(), log().splitlines(), result)
        command(b"Q")
        result.update(primaryExit=proc.wait(timeout=15), primaryJobEmpty=api.wait_job_empty(job, 4))
        if (result["primaryExit"] or not result["primaryJobEmpty"] or "DRAINED passes=" not in log()
                or f"LAUNCHER_PRIMARY pid={proc.pid}" not in log()):
            raise ValueError("The primary and its owned inventory did not drain normally")
        return result


def desktop_cases(api, desk, name, desktop, exe, trial, env, out):
    user = c.WinDLL("user32", use_last_error=True)
    select_thread = bind(user, "SetThreadDesktop", w.BOOL, w.HANDLE)
    shell = bind(user, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
    create = bind(user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                  c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p)
    destroy = bind(user, "DestroyWindow", w.BOOL, w.HWND)
    check(select_thread(desktop), "SetThreadDesktop(fixture observer thread)")
    if (desk.name(desk.thread_desktop(desk.thread())) != name or desk.receiving_input(desktop) is not False
            or shell("Shell_TrayWnd", None)):
        raise ValueError("The observation thread requires the owned shell-less non-input desktop")
    # A never-shown observer-owned window keeps HWND enumeration meaningful after the GUI closes.
    anchor = check(create(0x08000080, "STATIC", name, 0x80000000, 0, 0, 1, 1, None, None, None, None), "CreateWindowExW")
    try:
        fixture = recorder.load_windows_fixture()
        activated = cycle(api, desk, name, desktop, fixture, exe, trial, env, out, "activation", False)
        restarted = cycle(api, desk, name, desktop, fixture, exe, trial, env, out, "restart", True)
        if (activated["primaryCreation100ns"] == restarted["primaryCreation100ns"]
                or desk.receiving_input(desktop) is not False or shell("Shell_TrayWnd", None)):
            raise ValueError("A fresh elected primary on the original shell-less desktop was required")
        return dict(activation=activated, restart=restarted, shellAbsent=True, desktopReceivedInput=False)
    finally:
        check(destroy(anchor), "DestroyWindow(private enumeration witness)")


def run(target, out, result):
    if (not recorder.hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the dedicated disposable native rewrite runner")
    artifacts = ROOT / "artifacts/rust"
    exe = artifacts / "gui-build/release/native-gui-assessment.exe"
    receipt_path = artifacts / "gui-native" / target / "build.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    profile = json.loads((ROOT / "rust/audit/gui-profile.json").read_text(encoding="utf-8"))
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    gui_source = QA / "gui"
    lifecycle = ROOT / "rust/crates/desktop-lifecycle"
    required = {path.relative_to(ROOT).as_posix() for path in
                [gui_source / "Cargo.toml", *sorted((gui_source / "src").glob("*.rs")),
                 gui_source / "src/tray-icon.argb", ROOT / "rust/Cargo.toml",
                 lifecycle / "Cargo.toml", lifecycle / "src/lib.rs"]}
    if (receipt["source"] != revision or receipt["target"] != target or recorder.sha(exe) != receipt["binarySha256"]
            or recorder.pe_machine(exe) != TARGETS[target] or receipt["graphSha256"] != profile["targetReportSha256"][target]
            or receipt["lockSha256"] != profile["lockSha256"]
            or required != set(receipt["compilerSources"])
            or any(recorder.sha(ROOT / path) != digest for path, digest in receipt["compilerSources"].items())):
        raise ValueError("The ordinary native GUI and its reviewed inputs must match the checkout")
    api, desk = recorder.Win32(), Desktop()
    if api.machine(-1) != (TARGETS[target], TARGETS[target]):
        raise ValueError("A native target-matching Windows observer is required")
    result.update(revision=revision, target=target, run=os.environ["GITHUB_RUN_ID"],
                  attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  buildReceipt=recorder.sha(receipt_path), gui=receipt["binarySha256"], graph=receipt["graphSha256"],
                  lock=receipt["lockSha256"],
                  observerInputs={path.relative_to(ROOT).as_posix(): recorder.sha(path) for path in
                                  (Path(__file__).resolve(), QA / "observe-windows-gui.py", QA / "windows-desktop/win32.py",
                                   QA / "windows-performance/native.py", QA / "windows-performance/run.py",
                                   QA / "windows-performance/build.py")})
    token = uuid.uuid4().hex
    with recorder.owned_directory(api, Path(os.environ["RUNNER_TEMP"]), "ifw-rw02-" + token) as root, ExitStack() as stack:
        pin_new_marker(stack, api, root / "inventory.owner", token)
        # CREATE_NEW and retain a read handle giving the elected primary write sharing.
        pid_file = api.create_file(str(root / "launcher.pid"), 0x80000000, 3, None, 1, 0x00200000, None)
        if pid_file == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        stack.callback(api.close, pid_file)
        gui, _, inventory = recorder.build_subject(root, out, exe, target, recorder.pe_machine)
        for image, digest in ((gui, result["gui"]), (gui.with_name("ifw-performance-worker.exe"), inventory["worker"])):
            stack.enter_context(recorder.pin_path(api, image, False))
            if recorder.sha(image) != digest:
                raise ValueError("The pinned staged executable differs from its build")
        result["inventory"] = inventory
        trial = root / "rust-1"
        media = trial / "empty"
        media.mkdir(parents=True)
        offline = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        offline.bind(("127.0.0.1", 0))
        env = recorder.environment(trial, "http://127.0.0.1:" + str(offline.getsockname()[1]), True, media, token)
        env.update(IFW_QA_WINDOWS_LAUNCHER="1", IFW_QA_LAUNCHER_SID=recorder.sid())
        name = "IfwQa_Launcher_" + token
        with ThreadPoolExecutor(max_workers=1) as creator:
            creation = creator.submit(desk.create, name, None, None, 0, DESKTOP_RIGHTS, None)
            desktop = check(creation.result(), "CreateDesktopW")
        try:
            with ThreadPoolExecutor(max_workers=1) as observer:
                result.update(observer.submit(desktop_cases, api, desk, name, desktop, gui, trial, env, out).result())
        finally:
            check(desk.close(desktop), "CloseDesktop(launcher)")
    result["cleanupConfirmed"] = True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    options = parser.parse_args()
    output = ROOT / "artifacts/rust/windows-launcher" / options.target
    output.mkdir(exist_ok=False, parents=True)
    results = {}
    try:
        run(options.target, output, results)
        recorder.write(output / "result.json", dict(status="passed", **results))
    except Exception as exc:
        recorder.write(output / "result.json", dict(status="failed", error=str(exc), **results))
        raise
