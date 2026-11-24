"""Observe live Windows contrast colors on the ordinary Rust filename label."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import runpy
import sys
import time
import traceback
import uuid

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
sys.path[:0] = [str(HERE), str(QA / "windows-text"), str(QA / "windows-desktop"),
                str(QA / "windows-performance"), str(QA)]
from native import Win32, pin_path
from storage.evidence import sha256, write_json
from job import run_worker
from win32 import Desktop, GA_ROOT, READ_OBJECTS, bind, check, ordinary_console, same_name, unlocked_console
from windows_colors import SystemColors, contrast_cycle, label_bitmap, label_colors
from windows_observer import private_gui_environment, private_profile, select_powershell
from worker import hosted, named_desktop, powershell

TEXT = runpy.run_path(str(QA / "windows-text/run.py"))


def job_guard():
    if (not hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"
            or not re.fullmatch("[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
            or not os.getenv("GITHUB_RUN_ID", "").isdecimal() or not os.getenv("GITHUB_RUN_ATTEMPT", "").isdecimal()):
        raise ValueError("Use the dedicated Windows rewrite job for the temporary contrast setting")


def verify_frames(output, phase, record, pid, hwnd, state):
    if (record.get("status"), record.get("phase"), record.get("pid"), record.get("hwnd"),
            record.get("label")) != ("observed", phase, pid, hwnd, "Dateiname"):
        raise ValueError("The two label samples must belong to the original Rust HWND")
    rect = record["rect"]
    if len(rect) != 4 or any(type(n) is not int for n in rect) or len(record["samples"]) != 2:
        raise ValueError("Missing the physical rectangle or the two repeat samples")
    rasters = []
    for i, item in enumerate(record["samples"], start=1):
        expected = f"{phase}.json.{i}.bmp"
        path = output / expected
        if item["file"] != expected or sha256(path) != item["sha256"]:
            raise ValueError("The original label frame differs from its receipt")
        width, height, colors, raster = label_bitmap(path)
        rasters.append(raster)
        if [width, height] != rect[2:]:
            raise ValueError("The captured bitmap differs from its physical UIA label bounds")
        metrics = label_colors(colors, state)
    if rasters[0] != rasters[1]:
        raise ValueError("Two successive samples of the static label have different pixels")
    return {"dimensions": rect[2:], "rasterSha256": rasters[0], **metrics}


def announce(folder, name, token, **fields):
    temp = folder / (name + ".tmp")
    final = folder / (name + ".json")
    if final.exists():
        raise ValueError("Duplicate Windows contrast phase " + name)
    write_json(temp, {"token": token, **fields})
    temp.replace(final)


def message(folder, name, token, worker=None, timeout=85):
    deadline = time.monotonic() + timeout
    while not (folder / (name + ".json")).is_file():
        if (folder / "stop.json").exists():
            raise RuntimeError("The contrast supervisor ended the observation")
        if worker is not None and worker.done():
            raise RuntimeError(f"The native capture worker ended with {worker.result()} before {name}")
        if time.monotonic() >= deadline:
            raise TimeoutError("Waiting for the contrast phase " + name)
        time.sleep(.1)
    data = TEXT["read"](folder / (name + ".json"))
    if not isinstance(data, dict) or data.pop("token", None) != token:
        raise ValueError("The contrast phase belongs to another native trial")
    return data


def require_live_window(api, session, name, pid, hwnd):
    def reject(operation, expected, observed):
        raise ValueError(f"The original visible Rust root HWND {hwnd} of PID {pid} in session {session} "
                         f"on {name!r} failed {operation} (expected {expected!r}, observed {observed!r})")

    def desktop_name(value):
        # Keep the private fixture name, the original Default desktop and native error values.
        if isinstance(value, str) and not (same_name(value, name) or same_name(value, "Default")):
            return "<different desktop>"
        return value

    def nonzero(operation, native, *args):
        c.set_last_error(0)
        value = native(*args)
        if not value:
            reject(operation, "nonzero", {"returned": value, "win32LastError": c.get_last_error()})
        return value

    context = api.context()
    if context["session"] != session:
        reject("observer session", session, context["session"])
    if not unlocked_console(context):
        fields = {key: context[key] for key in ("windowStation", "stationVisible", "session", "activeConsoleSession", "wts")}
        if isinstance(fields["windowStation"], str) and not same_name(fields["windowStation"], "WinSta0"):
            fields["windowStation"] = "<different window station>"
        reject("unlocked_console", "visible WinSta0 in its active unlocked console session", fields)
    if not same_name(context["inputDesktop"], name):
        reject("input desktop name", name, desktop_name(context["inputDesktop"]))
    if context["inputObjectReceivesInput"] is not True:
        reject("UOI_IO on the input desktop", True, context["inputObjectReceivesInput"])
    subject_session = api.pid_session(pid)
    if subject_session != session:
        reject("ProcessIdToSessionId", session, subject_session)
    owner = w.DWORD()
    thread = nonzero("GetWindowThreadProcessId", api.owner, hwnd, c.byref(owner))
    if owner.value != pid:
        reject("GetWindowThreadProcessId owner PID", pid, owner.value)
    handle = nonzero(f"GetThreadDesktop for subject thread {thread}", api.thread_desktop, thread)
    c.set_last_error(0)
    thread_name = api.name(handle)
    if not same_name(thread_name, name):
        reject("GetUserObjectInformationW(UOI_NAME) on the subject thread desktop", name, desktop_name(thread_name))
    if not api.visible(hwnd):
        reject("IsWindowVisible", True, False)
    if api.iconic(hwnd):
        reject("IsIconic", False, True)
    ancestor = nonzero("GetAncestor(GA_ROOT)", api.ancestor, hwnd, GA_ROOT)
    if ancestor != hwnd:
        reject("GetAncestor(GA_ROOT)", hwnd, ancestor)


def on_subject_desktop(api, name, cycle):
    if not named_desktop(name):
        raise ValueError("The contrast publisher requires the test-owned input desktop")
    handle = check(api.open_named(name, 0, False, READ_OBJECTS), "OpenDesktopW(contrast publisher)")
    try:
        def publish():
            attach = bind(c.WinDLL("user32", use_last_error=True), "SetThreadDesktop", w.BOOL, w.HANDLE)
            check(attach(handle), "SetThreadDesktop(contrast publisher)")
            if not ordinary_console(api.context(), name):
                raise RuntimeError("The contrast publisher did not join the owned input desktop")
            return cycle()
        # Both setting broadcasts originate on the subject's desktop. This short-lived
        # supervisor thread exits before its handle closes, including after capture failure.
        with ThreadPoolExecutor(max_workers=1) as publisher:
            return publisher.submit(publish).result()
    finally:
        check(api.close(handle), "CloseDesktop(contrast publisher)")


def capture_job(target, desktop, report):
    return run_worker(Path(__file__).resolve(), [target, "--capture-worker"],
                      desktop, ROOT, report, timeout_seconds=300)


def exercise(api, context, pid, hwnd, env, ps, output, report):
    name = context["threadDesktop"]
    control = output / "control"
    setup = TEXT["read"](control / "session.json")
    report["hwnd"], report["pid"] = hwnd, pid
    if (setup["session"] != context["session"] or setup["source"] != report["build"]["source"]
            or setup["target"] != report["target"] or setup["run"] != os.environ["GITHUB_RUN_ID"]
            or setup["attempt"] != os.environ["GITHUB_RUN_ATTEMPT"]
            or not named_desktop(name)):
        raise ValueError("The capture worker does not belong to its contrast supervisor")
    def window_guard():
        require_live_window(api, context["session"], name, pid, hwnd)
    window_guard()
    token = setup["token"]
    announce(control, "ready", token, pid=pid, hwnd=hwnd, build=report["build"], desktop=name)
    system = SystemColors(bind, check)
    for phase in ("original", "changed", "restored"):
        request = message(control, "request-" + phase, token)
        state = system.read()
        if vars(state) != request["state"]:
            raise ValueError("The worker and supervisor see different Windows accessibility settings")
        window_guard()
        path = output / (phase + ".json")
        args = ["-SubjectId", pid, "-WindowHandle", hwnd, "-Phase", phase, "-OutputFile", path]
        code = powershell(ps, HERE / "windows-label.ps1", args, env, output, output / (phase + ".log"), 60)
        observed = TEXT["read"](path) if path.is_file() else {}
        if code:
            raise RuntimeError(observed.get("error") or f"The {phase} label observer exited {code}")
        window_guard()
        if state != system.read():
            raise ValueError("The Windows palette changed while the worker observed the label")
        signature = verify_frames(output, phase, observed, pid, hwnd, state)
        announce(control, "observed-" + phase, token, pid=pid, hwnd=hwnd, frame=signature, state=vars(state))


def inputs(folder):
    files = [*TEXT["observer_paths"](), Path(__file__).resolve(), HERE / "windows_colors.py",
             HERE / "windows-label.ps1", HERE / "test_windows_colors.py", QA / "windows-services/service_sources.py",
             QA / "windows-performance/native.py", ROOT / ".gitattributes"]
    files += [ROOT / name for name in TEXT["read"](folder / "build.json")["compilerSources"]]
    verify = runpy.run_path(str(QA / "windows-services/service_sources.py"))["verify_checkout"]
    return verify(ROOT, files, os.environ["GITHUB_SHA"])


def capture_profile(output):
    name = TEXT["read"](output / "control/session.json")["profile"]
    if not isinstance(name, str) or not re.fullmatch(r"profile-[a-zA-Z0-9_-]+", name):
        raise ValueError("The capture worker needs the supervisor's private profile")
    path = output.resolve(strict=True) / name
    if path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError("The capture profile must be the supervisor's original directory")
    return path


def capture_worker(target, folder, output):
    job_guard()
    report = {"status": "failed", "target": target}
    try:
        with ExitStack() as stack:
            binary = TEXT["DESKTOP"]["GUI_BINARY"].resolve(strict=True)
            stack.enter_context(pin_path(Win32(), binary, False))
            report["build"] = TEXT["check_build"](target, binary, folder)
            report["inputs"] = inputs(folder)
            profile = capture_profile(output)
            env = private_gui_environment(profile)
            ps, report["observerHosts"] = select_powershell(profile, "accessibility", env=env)
            if not ps:
                raise RuntimeError("The native UI Automation observer could not start")
            TEXT["observe"](binary, output, env, ps, report, exercise=exercise)
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    write_json(output / "worker.json", report)
    return int(report["status"] != "passed")


def supervise(target, folder, output):
    job_guard()
    output.mkdir(exist_ok=False)
    control = output / "control"
    control.mkdir()
    desk, processes = Desktop(), Win32()
    token = uuid.uuid4().hex
    report = dict(target=target, run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  source=os.environ["GITHUB_SHA"], status="failed")
    try:
        report["inputs"] = inputs(folder)
        context = desk.context()
        if not ordinary_console(context, "Default"):
            raise RuntimeError("Start the contrast supervisor on the active unlocked disposable runner")
        session = context["session"]
        placement = report["placement"] = {}
        selected = TEXT["DESKTOP"]["named_input_desktop"](desk, placement)
        with (private_profile(output, "profile-", report) as profile, selected as desktop,
              ThreadPoolExecutor(max_workers=1) as pool, ExitStack() as stack):
            announce(control, "session", token, session=session, source=report["source"], target=target,
                     run=report["run"], attempt=report["attempt"], profile=profile.name)
            job = report["captureJob"] = {}
            placement["selected"] = desktop
            worker = pool.submit(capture_job, target, desktop, job)
            try:
                ready = report["ready"] = message(control, "ready", token, worker, timeout=100)
                pid, hwnd = ready["pid"], ready["hwnd"]
                exe = TEXT["DESKTOP"]["GUI_BINARY"].resolve(strict=True)
                if (type(pid) is not int or pid <= 0 or type(hwnd) is not int or hwnd <= 0
                        or desk.pid_session(pid) != session or not same_name(ready["desktop"], desktop)):
                    raise ValueError("The observed GUI does not belong to the supervisor's session")
                handle = check(processes.open(0x101000, False, pid), "OpenProcess(contrast subject)")
                def close_image():
                    check(processes.close(handle), "CloseHandle(contrast subject)")
                stack.callback(close_image)
                image, size = c.create_unicode_buffer(32768), w.DWORD(32768)
                check(desk.image(handle, 0, image, c.byref(size)), "QueryFullProcessImageNameW")
                report["creation100ns"] = processes.process_identity(handle)
                if Path(image.value) != exe or ready["build"] != TEXT["check_build"](target, exe, folder):
                    raise ValueError("The observed process differs from the pinned native executable")
                alive = bind(processes.kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
                def session_guard():
                    job_guard()
                    if desk.pid_session(os.getpid()) != session:
                        raise ValueError("The contrast supervisor left its original logon session")
                def window_guard():
                    if worker.done() or alive(handle, 0) != 258:
                        raise RuntimeError("The capture worker or original Rust process exited")
                    require_live_window(desk, session, ready["desktop"], pid, hwnd)
                def capture(phase, state):
                    announce(control, "request-" + phase, token, state=vars(state))
                    ack = message(control, "observed-" + phase, token, worker)
                    original = verify_frames(output, phase, TEXT["read"](output / (phase + ".json")), pid, hwnd, state)
                    if ack != {"pid": pid, "hwnd": hwnd, "frame": original, "state": vars(state)}:
                        raise ValueError("The capture receipt differs from the native files or supervisor's palette")
                    return original
                def change_and_restore():
                    contrast_cycle(SystemColors(bind, check), session_guard, window_guard, capture, report)
                on_subject_desktop(desk, desktop, change_and_restore)
            finally:
                announce(control, "stop", token)
        child = TEXT["read"](output / "worker.json")
        if (worker.result() or not job.get("jobClosed") or child.get("status") != "passed"
                or not child.get("drained") or not report["profileRemoved"] or not report["restoreVerified"]):
            raise RuntimeError("The native capture, system restoration or process cleanup is unconfirmed")
        report["status"] = "passed"
    except Exception:
        report["error"] = traceback.format_exc()
    write_json(output / "result.json", report)
    files = sorted(p for p in output.rglob("*") if p.is_file() and p.parent in (output, control))
    (output / "evidence.sha256").write_text("".join(f"{sha256(p)}  {p.relative_to(output).as_posix()}\n" for p in files),
                                            encoding="utf-8", newline="\n")
    print(report.get("error") or report["status"])
    return int(report["status"] != "passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TEXT["TARGETS"]))
    parser.add_argument("--capture-worker", action="store_true", help="read the owned label on the chosen input desktop")
    args = parser.parse_args()
    build_dir = ROOT / "artifacts/rust/gui-native" / args.target
    method = capture_worker if args.capture_worker else supervise
    sys.exit(method(args.target, build_dir, build_dir / "windows-contrast"))
