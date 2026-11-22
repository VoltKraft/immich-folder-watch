"""Observe the integrated launcher's real notification icon on two disposable Windows desktops."""
import argparse
from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import math
from pathlib import Path
import re
import sys

import observe as launcher
from observe import CleanupUnconfirmed, bind, check, ordinary_console, recorder

PROVIDER = launcher.HERE / "tray_provider.ps1"
RECORDS = {
    "TRAY_REGISTER": r"phase=(initial|retry|recreate) pid=(\d+) hwnd=(\d+) id=(\d+) token=([0-9a-f]{32}) added=([01]) version4=([01])",
    "TRAY_ICON": r"phase=(initial|changed|sample) pid=(\d+) hwnd=(\d+) id=(\d+) rgb=([0-9a-f]{6}) rect=(none|-?\d+,-?\d+,-?\d+,-?\d+) ok=([01])",
    "TRAY_CALLBACK": r"pid=(\d+) hwnd=(\d+) id=(\d+) code=(\d+) ordinal=(\d+) queued_ms=(none|\d+) dispatch_ms=(\d+)",
    "TRAY_OPEN": r"pid=(\d+) ordinal=(\d+)",
    "TRAY_CLEANUP": r"pid=(\d+) hwnd=(\d+) id=(\d+) registered=([01]) removed=([01])",
}


class Unavailable(Exception):
    """The desktop or Shell could not expose the requested native observation."""


class IconIdentifier(c.Structure):
    _fields_ = [("size", w.DWORD), ("owner", w.HWND), ("id", w.UINT), ("guid", c.c_uint32 * 4)]


class MonitorInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("monitor", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]


def monitor_work_area(hwnd):
    user = c.WinDLL("user32", use_last_error=True)
    from_window = bind(user, "MonitorFromWindow", w.HANDLE, w.HWND, w.DWORD)
    info = bind(user, "GetMonitorInfoW", w.BOOL, w.HANDLE, c.POINTER(MonitorInfo))
    handle = from_window(hwnd, 0)  # MONITOR_DEFAULTTONULL
    if not handle:
        return None
    monitor = MonitorInfo(size=c.sizeof(MonitorInfo))
    check(info(handle, c.byref(monitor)), "GetMonitorInfoW(visible primary)")
    r = monitor.work
    return [r.left, r.top, r.right, r.bottom]


def shell_rect(hwnd):
    if c.sizeof(IconIdentifier) != 40:
        raise ValueError("Expected the native 64-bit NOTIFYICONIDENTIFIER layout")
    get_rect = bind(c.WinDLL("shell32"), "Shell_NotifyIconGetRect", w.LONG, c.POINTER(IconIdentifier), c.POINTER(w.RECT))
    key, bounds = IconIdentifier(size=40, owner=hwnd, id=23), w.RECT()
    hr = get_rect(c.byref(key), c.byref(bounds))
    return dict(hresult=hr, rect=None if hr != 0 else [bounds.left, bounds.top, bounds.right, bounds.bottom])


def records(log, name):
    values = []
    for raw in log.splitlines(keepends=True):
        if raw.startswith(name + " ") and raw.endswith("\n"):
            line = raw.rstrip("\r\n")
            match = re.fullmatch(name + " " + RECORDS[name], line)
            if match is None:
                raise ValueError(f"Malformed native {name} record")
            values.append(match.groups())
    return values


def one(rows, name):
    if len(rows) != 1:
        raise ValueError(f"Expected one {name} record, received {len(rows)}")
    return rows[0]


def marker_colors(token):
    first = [base + (int(token[n:n + 2], 16) & 63) for n, base in ((0, 24), (2, 164), (4, 48))]
    return bytes(first).hex(), bytes(255 - value for value in first).hex()


def icon(log, phase, key, rgb):
    rows = [row for row in records(log, "TRAY_ICON") if row[0] == phase]
    if not rows:
        return None
    _, pid, hwnd, ident, value, rect, ok = one(rows, phase)
    if (pid, hwnd, ident) != key:
        raise ValueError("The GUI reported another notification icon")
    if ok == "0" or rect == "none":
        raise Unavailable(f"The Shell did not supply the {phase} icon or its native rectangle")
    if value != rgb:
        raise ValueError("The GUI did not publish the requested token-derived marker")
    return [int(n) for n in rect.split(",")]


def delivery(log, key, start, observed):
    callbacks, opened = records(log, "TRAY_CALLBACK"), records(log, "TRAY_OPEN")
    if not callbacks or not opened:
        return None
    pid, hwnd, ident, code, ordinal, queued, dispatch = one(callbacks, "Shell callback")
    if ((pid, hwnd, ident) != key or int(code) not in (0x203, 0x400, 0x401)
            or int(ordinal) != 1 or one(opened, "GUI Open") != (pid, ordinal)):
        raise ValueError("The v4 callback and the primary Open did not identify the original icon and ordinal")
    if not (0 <= start <= int(dispatch) <= observed and observed - start <= 35_000):
        raise ValueError("The native callback dispatch was outside the provider observation")
    if start == int(dispatch):
        raise Unavailable("The callback and invocation shared a coarse Windows tick and could not be ordered")
    if queued != "none":
        queue_offset = (int(queued) - start) & 0xffffffff
        if int(queued) > 0xffffffff or queue_offset > int(dispatch) - start:
            raise ValueError("The callback was queued outside the provider observation")
        if queue_offset == 0:
            raise Unavailable("The callback queue time could not be ordered after the provider invocation")
    return dict(pid=int(pid), hwnd=int(hwnd), iconId=int(ident), code=int(code), ordinal=int(ordinal),
                queuedMs=None if queued == "none" else int(queued), dispatchMs=int(dispatch), observedMs=observed)


class NativeTray:
    def __init__(self, api, desk, name, token):
        self.api, self.desk, self.name, self.token = api, desk, name, token

    def registration(self, proc, log, wait, result, *, no_host):
        entries = wait(lambda: records(log(), "TRAY_REGISTER"), "No initial native registration outcome")
        initial = one([row for row in entries if row[0] == "initial"], "initial registration")
        _, pid, hwnd, ident, token, added, v4 = initial
        key = pid, hwnd, ident
        if (int(pid) != proc.pid or int(hwnd) <= 0 or ident != "23" or token != self.token
                or (v4 == "1" and added != "1")):
            raise ValueError("The native registration did not identify the original primary and profile")
        raw = log().splitlines()
        if (raw.count("gui_tray.initial.add=" + ("true" if added == "1" else "false")) != 1
                or (added == "1" and raw.count("gui_tray.initial.version4=" + ("true" if v4 == "1" else "false")) != 1)):
            raise ValueError("Missing the underlying Shell_NotifyIcon registration outcome")
        window = self.desk.window(int(hwnd))
        actual_desktop = self.desk.name(self.desk.thread_desktop(window["tid"])) if window else None
        result["registration"] = dict(pid=int(pid), hwnd=int(hwnd), iconId=int(ident), token=token,
                                      added=added == "1", version4=v4 == "1", receiver=window, desktop=actual_desktop)
        if (not window or window["pid"] != proc.pid or window["class"] != "IFW RW02 synthetic tray receiver"
                or actual_desktop != self.name):
            raise ValueError("The receiver HWND did not belong to the retained primary on the selected desktop")
        independent = result["registration"]["shellReadback"] = shell_rect(int(hwnd))
        if no_host and ((added, v4) != ("0", "0") or independent["hresult"] >= 0):
            raise Unavailable("The Shell accepted registration on the private desktop without a taskbar")
        if not no_host and (added, v4) != ("1", "1"):
            raise Unavailable("The input desktop did not accept the integrated icon's first v4 registration")
        return key

    def visible_window(self, proc, hwnd, result, stage):
        window = self.desk.window(hwnd)
        cloaked = w.DWORD()
        if not window or window["pid"] != proc.pid or self.desk.name(self.desk.thread_desktop(window["tid"])) != self.name:
            raise ValueError("The visible GUI window did not belong to the original primary on its desktop")
        hr = self.desk.attribute(hwnd, 14, c.byref(cloaked), c.sizeof(cloaked))
        window.update(minimized=bool(self.desk.iconic(hwnd)), cloakHresult=hr,
                      cloaked=cloaked.value if hr == 0 else None)
        result[stage] = window
        if self.name == "Default" and window["cloaked"] != 0:
            raise Unavailable("DWM did not confirm an uncloaked GUI window on the input desktop")
        rect = window["rect"]
        if (not self.desk.visible(hwnd) or window["minimized"]
                or not isinstance(rect, list) or rect[0] >= rect[2] or rect[1] >= rect[3]):
            raise ValueError("The native launcher window did not have a visible, non-minimized surface")
        if self.name == "Default":
            work = window["monitorWorkArea"] = monitor_work_area(hwnd)
            if work is None:
                raise ValueError("The activated GUI window did not intersect a real monitor")
            overlap = window["visibleWorkArea"] = [max(rect[0], work[0]), max(rect[1], work[1]),
                                                   min(rect[2], work[2]), min(rect[3], work[3])]
            if overlap[0] >= overlap[2] or overlap[1] >= overlap[3]:
                raise ValueError("The activated GUI window did not intersect the monitor work area")

    def check_drain(self, proc, job, log, result):
        """Retain normal app exit, job accounting and exact icon removal even on observation failure."""
        rows = records(log, "TRAY_REGISTER")
        cleanup = records(log, "TRAY_CLEANUP")
        report = result["nativeShutdown"] = dict(registrations=rows, cleanup=cleanup, exit=proc.poll(),
                                                 jobEmpty=self.api.wait_job_empty(job, 4))
        passes = re.findall(r"^DRAINED passes=(\d+)$", log, re.M)
        if (report["exit"] != 0 or not report["jobEmpty"] or len(passes) != 1
                or log.splitlines().count(f"LAUNCHER_PRIMARY pid={proc.pid}") != 1):
            raise CleanupUnconfirmed("The integrated primary did not quit and drain its inventory normally")
        report["uiPasses"] = int(passes[0])
        initial = one([row for row in rows if row[0] == "initial"], "initial registration")
        key = initial[1:4]
        if (key[0] != str(proc.pid) or int(key[1]) <= 0 or key[2] != "23"
                or any(row[1:4] != key or row[4] != self.token for row in rows)
                or len(cleanup) != 1 or cleanup[0][:3] != key):
            raise CleanupUnconfirmed("The retained primary's real tray cleanup could not be identified")
        registered, removed = cleanup[0][3:]
        if (registered != removed or (any(row[-1] == "1" for row in rows) and registered != "1")
                or (all(row[-2] == "0" for row in rows) and registered != "0")
                or (registered == "1" and log.splitlines().count("gui_tray.shutdown=true") != 1)
                or (any(row[-2:] == ("1", "0") for row in rows)
                    and "gui_tray.incompatible_version=true" not in log.splitlines())):
            raise CleanupUnconfirmed("The Shell did not confirm removal of the integrated icon")
        owner = w.DWORD()
        after_tid = self.desk.owner(int(key[1]), c.byref(owner))
        report["receiverAfterExit"] = dict(tid=after_tid, pid=owner.value)
        if after_tid:
            # A recycled HWND belongs to another process. Do not query that process's icon.
            report["shellAfterExit"] = None
        else:
            report["shellAfterExit"] = shell_rect(int(key[1]))
            if report["shellAfterExit"]["hresult"] >= 0:
                raise CleanupUnconfirmed("The Shell did not confirm absence of the original icon after quit")
        report["stableRegistration"] = len(rows) == 1 and "TRAY_TASKBAR " not in log and "TRAY_HOST " not in log

    @staticmethod
    def qualify_quiet_shell(log, result, *, no_host):
        if not result["nativeShutdown"]["stableRegistration"]:
            raise Unavailable("The taskbar changed or the subject repeated registration during the trial")
        if result["nativeShutdown"]["shellAfterExit"] is None:
            raise Unavailable("The receiver HWND was reused before post-quit readback")
        if not no_host and not result["nativeShutdown"]["uiPasses"]:
            raise ValueError("The GUI completed no UI pass after opening from background startup")
        if no_host and (records(log, "TRAY_CALLBACK") or records(log, "TRAY_OPEN")):
            raise ValueError("Unexpected notification-area activation on the shell-less desktop")


def command(process, data):
    process.stdin.write(data)
    process.stdin.flush()


def provider_event(path, stage):
    found = []
    for line in path.read_bytes().splitlines(keepends=True):
        if line.startswith(b"IFW_PROVIDER ") and line.endswith(b"\n"):
            event = json.loads(line[len(b"IFW_PROVIDER "):])
            if event["stage"] == "unavailable":
                raise Unavailable(event["reason"])
            if event["stage"] == "failed":
                raise RuntimeError(event["reason"])
            if event["stage"] == stage:
                found.append(event)
    return one(found, stage) if found else None


@contextmanager
def provider(api, desk, trial, env, out, key, creation, result):
    # The native Windows PowerShell installation supplies the .NET Framework UIA client.
    host = Path(launcher.system_console_path(api.kernel)).parent / "WindowsPowerShell/v1.0/powershell.exe"
    if not host.is_file():
        raise Unavailable("The native Windows PowerShell UI Automation host is unavailable")
    log = out / "provider.log"
    args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
            "-File", str(PROVIDER), "-Token", env["IFW_QA_INVENTORY_TOKEN"],
            "-PrimaryId", key[0], "-Receiver", key[1], "-Creation", str(creation)]
    with log.open("xb") as stream, launcher.child(api, desk, "Default", host, args, trial, env, stream, True,
                                                  private=False) as (proc, job, _):
        result.update(pid=proc.pid, creation100ns=api.process_identity(int(proc._handle)), host=str(host))

        def get(stage):
            item = provider_event(log, stage)
            status = proc.poll()
            if item is None and status is not None:
                # The process may have exited between reading the file and polling the handle.
                item = provider_event(log, stage)
                if item is None:
                    raise RuntimeError(f"The provider exited before {stage} with {status}")
            return item
        try:
            machine = result["machine"] = api.machine(int(proc._handle))
            if machine != api.machine(-1):
                raise Unavailable("The UI Automation observer did not execute natively on this target")
            yield proc, get
        finally:
            if proc.poll() is None:
                try:
                    command(proc, b"cancel\n")
                except BrokenPipeError:
                    pass
            result["exit"] = launcher.wait_for_exit(proc, lambda: None, 10)
            result["jobEmpty"] = api.wait_job_empty(job, 5)
            if not result["jobEmpty"] or result["exit"] not in (0, 2):
                raise RuntimeError("The native UI Automation observer failed to finish")


def confirm_surface(event, key, creation, rect, expected_rgb, first=None):
    surface = event["surface"]
    if ([str(surface[name]) for name in ("pid", "hwnd", "id")] != list(key)
            or surface["creation"] != creation or surface["rect"] != rect):
        raise ValueError("The independent Shell rectangle and executable identity differ from the primary")
    left, top, right, bottom = rect
    if (not (2 <= right - left <= 256 and 2 <= bottom - top <= 256)
            or surface["point"] != [(left + right) // 2, (top + bottom) // 2]
            or surface["bar"] <= 0 or surface["hit"] <= 0 or surface["shellPid"] <= 0
            or surface["shellCreation"] <= 0 or surface["desktop"] != "Default"
            or not re.fullmatch("[0-9a-f]{6}", surface["rgb"])):
        raise ValueError("Incomplete pixel, input desktop or Explorer hit evidence")
    if any(abs(a - b) > 8 for a, b in zip(bytes.fromhex(surface["rgb"]), bytes.fromhex(expected_rgb))):
        raise ValueError("The independent pixel did not match the current marker")
    if first and any(surface[k] != first[k] for k in ("rect", "point", "hit", "bar", "shellPid", "shellCreation")):
        raise Unavailable("Explorer's original hit window, process or rectangle changed")
    return surface


def confirm_provider(event, surface, token):
    provider = event["provider"]
    bounds = provider["bounds"]
    left, top, right, bottom = surface["rect"]
    x, y = surface["point"]
    if (provider["matchCount"] != 1 or provider["matchedLabel"] != "IFW tray " + token
            or not provider["runtimeId"] or provider["pid"] != surface["shellPid"]
            or not (provider["nameMatches"] is True or provider["helpMatches"] is True)
            or provider["enabled"] is not True or provider["offscreen"] is not False
            or not 0 <= provider["hitDepth"] < 12 or len(bounds) != 4
            or not all(math.isfinite(v) for v in bounds)
            or not (left <= bounds[0] <= x < bounds[2] <= right and top <= bounds[1] <= y < bounds[3] <= bottom)):
        raise ValueError("The provider did not independently identify a unique visible item at the marker")
    return provider


def resident(api, desk, gui, trial, env, out, result):
    desktop = check(desk.thread_desktop(desk.thread()), "GetThreadDesktop(input observer)")
    result["contextBefore"] = desk.context()
    if not ordinary_console(result["contextBefore"], "Default"):
        raise Unavailable("The runner did not supply its original unlocked console input desktop")
    native = NativeTray(api, desk, "Default", env["IFW_QA_INVENTORY_TOKEN"])
    clock = bind(api.kernel, "GetTickCount64", c.c_uint64)
    primary_log = out / "resident-primary.log"
    with ExitStack() as stack:
        stream = stack.enter_context(primary_log.open("xb"))
        proc, job, tid = stack.enter_context(launcher.child(api, desk, "Default", gui, ["--autostart"], trial, env,
                                                            stream, True, private=False))
        creation = api.process_identity(int(proc._handle))
        result.update(primaryPid=proc.pid, primaryCreation100ns=creation, primaryArguments=["--autostart"])
        windows = recorder.load_windows_fixture().Windows(proc.pid, desktop)
        stack.callback(launcher.release, windows.close, "Could not release the resident GUI window hook")

        def log():
            return primary_log.read_text(encoding="utf-8", errors="replace")

        def wait(get, message):
            def poll():
                windows.pump()
                recorder.wait_running(proc)
                return get()
            return recorder.await_value(poll, message, delay=.04)

        def hidden():
            text = log()
            if (windows.visible() is not None or records(text, "TRAY_CALLBACK") or records(text, "TRAY_OPEN")
                    or any(value in text for value in ("ADAPTER Dx12 ", "WINDOW_RELEASED ", "LAUNCHER_OPEN "))
                    or not ordinary_console(desk.context(), "Default")):
                raise Unavailable("The original GUI, accessibility or desktop state changed before provider activation")

        result["stage"] = "registration"
        try:
            command(proc, b"B")
            key = native.registration(proc, log, wait, result, no_host=False)
            wait(lambda: "READY BackgroundStartup Available" in log().splitlines(), "The supervisor did not remain resident")
            wait(lambda: recorder.idle_complete(log()), "The original worker did not finish its initial inventories")
            worker = recorder.owned_worker(api, proc, primary_log, recorder.await_value)
            handle = recorder.checked(api.open(0x100000 | 0x1000, False, worker))
            stack.callback(launcher.release_handle, api.close, "CloseHandle(resident worker)", handle)
            console = launcher.system_console_path(api.kernel)

            def worker_identity(stage):
                detail = result[stage + "Job"] = {}
                return launcher.primary_job_members(api, desk, job, proc.pid, worker, gui, console, detail)
            result["workerBefore"] = worker_identity("before")
            hidden()
            result["residentWindows"] = launcher.snapshot(desk, windows, desktop, None, tid, creation)
            colors = marker_colors(native.token)
            first_rect = wait(lambda: icon(log(), "initial", key, colors[0]), "Missing initial GUI icon")
            state = result["provider"] = {}
            result["stage"] = "first-marker"
            with provider(api, desk, trial, env, out, key, creation, state) as (helper, get):
                initial = wait(lambda: get("first"), "The native marker observer did not start")
                first = result["first"] = confirm_surface(initial, key, creation, first_rect, colors[0])
                hidden()
                result["stage"] = "second-marker"
                command(proc, b"M")
                changed = wait(lambda: icon(log(), "changed", key, colors[1]), "Missing GUI marker modification")
                command(proc, b"P")
                current = wait(lambda: icon(log(), "sample", key, colors[1]), "Missing fresh GUI rectangle")
                if first_rect != changed or changed != current:
                    raise Unavailable("The notification icon moved during the marker challenge")
                command(helper, b"second\n")
                ready = wait(lambda: get("ready"), "The two-color and accessibility observer did not report an outcome")
                result["second"] = confirm_surface(ready, key, creation, current, colors[1], first)
                result["providerIdentity"] = confirm_provider(ready, result["second"], native.token)
                hidden()
                result["stage"] = "provider-invoke"
                command(helper, b"invoke\n")
                attempted = wait(lambda: get("attempt"), "The exact accessibility provider was unavailable")
                confirm_surface(attempted, key, creation, current, colors[1], first)
                if confirm_provider(attempted, result["second"], native.token) != result["providerIdentity"]:
                    raise ValueError("The accessibility provider changed before invocation")
                invoked = wait(lambda: get("invoked"), "The accessibility provider did not return")
                state.update(attemptTick=attempted["tick"], startTick=invoked["startTick"], returnedTick=invoked["returnedTick"])
                if not 0 <= state["attemptTick"] <= state["startTick"] <= state["returnedTick"]:
                    raise ValueError("The provider's monotonic interval was invalid")
            result["stage"] = "shell-callback"
            try:
                result["delivery"] = wait(lambda: delivery(log(), key, state["startTick"], clock()),
                                          "No matching v4 Shell callback and GUI Open")
            except TimeoutError as exc:
                if records(log(), "TRAY_CALLBACK") or records(log(), "TRAY_OPEN"):
                    raise ValueError("The observed Shell callback did not reach the original GUI queue") from exc
                raise Unavailable("The exact provider returned without a matching Shell callback") from exc
            result["stage"] = "visible-primary"
            hwnd = wait(windows.visible, "The opened primary had no independently visible window")
            wait(lambda: "ADAPTER Dx12 " in log(), "The activated GUI did not initialize its renderer")
            native.visible_window(proc, hwnd, result, "openedWindow")
            result["foregroundObservation"] = launcher.passive_foreground(desk, windows, hwnd, desk.foreground() == hwnd)
            result["openedWindows"] = launcher.snapshot(desk, windows, desktop, None, tid, creation)
            result["workerAfter"] = worker_identity("after")
            if result["workerAfter"] != result["workerBefore"] or api.process_identity(int(proc._handle)) != creation:
                raise ValueError("The activated primary or its original inventory worker changed")
        finally:
            try:
                result["quitRequested"] = False
                if proc.poll() is None:
                    try:
                        command(proc, b"Q")
                        result["quitRequested"] = True
                    except OSError as exc:
                        result["quitWriteError"] = str(exc)
                try:
                    launcher.wait_for_exit(proc, windows.pump, 15)
                finally:
                    native.check_drain(proc, job, log(), result)
            finally:
                result["contextAfter"] = desk.context()
        if not result["quitRequested"]:
            raise ValueError("The primary exited before the observer could request normal Quit")
        if not ordinary_console(result["contextAfter"], "Default"):
            raise Unavailable("The original input desktop could not be confirmed at teardown")
        native.qualify_quiet_shell(log(), result, no_host=False)
        if (delivery(log(), key, state["startTick"], result["delivery"]["observedMs"]) != result["delivery"]
                or "LAUNCHER_OPEN " in log()):
            raise ValueError("The original provider activation changed before quit")


def assess(target, out, result):
    files = (Path(__file__).resolve(), PROVIDER, launcher.QA / "windows-inventory/scan.py",
             launcher.QA / "windows-inventory/subject.py")
    with launcher.native_subject(target, out, result, files) as (api, desk, built_gui, inventory, _revision):
        for case in ("shellLess", "inputDesktop"):
            state = result[case] = dict(cleanupConfirmed=False)
            try:
                with launcher.staged_profile(state, api, built_gui, inventory) as (gui, trial, env):
                    env["IFW_QA_WINDOWS_TRAY"] = "1"
                    if case == "shellLess":
                        name = "IfwQa_Tray_" + state["profile"]
                        native = NativeTray(api, desk, name, state["profile"])
                        select = bind(c.WinDLL("user32", use_last_error=True), "SetThreadDesktop", w.BOOL, w.HANDLE)
                        state["desktopCleanup"] = {}
                        launcher.private_desktop(desk, select, name, lambda handle: launcher.desktop_cases(
                            api, desk, name, handle, gui, trial, env, out, state, native_tray=native), state["desktopCleanup"])
                    else:
                        resident(api, desk, gui, trial, env, out, state)
            except Exception as exc:
                state.update(status="unavailable" if isinstance(exc, Unavailable) else "failed", failures=launcher.failures(exc))
                if not state["cleanupConfirmed"] or CleanupUnconfirmed.in_chain(exc):
                    state["status"] = "failed"
                    if case == "shellLess":
                        result["inputDesktop"] = dict(status="not-run", reason="Private cleanup was not confirmed")
                    raise
            else:
                state["status"] = "passed"
    statuses = {result[case]["status"] for case in ("shellLess", "inputDesktop")}
    return "failed" if "failed" in statuses else "unavailable" if "unavailable" in statuses else "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=launcher.TARGETS)
    target = parser.parse_args().target
    out = launcher.ROOT / "artifacts/rust/windows-gui-tray" / target
    out.mkdir(parents=True, exist_ok=False)
    result = {"target": target, "status": "failed"}
    try:
        result["status"] = assess(target, out, result)
    except Exception as exc:
        result["failures"] = launcher.failures(exc)
    finally:
        result["evidenceFiles"] = {path.name: recorder.sha(path) for path in sorted(out.iterdir()) if path.is_file()}
        recorder.write(out / "result.json", result)
    print(result["status"])
    return {"passed": 0, "unavailable": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
