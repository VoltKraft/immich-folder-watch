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
from window_readback import RECEIVER_CLASS, monitor_work_area, visible_surface

PROVIDER = launcher.HERE / "tray_provider.ps1"
RECORDS = {
    "TRAY_REGISTER": r"phase=(initial|retry|recreate) pid=(\d+) hwnd=(\d+) id=(\d+) token=([0-9a-f]{32}) added=([01]) version4=([01])",
    "TRAY_BIND": r"phase=(initial|retry|recreate) pid=(\d+) hwnd=(\d+) id=(\d+) shell_pid=(\d+) shell_hwnd=(\d+) verified=([01])",
    "TRAY_RETIRED": r"pid=(\d+) hwnd=(\d+) id=(\d+) shell_pid=(\d+) shell_hwnd=(\d+)",
    "TRAY_ICON": r"phase=(initial|changed|sample) pid=(\d+) hwnd=(\d+) id=(\d+) rgb=([0-9a-f]{6}) rect=(none|-?\d+,-?\d+,-?\d+,-?\d+) ok=([01])",
    "TRAY_CALLBACK": r"pid=(\d+) hwnd=(\d+) id=(\d+) code=(\d+) ordinal=(\d+) queued_ms=(none|\d+) dispatch_ms=(\d+)",
    "TRAY_OPEN": r"pid=(\d+) ordinal=(\d+)",
    "TRAY_CLEANUP": r"pid=(\d+) hwnd=(\d+) id=(\d+) registered=([01]) removed=([01])",
}


class Unavailable(Exception):
    """The desktop or Shell could not expose the requested native observation."""


class IconIdentifier(c.Structure):
    _fields_ = [("size", w.DWORD), ("owner", w.HWND), ("id", w.UINT), ("guid", c.c_uint32 * 4)]


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


def shell_operations(log):
    """Read the completed supervisor's Shell calls and matching receipts in their emission order."""
    events = {"TRAY_REGISTER", "TRAY_BIND", "TRAY_RETIRED", "TRAY_CLEANUP"}
    for raw in log.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        name = line.partition(" ")[0]
        if name in events:
            match = re.fullmatch(name + " " + RECORDS[name], line)
            if not match or not raw.endswith("\n"):
                raise CleanupUnconfirmed(f"Incomplete {name} in the completed supervisor log")
            yield name, match.groups()
        elif line.startswith("gui_tray."):
            name, _, value = line.removeprefix("gui_tray.").partition("=")
            if name.endswith(".raw_last_error"):
                continue
            if value not in ("true", "false") or not raw.endswith("\n"):
                raise CleanupUnconfirmed("Incomplete native Shell call outcome")
            yield name, value == "true"


def replay_shutdown(log, key, token, report):
    """Reconstruct outstanding ownership from real adds, version acknowledgements and deletes."""
    lines = log.splitlines(keepends=True)
    primary = next((i for i, line in enumerate(lines) if line.rstrip("\r\n") == f"LAUNCHER_PRIMARY pid={key[0]}"), None)
    drained = next((i for i, line in enumerate(lines) if re.fullmatch(r"DRAINED passes=\d+\r?\n", line)), None)
    if (primary is None or drained is None or primary >= drained
            or any(shell_operations("".join(lines[:primary] + lines[drained + 1:])))):
        raise CleanupUnconfirmed("The Shell operations were not enclosed by the elected primary and its final drain")
    report["shellOperations"] = list(shell_operations("".join(lines[primary + 1:drained])))
    operations = iter(report["shellOperations"])
    bindings, withdrawals = [], []
    report.update(bindings=bindings, withdrawals=withdrawals)

    def take(name):
        actual, data = next(operations, (None, None))
        if actual != name:
            raise CleanupUnconfirmed(f"Expected {name} after the preceding native Shell operation")
        return data

    def bind_owner(phases):
        row = take("TRAY_BIND")
        bindings.append(row)
        phase, pid, hwnd, ident, shell_pid, bar, verified = row
        if (phase not in phases or (pid, hwnd, ident) != key
                or (verified == "1" and min(int(shell_pid), int(bar)) == 0)
                or (verified == "0" and (shell_pid, bar) != ("0", "0"))):
            raise CleanupUnconfirmed("The binding did not identify the current operation and notification icon")
        return (int(shell_pid), int(bar)) if verified == "1" else None

    outstanding = False
    bound = None
    registrations = marker_acks = 0
    existing_refused = awaiting_add = False
    for action, outcome in operations:
        can_withdraw, existing_refused = existing_refused, False
        if ((awaiting_add and action not in ("retry.add", "recreate.add"))
                or (can_withdraw and action not in ("existing.withdraw", "retry.add", "recreate.add"))):
            raise CleanupUnconfirmed("Missing the fresh add or withdrawal after the old Shell declined v4")
        awaiting_add = False
        if action in ("initial.add", "retry.add", "recreate.add"):
            if outstanding and not can_withdraw:
                raise CleanupUnconfirmed("An outstanding icon must receive a real existing-version refusal before a fresh add")
            phase = action.split(".")[0]
            if (phase == "initial") != (registrations == 0):
                raise CleanupUnconfirmed("The first Shell request must be the only initial registration")
            registrations += 1
            version4 = False
            if outcome:
                outstanding = True
                version4 = take(phase + ".version4")
                bound = bind_owner((phase,))
            if take("TRAY_REGISTER") != (phase, *key, token, str(int(outcome)), str(int(version4))):
                raise CleanupUnconfirmed("Shell calls and registration receipt disagree")
            if outcome and not version4:
                if not take("incompatible_version"):
                    raise CleanupUnconfirmed("The Shell did not remove the rejected v4 icon")
                withdrawals.append("incompatible_version")
                outstanding, bound = False, None
        elif action == "existing.version4" and outstanding:
            if outcome:
                bound = bind_owner(("recreate", "retry"))
            else:
                existing_refused = True
        elif action == "existing.withdraw" and outstanding and can_withdraw:
            bound = None  # The host had this key but refused to confirm v4.
            if outcome:
                outstanding = False
                withdrawals.append(action)
                awaiting_add = True
        elif action == "change" and outstanding:
            marker_acks += int(outcome)
        elif action == "shutdown" and outstanding:
            if outcome:
                cleanup = take("TRAY_CLEANUP")
                retirement, method = None, "deletedAtQuit"
            else:
                retired = take("TRAY_RETIRED")
                if not bound or retired != (*key, *map(str, bound)):
                    raise CleanupUnconfirmed("The retired Shell did not match the last verified registration")
                retirement, method = bound, "originalShellExited"
                cleanup = take("TRAY_CLEANUP")
            expected = (*key, "1", str(int(outcome)))
            break
        elif action == "TRAY_CLEANUP" and not outstanding:
            cleanup, expected, retirement = outcome, (*key, "0", "0"), None
            method = "withdrawnBeforeQuit" if withdrawals else "neverAdded"
            break
        else:
            raise CleanupUnconfirmed(f"Unexpected {action} for the outstanding notification icon")
    else:
        raise CleanupUnconfirmed("Missing final integrated icon cleanup")
    if not registrations or cleanup != expected or next(operations, None) is not None:
        raise CleanupUnconfirmed("The final icon ID, cleanup BOOLs or operation order changed")
    report.update(reportedCleanupMethod=method, markerAcknowledgements=marker_acks)
    return retirement


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


class ShellWitness:
    """Keep the original Shell process object open across the GUI's registration, markers and Quit."""
    def __init__(self, api, desk, name, stack, report):
        self.api, self.desk, self.name, self.report = api, desk, name, report
        self.desktop = desk.thread_desktop(desk.thread())
        self.find = bind(c.WinDLL("user32", use_last_error=True), "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
        self.wait = bind(api.kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        self.handle, self.original, self.confirmed, self.markers = None, None, False, 0
        before = report["beforeOpen"] = self.snapshot()
        original = self.identity(before)
        if original:
            self.handle = api.open(0x100000, False, original[0])  # SYNCHRONIZE, never inherit.
            if self.handle:
                stack.callback(launcher.release_handle, api.close, "CloseHandle(original Shell witness)", self.handle)
                after = report["afterOpen"] = self.snapshot()
                if self.identity(after) == original and self.wait(self.handle, 0) == 258:
                    self.original = original
        report["pinnedBeforeRegistration"] = self.original is not None

    def snapshot(self):
        desktop = self.desk.thread_desktop(self.desk.thread())
        correct = (desktop == self.desktop and self.desk.name(desktop) == self.name
                   and str(self.desk.name(self.desk.station())).casefold() == "winsta0")
        bar, shell = self.find("Shell_TrayWnd", None), self.desk.shell()

        def owner(hwnd):
            pid = w.DWORD()
            if not hwnd:
                return None
            tid = self.desk.owner(hwnd, c.byref(pid))
            return dict(hwnd=int(hwnd), tid=tid, pid=pid.value,
                        desktop=self.desk.name(self.desk.thread_desktop(tid)) if tid else None)

        return dict(originalDesktop=correct, taskbar=owner(bar), shell=owner(shell))

    def identity(self, sample):
        bar, shell = sample["taskbar"], sample["shell"]
        if (sample["originalDesktop"] and bar and shell and bar["pid"] > 0
                and bar["pid"] == shell["pid"] and bar["desktop"] == shell["desktop"] == self.name):
            return bar["pid"], bar["hwnd"]
        return None

    def live(self, stage):
        sample = self.report[stage] = self.snapshot()
        state = self.wait(self.handle, 0) if self.handle else None
        sample["wait"] = state
        return bool(self.original and self.identity(sample) == self.original and state == 258)

    def confirm_initial(self, row):
        live = self.live("afterInitialRegistration")
        self.confirmed = bool(row and row[-1] == "1" and self.original == (int(row[4]), int(row[5])) and live)
        self.report["initialBindingConfirmed"] = self.confirmed

    def verify_retirement(self, expected, report, read_rect):
        # Only the initial registration was bracketed before and after its acknowledgement.
        # A subsequent acknowledged add or SETVERSION gets a different binding in the replay.
        if (expected != self.original or not self.confirmed or len(report["bindings"]) != 1
                or report["markerAcknowledgements"] != self.markers):
            raise CleanupUnconfirmed("The observer did not retain the final registered Shell identity")
        before = self.snapshot()
        state = self.wait(self.handle, 0)
        report["shellAfterExit"] = read_rect()
        after = self.snapshot()
        report["hostExitReadback"] = dict(before=before, wait=state, after=after)
        if (state != 0 or report["shellAfterExit"]["hresult"] >= 0
                or any(not item["originalDesktop"] or item["shell"] or item["taskbar"] for item in (before, after))):
            raise CleanupUnconfirmed("The original Shell process, desktop or icon absence could not be confirmed")


class NativeTray:
    def __init__(self, api, desk, name, token):
        self.api, self.desk, self.name, self.token = api, desk, name, token
        self.witness = None
        self.activation_checks = {}

    def watch_original(self, stack, result):
        result["shellWitness"] = {}
        self.witness = ShellWitness(self.api, self.desk, self.name, stack, result["shellWitness"])

    def original_at(self, stage, surface=None):
        witness = self.witness
        try:
            live = witness is not None and witness.live(stage)
        except OSError as exc:
            witness.report[stage] = {"error": str(exc)}
            live = False
        agrees = bool(live and witness.confirmed and (surface is None or
                      (surface["shellPid"], surface["bar"]) == witness.original))
        self.activation_checks[stage] = agrees
        return agrees

    def require_original(self, stage, surface=None):
        if not self.original_at(stage, surface):
            raise Unavailable(f"The retained original Shell could not be confirmed at {stage}")

    def registration(self, proc, log, wait, result, *, no_host, private=None):
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
        if not window or window["pid"] != proc.pid or window["class"] != RECEIVER_CLASS:
            raise ValueError("The receiver HWND did not belong to the retained primary on the selected desktop")
        if no_host:
            if (private is None or private.proc is not proc or private.name != self.name or self.name == "Default"
                    or actual_desktop not in (self.name, {"win32Error": 5})):
                raise ValueError("The receiver lacked a consistent thread or private desktop membership witness")
            private.verify(int(hwnd), "trayReceiver", visible=False, tid=window["tid"], receiver=True)
        elif actual_desktop != self.name:
            raise ValueError("The receiver HWND did not belong to the original desktop")
        independent = result["registration"]["shellReadback"] = shell_rect(int(hwnd))
        binds = [row for row in records(log(), "TRAY_BIND") if row[0] == "initial"]
        if added == "1":
            bound = one(binds, "initial Shell binding")
            if bound[1:4] != key:
                raise ValueError("The initial Shell binding identified a different notification icon")
        else:
            if binds:
                raise ValueError("A refused initial add cannot bind a Shell process")
            bound = None
        if self.witness:
            self.witness.confirm_initial(bound)
        if no_host and ((added, v4) != ("0", "0") or independent["hresult"] >= 0):
            raise Unavailable("The Shell accepted registration on the private desktop without a taskbar")
        if not no_host and (added, v4) != ("1", "1"):
            raise Unavailable("The input desktop did not accept the integrated icon's first v4 registration")
        if not no_host:
            self.activation_checks["initialAck"] = bool(self.witness and self.witness.confirmed)
            if not self.activation_checks["initialAck"]:
                raise Unavailable("The first v4 acknowledgement did not match the independently pinned original Shell")
        return key

    def visible_window(self, proc, hwnd, result, stage, *, private=None):
        if private is not None:
            receiver = result["registration"]
            private.verify(receiver["hwnd"], stage + ".receiver", visible=False,
                           tid=receiver["receiver"]["tid"], receiver=True)
        visible_surface(self.desk, self.name, proc.pid, hwnd, result, stage, private=private,
                        monitor_area=monitor_work_area, unavailable=Unavailable)

    def check_drain(self, proc, job, log, result):
        """Retain normal app exit, job accounting and exact icon removal even on observation failure."""
        try:
            self._shutdown(proc, job, log, result)
        except (ValueError, OSError) as exc:
            raise CleanupUnconfirmed("Could not verify the original notification icon's cleanup") from exc

    def _shutdown(self, proc, job, log, result):
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
        retirement = replay_shutdown(log, key, self.token, report)
        owner = w.DWORD()
        after_tid = self.desk.owner(int(key[1]), c.byref(owner))
        report["receiverAfterExit"] = dict(tid=after_tid, pid=owner.value)
        if retirement:
            if after_tid or not self.witness:
                raise CleanupUnconfirmed("The receiver or the independently retained Shell handle changed")
            self.witness.verify_retirement(retirement, report, lambda: shell_rect(int(key[1])))
            if self.desk.owner(int(key[1]), c.byref(owner)):
                raise CleanupUnconfirmed("The receiver HWND was reused during the retirement readback")
        elif after_tid:
            # A recycled HWND belongs to another process. Do not query that process's icon.
            report["shellAfterExit"] = None
        else:
            report["shellAfterExit"] = shell_rect(int(key[1]))
            if report["shellAfterExit"]["hresult"] >= 0:
                raise CleanupUnconfirmed("The Shell did not confirm absence of the original icon after quit")
        report["cleanupMethod"] = report["reportedCleanupMethod"]
        quiet = len(rows) == 1 and not retirement and not report["withdrawals"] and not shell_changed(log)
        stable = quiet
        if self.name == "Default" and initial[-2:] == ("1", "1"):
            self.original_at("afterQuit")
            steps = ("initialAck", "beforeMarker", "afterMarker", "beforeInvoke", "providerAttempt", "afterInvoke", "afterQuit")
            report["activationHostChecks"] = dict(self.activation_checks)
            changes = [ok for event, ok in report["shellOperations"] if event == "change"]
            stable = bool(quiet and all(self.activation_checks.get(step) is True for step in steps)
                          and self.witness and self.witness.markers == 1 and changes == [True])
        report["observedHostInstability"] = not quiet or False in self.activation_checks.values()
        report["stableRegistration"] = stable

    @staticmethod
    def qualify_quiet_shell(log, result, *, no_host):
        if (not result["nativeShutdown"]["stableRegistration"]
                or (not no_host and result["nativeShutdown"].get("activationHostChecks", {}).get("initialAck") is not True)):
            raise Unavailable("The original Shell registration could not be confirmed through the trial")
        if result["nativeShutdown"]["shellAfterExit"] is None:
            raise Unavailable("The receiver HWND was reused before post-quit readback")
        if not no_host and not result["nativeShutdown"]["uiPasses"]:
            raise ValueError("The GUI completed no UI pass after opening from background startup")
        if no_host and (records(log, "TRAY_CALLBACK") or records(log, "TRAY_OPEN")):
            raise ValueError("Unexpected notification-area activation on the shell-less desktop")


def command(process, data):
    process.stdin.write(data)
    process.stdin.flush()


def shell_changed(log):
    return (any(tag in log for tag in ("TRAY_TASKBAR ", "TRAY_HOST ", "gui_tray.existing.", "gui_tray.retry.", "gui_tray.recreate."))
            or len(records(log, "TRAY_BIND")) > 1 or len(records(log, "TRAY_REGISTER")) > 1)


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


def resident(api, desk, gui, trial, env, out, result, *, subject="canonical", reopen=False):
    if reopen and subject != "retained":
        raise ValueError("The Shell reopen case requires the retained-window executable")
    desktop = check(desk.thread_desktop(desk.thread()), "GetThreadDesktop(input observer)")
    result["contextBefore"] = desk.context()
    if not ordinary_console(result["contextBefore"], "Default"):
        raise Unavailable("The runner did not supply its original unlocked console input desktop")
    native = NativeTray(api, desk, "Default", env["IFW_QA_INVENTORY_TOKEN"])
    clock = bind(api.kernel, "GetTickCount64", c.c_uint64)
    primary_log = out / "resident-primary.log"
    args = [] if reopen else ["--autostart"]
    with ExitStack() as stack:
        stream = stack.enter_context(primary_log.open("xb"))
        proc, job, tid = stack.enter_context(launcher.child(api, desk, "Default", gui, args, trial, env,
                                                            stream, True, private=False))
        creation = api.process_identity(int(proc._handle))
        result.update(primaryPid=proc.pid, primaryCreation100ns=creation, primaryArguments=args)
        fixture = recorder.load_windows_fixture()
        windows = fixture.Windows(proc.pid, desktop)
        stack.callback(launcher.release, windows.close, "Could not release the resident GUI window hook")
        retained = None
        if subject == "retained":
            evidence = result["retainedWindow"] = {}
            retained = launcher.RetainedWindow(desk, windows, fixture.TITLE, "Default", evidence)
            stack.callback(launcher.release, retained.close, "Could not remove the Shell activation lifetime hook")

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
            if shell_changed(text) or not ordinary_console(desk.context(), "Default"):
                raise Unavailable("The original GUI, accessibility or desktop state changed before provider activation")
            if (windows.visible() is not None or records(text, "TRAY_CALLBACK") or records(text, "TRAY_OPEN")
                    or any(value in text for value in ("WINDOW_RELEASED ", "LAUNCHER_OPEN "))):
                error = ValueError if retained is not None else Unavailable
                raise error("Unexpected GUI activation or release before the selected Shell provider was invoked")
            if reopen:
                if not retained.hidden(text):
                    raise ValueError("The previously closed GUI did not remain hidden until the real Shell activation")
            elif "ADAPTER Dx12 " in text or "GRAPHICS_ATTEMPT " in text:
                raise ValueError("The background GUI allocated a renderer before the real Shell activation")

        result["stage"] = "registration"
        try:
            native.watch_original(stack, result)
            command(proc, b"B")
            key = native.registration(proc, log, wait, result, no_host=False)
            expected = "READY Visible Available" if reopen else "READY BackgroundStartup Available"
            wait(lambda: expected in log().splitlines(), "The supervisor did not select its expected window intent")
            result["startupIntent"] = expected
            wait(lambda: recorder.idle_complete(log()), "The original worker did not finish its initial inventories")
            worker = recorder.owned_worker(api, proc, primary_log, recorder.await_value)
            handle = recorder.checked(api.open(0x100000 | 0x1000, False, worker))
            stack.callback(launcher.release_handle, api.close, "CloseHandle(resident worker)", handle)
            console = launcher.system_console_path(api.kernel)

            def worker_identity(stage):
                detail = result[stage + "Job"] = {}
                return launcher.primary_job_members(api, desk, job, proc.pid, worker, gui, console, detail)
            result["workerBefore"] = worker_identity("before")
            if reopen:
                result["stage"] = "close-before-provider"
                first_window = wait(windows.visible, "The ordinary retained primary did not show its first window")
                wait(lambda: "ADAPTER Dx12 " in log(), "The original window did not initialize DX12")
                retained.first(first_window, log, wait)
                retained.close_window()
                wait(lambda: retained.hidden(log()), "The retained window did not hide before the provider challenge")
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
                native.require_original("beforeMarker", first)
                command(proc, b"M")
                changed = wait(lambda: icon(log(), "changed", key, colors[1]), "Missing GUI marker modification")
                native.require_original("afterMarker")
                if [line for line in log().splitlines() if line.startswith("gui_tray.change=")] != ["gui_tray.change=true"]:
                    raise ValueError("The GUI marker was not backed by exactly one acknowledged Shell modification")
                native.witness.markers += 1
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
                native.require_original("beforeInvoke", result["second"])
                if retained is not None:
                    windows.pump()
                    events_before_invoke = len(windows.events)
                command(helper, b"invoke\n")
                attempted = wait(lambda: get("attempt"), "The exact accessibility provider was unavailable")
                target = confirm_surface(attempted, key, creation, current, colors[1], first)
                native.require_original("providerAttempt", target)
                if confirm_provider(attempted, result["second"], native.token) != result["providerIdentity"]:
                    raise ValueError("The accessibility provider changed before invocation")
                invoked = wait(lambda: get("invoked"), "The accessibility provider did not return")
                native.require_original("afterInvoke", target)
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
            if retained is not None:
                retained.sample_after_trigger("callbackShow", result["delivery"], clock)
            result["stage"] = "visible-primary"
            hwnd = wait(windows.visible, "The opened primary had no independently visible window")
            wait(lambda: "ADAPTER Dx12 " in log(), "The activated GUI did not initialize its renderer")
            native.visible_window(proc, hwnd, result, "openedWindow")
            result["foregroundObservation"] = launcher.passive_foreground(desk, windows, hwnd, desk.foreground() == hwnd)
            result["openedWindows"] = launcher.snapshot(desk, windows, desktop, None, tid, creation)
            result["workerAfter"] = worker_identity("after")
            if result["workerAfter"] != result["workerBefore"] or api.process_identity(int(proc._handle)) != creation:
                raise ValueError("The activated primary or its original inventory worker changed")
            if retained is not None:
                if reopen:
                    retained.opened(hwnd, log, wait)
                else:
                    retained.first(hwnd, log, wait)
                show_ordered = retained.activated_show(events_before_invoke, result["delivery"]["dispatchMs"], clock(), "callbackShow")
                result["keyboardFocus"] = {}
                retained.focus(result["keyboardFocus"])
                retained.check_visible(log, "beforeQuit")
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
        if retained is not None:
            launcher.retained_graphics(log(), evidence, before_quit=False)
            if not show_ordered:
                raise launcher.ShowOrderUnavailable(evidence["callbackShow"]["reason"])


def assess(target, out, result, *, subject="canonical"):
    files = (Path(__file__).resolve(), PROVIDER, launcher.QA / "windows-inventory/scan.py",
             launcher.QA / "windows-inventory/subject.py")
    cases = ("shellLess", "inputDesktop", "inputDesktopReopen") if subject == "retained" else ("shellLess", "inputDesktop")
    with launcher.native_subject(target, out, result, files, subject=subject) as (api, desk, built_gui, inventory, _revision):
        for index, case in enumerate(cases):
            state = result[case] = dict(cleanupConfirmed=False)
            try:
                case_out = out
                if case == "inputDesktopReopen":
                    case_out = out / case
                    case_out.mkdir()
                with launcher.staged_profile(state, api, built_gui, inventory) as (gui, trial, env):
                    env["IFW_QA_WINDOWS_TRAY"] = "1"
                    if case == "shellLess":
                        name = "IfwQa_Tray_" + state["profile"]
                        native = NativeTray(api, desk, name, state["profile"])
                        select = bind(c.WinDLL("user32", use_last_error=True), "SetThreadDesktop", w.BOOL, w.HANDLE)
                        state["desktopCleanup"] = {}
                        def visit(handle):
                            with ExitStack() as stack:
                                native.watch_original(stack, state)
                                launcher.desktop_cases(api, desk, name, handle, gui, trial, env, case_out, state,
                                                       native_tray=native, subject=subject)
                        launcher.private_desktop(desk, select, name, visit, state["desktopCleanup"])
                    else:
                        resident(api, desk, gui, trial, env, case_out, state, subject=subject,
                                 reopen=case == "inputDesktopReopen")
                if not state["cleanupConfirmed"]:
                    raise CleanupUnconfirmed(f"Cleanup of {case} was not confirmed")
            except Exception as exc:
                shutdown = state.get("nativeShutdown", state.get("activation", {}).get("nativeShutdown", {}))
                churn_timeout = isinstance(exc, TimeoutError) and shutdown.get("observedHostInstability") is True
                state.update(status="unavailable" if isinstance(exc, (Unavailable, launcher.ShowOrderUnavailable)) or churn_timeout else "failed",
                             failures=launcher.failures(exc))
                if not state["cleanupConfirmed"] or CleanupUnconfirmed.in_chain(exc):
                    state["status"] = "failed"
                    for later in cases[index + 1:]:
                        result[later] = dict(status="not-run", reason=f"Cleanup of {case} was not confirmed")
                    raise
            else:
                state["status"] = "passed"
    statuses = {result[case]["status"] for case in cases}
    return "failed" if "failed" in statuses else "unavailable" if "unavailable" in statuses else "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=launcher.TARGETS)
    parser.add_argument("--subject", choices=launcher.SUBJECTS, default="canonical")
    options = parser.parse_args()
    target = options.target
    directory = "windows-gui-tray-retained" if options.subject == "retained" else "windows-gui-tray"
    out = launcher.ROOT / "artifacts/rust" / directory / target
    out.mkdir(parents=True, exist_ok=False)
    result = {"target": target, "subject": options.subject, "status": "failed"}
    try:
        result["status"] = assess(target, out, result, subject=options.subject)
    except Exception as exc:
        result["failures"] = launcher.failures(exc)
    finally:
        result["evidenceFiles"] = {path.relative_to(out).as_posix(): recorder.sha(path)
                                   for path in sorted(out.rglob("*")) if path.is_file()}
        recorder.write(out / "result.json", result)
    print(result["status"])
    return {"passed": 0, "unavailable": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
