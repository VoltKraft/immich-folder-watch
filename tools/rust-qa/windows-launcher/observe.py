"""Observe the ordinary Windows launcher on the disposable runner and its private non-input desktop."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
sys.path[:0] = [str(QA / "windows-performance"), str(QA / "windows-desktop")]
import run as recorder
from native import CleanupUnconfirmed, JobAccounting, ThreadEntry, dispose_empty_directory, pin_new_marker
from named_process import start as start_named
from win32 import Desktop, bind, check, ordinary_console
from window_readback import PrivateMembership, check_private_snapshot, paint_control, snapshot
import retained_subject
from retained_window import LIFETIME, RetainedWindow, ShowOrderUnavailable, graphics as retained_graphics

TARGETS = {"x86_64-pc-windows-msvc": 0x8664, "aarch64-pc-windows-msvc": 0xaa64}
SUBJECTS = ("canonical", "retained")
# Read, create windows/menus, observe events, enumerate and write this desktop's objects.
DESKTOP_RIGHTS = 0xCF


class JobProcessIds(c.Structure):
    # JOBOBJECT_BASIC_PROCESS_ID_LIST has two DWORD counts followed by ULONG_PTR IDs.
    _fields_ = [("assigned", c.c_uint32), ("listed", c.c_uint32), ("ids", c.c_size_t * 16)]


def system_console_path(kernel):
    directory = c.create_unicode_buffer(32768)
    get_directory = bind(kernel, "GetSystemDirectoryW", w.UINT, w.LPWSTR, w.UINT)
    if check(get_directory(directory, len(directory)), "GetSystemDirectoryW") >= len(directory):
        raise ValueError("The native system directory did not fit its buffer")
    return PureWindowsPath(directory.value) / "conhost.exe"


def primary_job_members(api, desk, job, primary, worker, exe, console, record):
    listing = JobProcessIds()
    recorder.checked(api.query_job(job, 3, c.byref(listing), c.sizeof(listing), None))
    if listing.listed != listing.assigned or listing.listed > len(listing.ids):
        raise ValueError("The primary job process list was incomplete")
    pids = sorted(listing.ids[:listing.listed])
    members = []
    record.update(pids=pids, members=members)
    if len(pids) != len(set(pids)) or primary == worker or not {primary, worker}.issubset(pids):
        raise ValueError("The primary job must still contain both original application processes")
    entries = api.processes()
    consoles = set()
    exe = PureWindowsPath(exe)
    for pid in pids:
        # Only query processes returned by this job. Recheck membership on the opened handle.
        handle = recorder.checked(api.open(0x1000, False, pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        try:
            belongs, status = w.BOOL(), w.DWORD()
            recorder.checked(api.in_job(handle, job, c.byref(belongs)))
            if not belongs.value:
                raise ValueError("A selected process no longer belongs to the primary job")
            recorder.checked(api.exit_code(handle, c.byref(status)))
            if status.value != 259 or pid not in entries:
                raise ValueError("A selected job member exited before its identity was observed")
            buffer = c.create_unicode_buffer(32768)
            length = w.DWORD(len(buffer))
            check(desk.image(handle, 0, buffer, c.byref(length)), "QueryFullProcessImageNameW")
            image = PureWindowsPath(buffer.value)
            parent = entries[pid][0]
            member = dict(pid=pid, parent=parent, image=image.name, creation100ns=api.process_identity(handle))
            members.append(member)
            if pid == primary and image == exe:
                member["role"] = "primary"
            elif pid == worker and parent == primary and image == exe.with_name("ifw-performance-worker.exe"):
                member["role"] = "worker"
            elif (pid not in (primary, worker) and parent in (primary, worker)
                  and image == console and parent not in consoles):
                member["role"] = "systemConsoleHost"
                consoles.add(parent)
            else:
                raise ValueError("Unexpected executable or parent in the primary job")
        finally:
            release_handle(api.close, "CloseHandle(launcher member)", handle)
    return [worker, next(member["creation100ns"] for member in members if member["pid"] == worker)]


def qualify(secondary_lines, primary_lines, receipt):
    pid = receipt["primaryPid"]
    if len(secondary_lines) != 2 or secondary_lines[1] != f"LAUNCHER_SECONDARY server={pid}":
        raise ValueError("The no-argument secondary did not exit through the launcher")
    grant = re.fullmatch(rf"LAUNCHER_FOREGROUND_GRANT server={pid} state="
                         r"(granted|denied hresult=(-?\d+)|unavailable reason=(legacy-pid|input-desktop|process-handle|process-identity))",
                         secondary_lines[0])
    requests = [line for line in primary_lines if line.startswith("WINDOW_FOREGROUND_REQUEST ")]
    request = (re.fullmatch(rf"WINDOW_FOREGROUND_REQUEST pid={pid} hwnd={receipt['reopenedWindow']} accepted=(true|false)",
                            requests[0]) if len(requests) == 1 else None)
    if grant is None or request is None:
        raise ValueError("The foreground handoff did not match one explicit request on the reopened primary HWND")
    receipt["foregroundHandoff"] = dict(server=pid, grant=grant[1].split()[0], hwnd=receipt["reopenedWindow"],
                                       hresult=int(grant[2]) if grant[2] else None,
                                       unavailableReason=grant[3], requestAccepted=request[1] == "true")
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


def release(action, label, *args):
    try:
        return action(*args)
    except Exception as exc:
        raise CleanupUnconfirmed(label) from exc


def release_handle(close, label, handle):
    return release(lambda: check(close(handle), label), label)


@contextmanager
def child(api, desk, name, exe, arguments, area, env, stream, primary, *, private=True, before_resume=None,
          named_input=False, before_create=None):
    job = api.new_job()
    proc = None
    try:
        with ExitStack() as startup:
            desktop = check(desk.open_named(name, 0, False, 1), "OpenDesktopW(verify launcher desktop)")
            startup.callback(release_handle, desk.close, "CloseDesktop(verify launcher desktop)", desktop)
            input_expected = not private
            expected_input_name = ("IfwQa_" + env["IFW_QA_INVENTORY_TOKEN"]) if named_input else "Default"
            if (named_input and private or desk.name(desk.station()) != "WinSta0" or desk.name(desktop) != name
                    or desk.receiving_input(desktop) is not input_expected
                    or desk.name(desk.thread_desktop(desk.thread())) != name
                    or (not private and (name != expected_input_name or not ordinary_console(desk.context(), name)))):
                raise ValueError("Expected the original launcher thread and desktop")
            launch_options = {"named_input": True, "before_create": before_create} if named_input else {}
            proc = start_named(exe, arguments, cwd=area, env=env, stream=stream, desktop=name, primary=primary,
                               **launch_options)
        api.assign_suspended(job, proc, exe)
        thread_id = None
        if primary:
            threads = [e.tid for e in api.snapshot_entries(4, ThreadEntry, api.walk_thread) if e.owner == proc.pid]
            if threads != [proc.thread_id]:
                raise ValueError("The suspended primary must have the one initial thread returned by CreateProcessW")
            thread_id = proc.thread_id
        if before_resume is not None:
            before_resume(proc)
        proc.resume()
        yield proc, job, thread_id
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
        except Exception as exc:
            raise CleanupUnconfirmed("Launcher-owned process did not exit") from exc
        finally:
            try:
                if proc is not None:
                    release(proc.close, "Could not close the launcher's retained process, thread or command pipe")
            finally:
                release_handle(api.close, "CloseHandle(launcher job)", job)


def wait_for_exit(proc, pump, timeout):
    def status():
        pump()
        code = proc.poll()
        return (code,) if code is not None else None
    return recorder.await_value(status, f"Launcher process {proc.pid} did not exit", timeout=timeout, delay=.02)[0]


def passive_foreground(desk, windows, hwnd, initial):
    """Observe delayed native foreground assignment without requesting focus or examining another window."""
    started = time.monotonic()
    matched, samples, still_visible = initial, 1, True
    while not matched and time.monotonic() - started < 2:
        time.sleep(.05)
        still_visible = windows.visible() == hwnd
        if not still_visible:
            break
        matched = desk.foreground() == hwnd
        samples += 1
    return dict(initial=initial, observed=matched, sameWindowVisible=still_visible, samples=samples,
                elapsedMs=round((time.monotonic() - started) * 1000))


def drain_after_failure(proc, log, result, pump):
    """Retain the application's own UI-pass count when ordinary Quit still drains it."""
    observation = result["failureDrain"] = {}
    try:
        if proc.poll() is None:
            proc.stdin.write(b"Q")
            proc.stdin.flush()
        observation["exit"] = wait_for_exit(proc, pump, 5)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        observation["error"] = str(exc)
    matches = re.findall(r"^DRAINED passes=(\d+)$", log(), re.MULTILINE)
    if len(matches) == 1 and observation.get("exit") == 0:
        observation["uiPassesAtQuit"] = int(matches[0])


def cycle(api, desk, name, desktop, witness, fixture, exe, console, trial, env, out, label, result, *, tray=False,
          native_tray=None, subject="canonical", keyboard_launcher=None):
    primary_log = out / (label + "-primary.log")
    autostart = label == "activation"
    private = witness is not None and keyboard_launcher is None
    args = ["--autostart"] if autostart else []
    show_ordered = True
    result.update(stage="primary-start", primaryArguments=args, initialTrayAvailable=tray,
                  windowReadbacks={})
    with ExitStack() as stack:
        stream = stack.enter_context(primary_log.open("xb"))
        input_options = {"named_input": True} if keyboard_launcher is not None else {}
        proc, job, tid = stack.enter_context(child(api, desk, name, exe, args, trial, env, stream, True,
                                                  private=private, **input_options))
        result.update(primaryPid=proc.pid, primaryCreation100ns=api.process_identity(int(proc._handle)))
        windows = fixture.Windows(proc.pid, desktop)
        stack.callback(release, windows.close, "Could not remove the primary's window event hook")
        membership = None
        if witness is not None:
            result["privateWindowMembership"] = {}
            membership = PrivateMembership(desk, windows, name, desktop, witness, proc, tid,
                                           result["primaryCreation100ns"], api, fixture.TITLE,
                                           result["privateWindowMembership"], **input_options)
        retained = None
        if subject == "retained":
            evidence = result["retainedWindow"] = {}
            retained = RetainedWindow(desk, windows, fixture.TITLE, name, evidence, membership)
            stack.callback(release, retained.close, "Could not remove the retained HWND lifetime hook")
        def log():
            return primary_log.read_text(encoding="utf-8", errors="replace")
        def wait(check_value, message):
            def poll():
                windows.pump()
                recorder.wait_running(proc)
                return check_value()
            return recorder.await_value(poll, message, delay=.02)
        def is_visible():
            return windows.visible(waiting_for_first=True)
        def verify_hwnd(hwnd):
            if windows.visible() != hwnd:
                raise ValueError("The launcher did not find the same visible primary window")
            if membership is not None:
                return membership.verify(hwnd, result["stage"], visible=True)["pid"]
            pid = w.DWORD()
            tid = windows.owner(hwnd, c.byref(pid))
            if pid.value != proc.pid or desk.name(desk.thread_desktop(tid)) != name:
                raise ValueError("The GUI window does not belong to the primary on the selected desktop")
            return pid.value
        def command(data):
            proc.stdin.write(data)
            proc.stdin.flush()

        def read_windows(stage):
            row = snapshot(desk, windows, desktop, witness, tid, result["primaryCreation100ns"])
            row["recentPrimaryEvents"] = windows.events[-16:]
            result["windowReadbacks"][stage] = row
            if witness is not None:
                check_private_snapshot(row, name)

        def observe_at(stage, check_value, message):
            result["stage"] = stage
            try:
                return wait(check_value, message)
            finally:
                read_windows(stage)

        def failure_drain(exc_type, _value, _traceback):
            if exc_type is not None and result["stage"] != "drained":
                drain_after_failure(proc, log, result, windows.pump)
                if native_tray is not None:
                    native_tray.check_drain(proc, job, log(), result)

        stack.push(failure_drain)
        if native_tray is None:
            command(b"T" if tray else b"N")
        else:
            command(b"B")
            native_tray.registration(proc, log, wait, result, no_host=True, private=membership)
        expected = "READY Visible " + ("Available" if tray else "Unavailable")
        observe_at("startup-intent", lambda: expected in log().splitlines(),
                   "The supervisor did not select the expected visible startup")
        result["visibleIntent"] = expected
        if autostart:
            result["fallbackReason"] = "No Shell_TrayWnd on the private non-input desktop"
        observe_at("first-dx12-adapter", lambda: "ADAPTER Dx12 " in log(), "The primary did not initialize its DX12 adapter")
        initial = observe_at("first-visible-window", is_visible, f"No visible primary window on {name}")
        if native_tray is not None:
            native_tray.visible_window(proc, initial, result, "fallbackWindow", private=membership)
        result.update(initialWindow=initial, initialWindowPid=verify_hwnd(initial),
                      initialPrimaryForeground=desk.foreground() == initial)
        if retained is not None:
            retained.first(initial, log, wait)
        result["stage"] = "first-inventories"
        wait(lambda: recorder.idle_complete(log()), "The primary did not finish its two empty inventories")
        worker = recorder.owned_worker(api, proc, primary_log, recorder.await_value)
        # Keep the worker process object alive across close and reopen to exclude PID reuse.
        handle = recorder.checked(api.open(0x100000 | 0x1000, False, worker))
        stack.callback(release_handle, api.close, "CloseHandle(launcher worker)", handle)
        result["primaryJobBefore"] = {}
        result["workerBefore"] = primary_job_members(api, desk, job, proc.pid, worker, exe, console,
                                                     result["primaryJobBefore"])
        if label != "restart":
            result["stage"] = "close"
            if retained is None:
                windows.close_window(initial)
            else:
                retained.close_window()
            observe_at("hidden-before-launch", lambda: (retained.hidden(log()) if retained is not None
                       else windows.visible() is None and "WINDOW_RELEASED " in log()),
                       "The primary window did not close")
            result["hiddenBeforeLaunch"] = True
            if any(line.startswith("WINDOW_FOREGROUND_REQUEST ") for line in log().splitlines()):
                raise ValueError("The GUI requested foreground before the second launch")
            result["stage"] = "secondary"
            second_log = out / (label + "-secondary.log")
            resume_options = {}
            gesture = None
            if keyboard_launcher is not None:
                gesture = stack.enter_context(keyboard_launcher(desk, name, result.setdefault("inputGesture", {})))
                resume_options["before_create"] = gesture.before_create
            if retained is not None:
                clock = bind(api.kernel, "GetTickCount64", c.c_uint64)
                def before_resume(secondary):
                    if gesture is not None:
                        gesture.observe_child(api, secondary, exe)
                    if not retained.hidden(log()):
                        raise ValueError("The closed root appeared before the ordinary secondary could run")
                    result["suspendedSecondary"] = dict(pid=secondary.pid, creation100ns=api.process_identity(int(secondary._handle)),
                                                       events=len(windows.events), tick=clock())
                resume_options["before_resume"] = before_resume
            with second_log.open("xb") as second_stream, ExitStack() as secondary_scope:
                def start_secondary():
                    return secondary_scope.enter_context(child(api, desk, name, exe, [], trial, env, second_stream,
                                                              False, private=private, **input_options, **resume_options))
                second, second_job, _tid = start_secondary() if gesture is None else gesture.launch(start_secondary)
                pump_secondary = windows.pump
                if retained is not None:
                    result["suspendedSecondary"]["resumeReturnedMs"] = clock()
                    def pump_secondary():
                        windows.pump()
                        if "afterTrigger" not in evidence and f"LAUNCHER_OPEN client={second.pid}\n" in log().splitlines(keepends=True):
                            retained.sample_after_trigger("secondaryShow", dict(secondaryPid=second.pid), clock)
                result.update(secondaryArguments=[], secondaryPid=second.pid,
                              secondaryLaunch=dict(api="CreateProcessW", callerPid=os.getpid(),
                                                   source="observer" if gesture is None else "foreground-key-handler"),
                              secondaryCreation100ns=api.process_identity(int(second._handle)))
                result["secondaryExit"] = wait_for_exit(second, pump_secondary, 12)
                result["secondaryJobEmpty"] = api.wait_job_empty(second_job, 3)
                counts = JobAccounting()
                recorder.checked(api.query_job(second_job, 1, c.byref(counts), c.sizeof(counts), None))
                result["secondaryTotalProcesses"] = counts.total
            reopened = observe_at("reopen", is_visible, "The ordinary secondary did not reopen the primary GUI")
            if native_tray is not None:
                native_tray.visible_window(proc, reopened, result, "activatedWindow", private=membership)
            result.update(reopenedWindow=reopened, reopenedWindowPid=verify_hwnd(reopened),
                          primaryForeground=desk.foreground() == reopened)
            if retained is not None:
                retained.opened(reopened, log, wait)
                start = result["suspendedSecondary"]
                if (start["pid"], start["creation100ns"]) != (result["secondaryPid"], result["secondaryCreation100ns"]):
                    raise ValueError("The resumed launcher secondary was not the original suspended process")
                show_ordered = retained.activated_show(start["events"], start["tick"], clock(), "secondaryShow",
                                                       released_by=start["resumeReturnedMs"])
            else:
                wait(lambda: log().count("ADAPTER Dx12 ") >= 2, "The reopened GUI did not acquire its DX12 adapter")
                result["canonicalRecreation"] = dict(initial=initial, reopened=reopened, differentHwnd=initial != reopened,
                                                    ready=[line for line in log().splitlines()
                                                           if line.startswith("GRAPHICS_READY ")],
                                                    events=[row for row in windows.events if row["hwnd"] in (initial, reopened)])
            if not private:
                result["foregroundObservation"] = passive_foreground(desk, windows, reopened, result["primaryForeground"])
            result["primaryJobAfter"] = {}
            result["workerAfter"] = primary_job_members(api, desk, job, proc.pid, worker, exe, console,
                                                        result["primaryJobAfter"])
        try:
            if retained is not None and label != "restart":
                result["keyboardFocus"] = {}
                retained.focus(result["keyboardFocus"], **input_options)
        finally:
            # A negative keyboard observation still permits normal Quit and the independent
            # grant, HWND and job checks. The focus failure propagates with those observations.
            if retained is not None:
                retained.check_visible(log, "beforeQuit")
            result["stage"] = "quit"
            command(b"Q")
            result.update(primaryExit=wait_for_exit(proc, windows.pump, 15), primaryJobEmpty=api.wait_job_empty(job, 4))
            final_log = log()
            if label != "restart":
                qualify(second_log.read_text(encoding="utf-8").splitlines(), final_log.splitlines(), result)
            drained = re.findall(r"^DRAINED passes=(\d+)$", final_log, re.MULTILINE)
            if (result["primaryExit"] or not result["primaryJobEmpty"] or len(drained) != 1
                    or final_log.splitlines().count(f"LAUNCHER_PRIMARY pid={proc.pid}") != 1):
                raise ValueError("The primary and its owned inventory did not drain normally")
            result.update(stage="drained", primaryUiPassesAtQuit=int(drained[0]))
            if native_tray is not None:
                native_tray.check_drain(proc, job, final_log, result)
                native_tray.qualify_quiet_shell(final_log, result, no_host=True)
            if retained is not None:
                retained_graphics(final_log, evidence, before_quit=False)
    if not show_ordered:
        raise ShowOrderUnavailable(evidence["secondaryShow"]["reason"])


def desktop_cases(api, desk, name, desktop, exe, trial, env, out, result, *, native_tray=None, subject="canonical"):
    user = c.WinDLL("user32", use_last_error=True)
    shell = bind(user, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
    create = bind(user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                  c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p)
    destroy = bind(user, "DestroyWindow", w.BOOL, w.HWND)
    if (desk.name(desk.thread_desktop(desk.thread())) != name or desk.receiving_input(desktop) is not False
            or shell("Shell_TrayWnd", None)):
        raise ValueError("The observation thread requires the owned shell-less non-input desktop")
    # The observer owns this enumeration witness across close and reopen.
    anchor = check(create(0x08000080, "STATIC", name, 0x80000000, 0, 0, 1, 1, None, None, None, None), "CreateWindowExW")
    try:
        result.update(shellAbsent=True, desktopReceivedInput=False, paintControl={})
        try:
            paint_control(user, desk, anchor, desktop, name, result["paintControl"])
        except (OSError, ValueError) as exc:
            result["paintControl"]["error"] = str(exc)
        fixture = recorder.load_windows_fixture()
        console = system_console_path(api.kernel)
        uncertain = None
        for label in (("activation", "restart") if native_tray is None else ("activation",)):
            result[label] = {}
            try:
                cycle(api, desk, name, desktop, anchor, fixture, exe, console, trial, env, out, label, result[label],
                      native_tray=native_tray, subject=subject)
            except ShowOrderUnavailable as exc:
                # cycle reports ambiguous ordering only after normal quit and verified job cleanup.
                uncertain = exc
        if "restart" in result and result["activation"]["primaryCreation100ns"] == result["restart"]["primaryCreation100ns"]:
            raise ValueError("A fresh elected primary on the original shell-less desktop was required")
        if desk.receiving_input(desktop) is not False or shell("Shell_TrayWnd", None):
            raise ValueError("The private desktop changed during the launcher trial")
        if uncertain is not None:
            raise uncertain
    finally:
        try:
            if native_tray is not None:
                result["desktopAfter"] = dict(name=desk.name(desktop), receivesInput=desk.receiving_input(desktop),
                                              shellAbsent=not bool(shell("Shell_TrayWnd", None)))
                if result["desktopAfter"]["receivesInput"] is not False:
                    raise CleanupUnconfirmed("The private tray desktop could not be confirmed as non-input at teardown")
        finally:
            release_handle(destroy, "DestroyWindow(private enumeration witness)", anchor)


def private_desktop(desk, select, name, visit, record):
    desktop = None

    def worker():
        nonlocal desktop
        thread = desk.thread()
        original = check(desk.thread_desktop(thread), "GetThreadDesktop(observer)")
        record["originalThreadDesktop"] = desk.name(original)
        if not isinstance(record["originalThreadDesktop"], str):
            raise ValueError("Could not identify the observer's original desktop")
        desktop = check(desk.create(name, None, None, 0, DESKTOP_RIGHTS, None), "CreateDesktopW")
        record.update(threadRestored=False, handleClosed=False)
        try:
            check(select(desktop), "SetThreadDesktop(private observer)")
            visit(desktop)
        finally:
            # CreateDesktop assigns its calling thread. Release all hooks and HWNDs before reattaching it.
            release_handle(select, "SetThreadDesktop(restore observer)", original)
            record["threadRestored"] = desk.name(desk.thread_desktop(thread)) == record["originalThreadDesktop"]
            if not record["threadRestored"]:
                raise CleanupUnconfirmed("The observer did not return to its original desktop handle")

    try:
        with ThreadPoolExecutor(max_workers=1) as observer:
            observer.submit(worker).result()
    finally:
        if desktop:
            release_handle(desk.close, "CloseDesktop(launcher)", desktop)
            record["handleClosed"] = True


def failures(error):
    rows = []
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        row = dict(type=type(error).__name__, message=str(error))
        if (winerror := getattr(error, "winerror", None)) is not None:
            row["win32Error"] = winerror
        if notes := getattr(error, "__notes__", None):
            row["notes"] = notes
        rows.append(row)
        error = error.__cause__ or error.__context__
    return list(reversed(rows))


def foreground_tray_input(path, target, revision, run, result):
    try:
        service = json.loads(path.read_text(encoding="utf-8"))
        tray = service["observations"]["shellIconAcceptedAndRemoved"]
        if (service["target"] != target or service["head"] != revision or service["workflowRun"] != run
                or service["hosted"] is not True or service["probeCompleted"] is not True or not isinstance(tray, bool)):
            raise ValueError("The Shell receipt did not describe a completed observation in this native job")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Normal startup requests a visible window for either tray value. Keep this control independent of the Shell trial.
        result.update(source="synthetic unavailable tray", reason=str(exc), available=False)
        return False
    result.update(source="native Shell receipt", sha256=recorder.sha(path), available=tray)
    return tray


def foreground_case(api, desk, gui, trial, env, out, target, revision, result, *, subject="canonical"):
    desktop = check(desk.thread_desktop(desk.thread()), "GetThreadDesktop(disposable runner)")
    name = desk.name(desktop)
    result["contextBefore"] = desk.context()
    if name != "Default" or not ordinary_console(result["contextBefore"], name):
        raise ValueError("The normal launch requires the disposable runner's existing unlocked input desktop")
    service_path = ROOT / "artifacts/rust/windows-services" / ("native-" + target) / "result.json"
    result.update(trayInput={}, activation={})
    tray = foreground_tray_input(service_path, target, revision, os.environ["GITHUB_RUN_ID"], result["trayInput"])
    try:
        cycle(api, desk, name, desktop, None, recorder.load_windows_fixture(), gui, system_console_path(api.kernel),
              trial, env, out, "foreground", result["activation"], tray=tray, subject=subject)
    finally:
        result["contextAfter"] = desk.context()
        if not ordinary_console(result["contextAfter"], name):
            raise ValueError("The original input desktop could not be confirmed at the end of the normal launch")


@contextmanager
def profile_resources(api, parent, token, result):
    name = "ifw-rw02-" + token
    root = parent / name
    waits = result["directoryDispositionWaits"] = []
    result["cleanupConfirmed"] = False
    observation = None
    try:
        with recorder.owned_directory(api, parent, name, directory_waits=waits) as owned, ExitStack() as stack:
            try:
                yield owned, stack
            except Exception as exc:
                observation = exc
                raise  # Preserve the primary failure while pinned handles and the directory are released.
    except Exception as exc:
        if exc is observation and not CleanupUnconfirmed.in_chain(exc) and not os.path.lexists(root):
            result["cleanupConfirmed"] = True
        raise
    if os.path.lexists(root):
        raise CleanupUnconfirmed("The owned launcher directory still exists after cleanup")
    result["cleanupConfirmed"] = True


def image_identity(api, handle):
    attributes, identity = api.file_info(handle)
    if attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x10 | 0x40):
        raise CleanupUnconfirmed("The staged launcher image is no longer a regular file")
    return identity


def delete_staged_image(api, path, original, record):
    """Retry only the sharing refusal on opening the original staged image for deletion."""
    deadline = time.monotonic() + 5
    record.update(attempts=0, timeoutMs=5000)
    while True:
        record["attempts"] += 1
        try:
            handle = api.path_handle(path, False, delete=True)
        except OSError as error:
            error.add_note(f"CreateFileW(DELETE | FILE_READ_ATTRIBUTES) on staged image 'subject/{path.name}'")
            if getattr(error, "winerror", None) != 32:
                raise
            record.setdefault("firstSharingViolation", failures(error)[-1])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(.05, remaining))
            if time.monotonic() >= deadline:
                raise
            continue
        break
    try:
        if image_identity(api, handle) != original:
            raise CleanupUnconfirmed("The staged launcher image was replaced before disposition")
        try:
            api.delete_handle(handle)
        except OSError as error:
            error.add_note(f"FileDispositionInfoEx on staged image 'subject/{path.name}' (volume {original[0]}, file ID {original[1]})")
            raise
        record["dispositionAccepted"] = True
    finally:
        release_handle(api.close, "CloseHandle(staged image disposition)", handle)


def require_absence(api, path):
    try:
        handle = api.path_handle(path, False)
    except OSError as error:
        if getattr(error, "winerror", None) == 2:  # ERROR_FILE_NOT_FOUND under the pinned parent
            return
        error.add_note(f"CreateFileW after disposition of {path.name!r}")
        raise
    release_handle(api.close, "CloseHandle(staged path readback)", handle)
    raise CleanupUnconfirmed(f"The staged path still exists after disposition: {path.name}")


def directory_identity(api, handle):
    attributes, identity = api.file_info(handle)
    if not attributes & 0x10 or attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x40):
        raise CleanupUnconfirmed("Expected the original regular subject directory")
    return identity


def remove_staged_directory(api, subject, directory_id, runtime_pin, waits):
    # Keep the original file ID live while transferring from the deny-delete pin to the DELETE handle.
    with ExitStack() as handles:
        witness = api.create_file(str(subject), 0x81, 7, None, 3, 0x02200000, None)
        if witness == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        handles.callback(release_handle, api.close, "CloseHandle(staged directory witness)", witness)
        if directory_identity(api, witness) != directory_id:
            raise CleanupUnconfirmed("The staged directory witness differs from its original pin")
        runtime_pin.close()
        final = api.path_handle(subject, True, delete=True)
        handles.callback(release_handle, api.close, "CloseHandle(staged directory disposition)", final)
        if directory_identity(api, final) != directory_id:
            raise CleanupUnconfirmed("The staged directory was replaced before disposition")
        dispose_empty_directory(api, final, "subject", directory_id, waits)
    require_absence(api, subject)


@contextmanager
def staged_images(api, root, built_gui, inventory, result):
    """Keep the original directory and both file identities live through checked removal."""
    if not re.fullmatch(r"ifw-rw02-[0-9a-f]{32}", root.name) or built_gui.name != "native-gui-assessment.exe":
        raise ValueError("Expected the fixed launcher image and private profile")
    subject = root / "subject"
    records = result["stagedImageCleanup"] = {}
    with ExitStack() as resources:
        try:
            subject.mkdir()
            # The running Rust worker opens this directory with FILE_SHARE_READ | FILE_SHARE_WRITE.
            directory = api.path_handle(subject, True)
            directory_lease = resources.enter_context(ExitStack())
            directory_lease.callback(release_handle, api.close, "CloseHandle(staged image directory)", directory)
            directory_id = directory_identity(api, directory)
            result["stagedDirectory"] = dict(volume=directory_id[0], fileId=directory_id[1], removed=False)
            pins = resources.enter_context(ExitStack())
            images = []
            for name, expected in ((built_gui.name, inventory["gui"]), ("ifw-performance-worker.exe", inventory["worker"])):
                path = subject / name
                with built_gui.with_name(name).open("rb") as source, path.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                pin = api.path_handle(path, False)
                pins.callback(release_handle, api.close, "CloseHandle(staged image pin)", pin)
                identity = image_identity(api, pin)
                if recorder.sha(path) != expected:
                    raise CleanupUnconfirmed("The pinned launcher executable differs from its build")
                # This overlap retains the file ID and denies writes even after the deny-delete
                # pin closes. FILE_READ_DATA | FILE_READ_ATTRIBUTES, FILE_SHARE_READ | DELETE.
                witness = api.create_file(str(path), 0x81, 5, None, 3, 0x00200000, None)
                if witness == c.c_void_p(-1).value:
                    raise c.WinError(c.get_last_error())
                lease = resources.enter_context(ExitStack())
                lease.callback(release_handle, api.close, "CloseHandle(staged image witness)", witness)
                if image_identity(api, witness) != identity:
                    raise CleanupUnconfirmed("The staged image witness differs from its original pin")
                record = records[name] = dict(sha256=expected, volume=identity[0], fileId=identity[1],
                                              dispositionAccepted=False, absent=False)
                images.append((path, identity, lease, record))
        except Exception as error:
            raise CleanupUnconfirmed("Could not establish the original staged launcher images") from error
        remove = True
        try:
            yield subject / built_gui.name
        except BaseException as error:
            remove = not CleanupUnconfirmed.in_chain(error)
            raise
        finally:
            if remove:
                try:
                    pins.close()
                    for path, identity, lease, record in images:
                        delete_staged_image(api, path, identity, record)
                        lease.close()
                        require_absence(api, path)
                        record["absent"] = True
                    remove_staged_directory(api, subject, directory_id, directory_lease, result["directoryDispositionWaits"])
                    result["stagedDirectory"]["removed"] = True
                except Exception as error:
                    raise CleanupUnconfirmed("Could not confirm removal of the original staged launcher images") from error


@contextmanager
def staged_profile(result, api, built_gui, inventory, *, token=None):
    token = uuid.uuid4().hex if token is None else token
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Expected a synthetic launcher profile token")
    result["profile"] = token
    with profile_resources(api, Path(os.environ["RUNNER_TEMP"]), token, result) as (root, stack):
        pin_new_marker(stack, api, root / "inventory.owner", token)
        # Keep the deny-delete handle throughout election, delivery and shutdown.
        pid_file = api.create_file(str(root / "launcher.pid"), 0x80000000, 3, None, 1, 0x00200000, None)
        if pid_file == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        stack.callback(release_handle, api.close, "CloseHandle(launcher pid marker)", pid_file)
        gui = stack.enter_context(staged_images(api, root, built_gui, inventory, result))
        trial = root / "rust-1"
        media = trial / "empty"
        media.mkdir(parents=True)
        offline = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        offline.bind(("127.0.0.1", 0))
        env = recorder.environment(trial, "http://127.0.0.1:" + str(offline.getsockname()[1]), True, media, token)
        for key in tuple(env):
            if key.startswith("IFW_QA_WINDOWS_"):
                del env[key]
        env.update(IFW_QA_WINDOWS_LAUNCHER="1", IFW_QA_LAUNCHER_SID=recorder.sid())
        result["stagedProfile"] = dict(gui=inventory["gui"], worker=inventory["worker"], trial=trial.name,
                                       configSha256=recorder.sha(trial / "config.yaml"), inventoryToken=token)
        yield gui, trial, env


def run_profile(case, result, api, desk, built_gui, inventory, out, target, revision, *, subject="canonical"):
    with staged_profile(result, api, built_gui, inventory) as (gui, trial, env):
        if case == "shellLess":
            name = "IfwQa_Launcher_" + result["profile"]
            change_thread = bind(c.WinDLL("user32", use_last_error=True), "SetThreadDesktop", w.BOOL, w.HANDLE)
            result["desktopCleanup"] = {}
            private_desktop(desk, change_thread, name,
                            lambda desktop: desktop_cases(api, desk, name, desktop, gui, trial, env, out, result,
                                                          subject=subject),
                            result["desktopCleanup"])
        else:
            foreground_case(api, desk, gui, trial, env, out, target, revision, result, subject=subject)


def run_cases(visit, result):
    first = None
    # Observe the original input desktop before creating any private desktop or its processes.
    for name in ("foreground", "shellLess"):
        record = result[name] = {"status": "running", "cleanupConfirmed": False}
        try:
            visit(name, record)
            if not record["cleanupConfirmed"]:
                raise CleanupUnconfirmed("Could not confirm cleanup of the launcher trial")
        except Exception as exc:
            chain = failures(exc)
            record.update(status="failed", error=chain[0]["message"], failures=chain)
            if not record["cleanupConfirmed"] or CleanupUnconfirmed.in_chain(exc):
                if name == "foreground":
                    result["shellLess"] = dict(status="not-run",
                                               reason="Original input desktop launcher cleanup was not confirmed")
                if CleanupUnconfirmed.in_chain(exc):
                    raise
                raise CleanupUnconfirmed(f"Cleanup of the {name} launcher trial was not confirmed") from exc
            if isinstance(exc, ShowOrderUnavailable):
                record["status"] = "unavailable"
            if first is None or (isinstance(first, ShowOrderUnavailable) and not isinstance(exc, ShowOrderUnavailable)):
                first = exc
        else:
            record["status"] = "passed"
    return first


@contextmanager
def native_subject(target, out, result, extra_inputs=(), *, subject="canonical"):
    if (not recorder.hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the dedicated disposable native rewrite runner")
    artifacts = ROOT / "artifacts/rust"
    exe = artifacts / "gui-build/release/native-gui-assessment.exe"
    receipt_path = artifacts / "gui-native" / target / "build.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    profile_path = ROOT / "rust/audit/gui-profile.json"
    profile = json.loads(profile_path.read_bytes())
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    gui_source = QA / "gui"
    lifecycle = ROOT / "rust/crates/desktop-lifecycle"
    required = {path.relative_to(ROOT).as_posix() for path in
                [gui_source / "Cargo.toml", *sorted((gui_source / "src").glob("*.rs")),
                 gui_source / "src/tray-icon.argb", ROOT / "rust/Cargo.toml",
                 lifecycle / "Cargo.toml", lifecycle / "src/lib.rs"]}
    if (revision != os.environ["GITHUB_SHA"] or receipt["source"] != revision or receipt["target"] != target
            or recorder.sha(exe) != receipt["binarySha256"]
            or recorder.pe_machine(exe) != TARGETS[target] or receipt["graphSha256"] != profile["targetReportSha256"][target]
            or receipt["lockSha256"] != profile["lockSha256"] or recorder.sha(gui_source / "Cargo.lock") != receipt["lockSha256"]
            or receipt["sourceProfileSha256"] != recorder.sha(ROOT / "rust/audit/gui-text-inputs.json")
            or receipt["sourceReconstructionSha256"] != recorder.sha(gui_source / "source_profile.py")
            or required != set(receipt["compilerSources"])
            or any(recorder.sha(ROOT / path) != digest for path, digest in receipt["compilerSources"].items())):
        raise ValueError("The ordinary native GUI and its reviewed inputs must match the checkout")
    if subject not in SUBJECTS:
        raise ValueError("Unknown native GUI subject")
    selected_receipt, selected_binary, lock = recorder.sha(receipt_path), receipt["binarySha256"], receipt["lockSha256"]
    if subject == "retained":
        api, exe, paired = retained_subject.select(target, exe, receipt, receipt_path.with_name("graph.json"), recorder.sha)
        result["pairedBuild"] = paired
        selected_receipt, selected_binary, lock = paired["buildReceipt"], paired["binary"], paired["lock"]
    else:
        api = recorder.Win32()
    desk = Desktop()
    if api.machine(-1) != (TARGETS[target], TARGETS[target]):
        raise ValueError("A native target-matching Windows observer is required")
    result.update(subject=subject, revision=revision, target=target, run=os.environ["GITHUB_RUN_ID"],
                  attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  buildReceipt=selected_receipt, gui=selected_binary, graph=receipt["graphSha256"], lock=lock,
                  guiProfile=recorder.sha(profile_path), textProfile=receipt["sourceProfileSha256"],
                  workerProfile=recorder.sha(QA / "performance/worker-inputs.json"),
                  observerInputs={path.relative_to(ROOT).as_posix(): recorder.sha(path) for path in
                                  (Path(__file__).resolve(), HERE / "named_process.py", HERE / "window_readback.py",
                                   HERE / "retained_subject.py", HERE / "retained_window.py", LIFETIME,
                                   retained_subject.WARM / "inputs.py",
                                   QA / "observe-windows-gui.py", QA / "windows-desktop/win32.py", QA / "windows-desktop/job.py",
                                   QA / "windows-performance/native.py", QA / "windows-performance/run.py",
                                   QA / "windows-performance/build.py", *extra_inputs)})
    with profile_resources(api, Path(os.environ["RUNNER_TEMP"]), uuid.uuid4().hex, result) as (build, stack):
        gui, _, inventory = recorder.build_subject(build, out, exe, target, recorder.pe_machine)
        if inventory["gui"] != result["gui"]:
            raise ValueError("The staged native GUI differs from the selected build")
        result["peMachines"] = {}
        for image in (gui, gui.with_name("ifw-performance-worker.exe")):
            stack.enter_context(recorder.pin_path(api, image, False))
            result["peMachines"][image.name] = recorder.pe_machine(image)
            if result["peMachines"][image.name] != TARGETS[target]:
                raise ValueError("Both pinned executables must match the native runner architecture")
        result["inventory"] = inventory
        yield api, desk, gui, inventory, revision


def run(target, out, result, *, subject="canonical"):
    with native_subject(target, out, result, subject=subject) as (api, desk, gui, inventory, revision):
        first = run_cases(lambda case, state: run_profile(case, state, api, desk, gui, inventory, out, target, revision,
                                                         subject=subject),
                          result)
        if first is not None:
            raise first


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--subject", choices=SUBJECTS, default="canonical")
    options = parser.parse_args()
    directory = "windows-launcher-retained" if options.subject == "retained" else "windows-launcher"
    output = ROOT / "artifacts/rust" / directory / options.target
    output.mkdir(exist_ok=False, parents=True)
    results = {"subject": options.subject}
    try:
        run(options.target, output, results, subject=options.subject)
    except Exception as exc:
        chain = failures(exc)
        if isinstance(exc, ShowOrderUnavailable):
            results.update(status="unavailable", error=chain[0]["message"], failures=chain)
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        results.update(status="failed", error=chain[0]["message"], failures=chain)
        raise
    else:
        results["status"] = "passed"
    finally:
        results["evidenceFiles"] = {path.name: recorder.sha(path) for path in sorted(output.iterdir()) if path.is_file()}
        recorder.write(output / "result.json", results)
