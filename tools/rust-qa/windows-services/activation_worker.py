"""Run the tray experiment inside the supervisor's new, disposable WinSta0 desktop."""

from contextlib import contextmanager, ExitStack
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

from activation import HERE, hosted, module, paths, sha, write
from activation_native import ICON, Native, Unavailable, callback_tick, check, elapsed_ticks, expected_colors, matches, same_spot

RECORDS = {"synthetic.fixture", "change", "arm", "finish", "overflow.pending", "overflow.ready", "release-menu"}
RECORDS.update(name + suffix for name in ("first", "second", "armed", "callback") for suffix in ("", ".pending"))


@contextmanager
def private_area(api, token, report):
    area = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True) / ("ifw-shell-" + token)
    area.mkdir(exist_ok=False)
    marker = area / "synthetic.fixture"
    def remove_original(path, is_directory, expected):
        owned = api.jobs.path_handle(path, is_directory, delete=True)
        try:
            attributes, actual = api.jobs.file_info(owned)
            if actual != expected or attributes & 0x400 or bool(attributes & 0x10) != is_directory:
                raise RuntimeError("The original private fixture identity changed before removal")
            api.jobs.delete_handle(owned)
        finally:
            check(api.jobs.close(owned), "CloseHandle(private cleanup)")

    with ExitStack() as pins, ExitStack() as marker_pin:
        _, directory_id = pins.enter_context(api.owners.pin_path(api.jobs, area, True))
        original_marker = api.owners.pin_new_marker(marker_pin, api.jobs, marker, token)
        report["temporaryDirectoryId"] = directory_id
        try:
            yield area
        finally:
            if marker.read_text(encoding="ascii") != token:
                raise RuntimeError("The private fixture lost its original owner marker")
            for file in area.iterdir():
                if file.name not in RECORDS or not file.is_file() or file.lstat().st_file_attributes & 0x400:
                    raise RuntimeError("An unknown file appeared in the private fixture directory")
            # The directory handle prevents a rename while deleting the known files and pinned marker.
            for name in RECORDS - {marker.name}:
                (area / name).unlink(missing_ok=True)
            marker_pin.close()
            remove_original(marker, False, original_marker)
            pins.close()
            remove_original(area, True, directory_id)
            report["temporaryDirectoryRemoved"] = True


def received(area, stage, duration, proc):
    path = area / stage
    until = time.monotonic() + duration
    while not path.is_file():
        if proc.poll() is not None or time.monotonic() >= until:
            raise Unavailable(f"The Rust receiver did not produce the {stage} observation")
        time.sleep(.02)
    return [int(word) for word in path.read_text(encoding="ascii").split()]


def snapshot(area, name, proc, report):
    values = received(area, name, 8, proc)
    if len(values) != 10 or values[0] != proc.pid or values[1] <= 0 or values[2] != ICON:
        raise ValueError("Invalid source identity in the Rust tray observation")
    item = {"pid": values[0], "hwnd": values[1], "iconId": values[2], "ready": values[3] == 1,
            "hresult": values[4], "rect": values[5:9], "opensBeforeInput": values[9]}
    report[name] = item
    if not item["ready"]:
        raise Unavailable(f"The named desktop Shell declined the {name} icon operation")
    if item["opensBeforeInput"]:
        raise Unavailable("The Rust receiver already had an activation before observer input")
    return item


def wait_color(sample, rgb, duration, record):
    until = time.monotonic() + duration
    while time.monotonic() < until:
        try:
            value = sample()
            record["lastSample"] = value
            if matches(value["rgb"], rgb):
                return value
        except Unavailable as error:
            record["lastUnavailable"] = str(error)
        time.sleep(.08)
    return None


@contextmanager
def overflow(host, area, api, bar, pid, record):
    if host == "-":
        raise Unavailable("No presentation of the fixture pixel and no functioning system UI Automation host")
    allowed = [Path(path).resolve() for name in ("powershell.exe", "pwsh.exe") if (path := shutil.which(name))]
    if Path(host).resolve(strict=True) not in allowed:
        raise ValueError("The optional overflow observer must use the probed system PowerShell")
    api.validate_bar(bar, pid)
    args = [host, "-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass", "-File",
            HERE / "activation-overflow.ps1", "-Desktop", api.name, "-Area", area, "-Bar", str(bar), "-ShellPid", str(pid)]
    with api.launch_child(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=area, creationflags=subprocess.CREATE_NO_WINDOW) as proc:
        try:
            until = time.monotonic() + 36
            ready = area / "overflow.ready"
            record["ready"], record["startTimedOut"] = False, False
            while time.monotonic() < until:
                if ready.is_file():
                    record["ready"] = ready.read_bytes() == b"ready"
                    break
                if proc.poll() is not None:
                    break
                time.sleep(.08)
            else:
                record["startTimedOut"] = True
            if not record["ready"]:
                raise RuntimeError("The private overflow helper did not confirm readiness")
            yield
        finally:
            (area / "release-menu").touch()
            try:
                out, err = proc.communicate(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate(timeout=6)
                record["timedOut"] = True
            record["exit"] = proc.returncode
            if out.strip():
                try:
                    record["provider"] = json.loads(out.decode("utf-8-sig"))
                except (UnicodeError, ValueError):
                    record["invalidProviderOutput"] = True
            if err.strip():
                record["diagnostic"] = err.decode("utf-8", errors="replace")[-600:]
            provider = record.get("provider")
            if (proc.returncode != 0 or record.get("timedOut") or record.get("startTimedOut") or not record.get("ready")
                    or err.strip() or not isinstance(provider, dict) or provider.get("completed") is not True
                    or provider.get("providerReady") is not True or "operationError" in provider or "restoreError" in provider):
                raise RuntimeError("The private overflow helper failed, timed out or returned an incomplete result")
            action = provider.get("overflow")
            if action == "requested":
                if (provider.get("releaseAcknowledged") is not True or provider.get("overflowClosed") is not True
                        or provider.get("restoreOutcome") != "verified closed"):
                    raise RuntimeError("The helper did not confirm restoration of the fixture's opened flyout")
            elif (action not in ("unchanged", "already visible") or provider.get("restoreOutcome") != "untouched"
                    or "overflowClosed" in provider or "releaseAcknowledged" in provider):
                raise RuntimeError("The overflow helper could not establish the original flyout state")


def gesture(api, sample, target, proc, area, record):
    saved = w.POINT()
    check(api.cursor(c.byref(saved)), "GetPhysicalCursorPos(private desktop)")
    live = sample()
    if not same_spot(live, target) or not matches(live["rgb"], expected_colors(api.name[6:])[1]):
        raise Unavailable("The independently observed icon moved before pointer placement")
    api.require_desktop()
    check(api.move(*target["center"]), "SetPhysicalCursorPos(verified private icon)")
    try:
        api.input_pair(sample, target, record, "first")
        until = time.monotonic() + .08
        while time.monotonic() < until and not (area / "callback").is_file():
            time.sleep(.005)
        if not (area / "callback").is_file():
            # The shipping Shell handler also accepts a double click. Re-prove ownership before each pair.
            double_interval = api.double_time()
            if elapsed_ticks(api.tick(), record["firstStartTick"]) < double_interval:
                try:
                    api.input_pair(sample, target, record, "second", double_interval)
                except Unavailable as error:
                    # A single-click activation may have closed its overflow while dispatch was in flight.
                    record["secondWithheld"] = str(error)
        event = received(area, "callback", 3.5, proc)
        record["callbackReadTick"] = api.tick()
        record["callback"] = dict(zip(("count", "code", "iconId", "messageTick32", "buttonUps",
                                       "dispatchTick64", "threadLastMessageTick32"), event))
        message_tick = callback_tick(event, record["firstReturnedTick"], record["callbackReadTick"], record.get("secondReturnedTick"))
        record["callback"]["qualifiedMessageTick64"] = message_tick
        if message_tick is None:
            raise Unavailable("The callback lacked a matching queued activation with a provable timestamp after input")
    finally:
        if record.get("incompleteInput"):
            # Further pointer movement could drag a queued button-down. Preserve its hard failure.
            record["cursorRestoreWithheldAfterIncompleteInput"] = True
        else:
            api.require_desktop()
            now = w.POINT()
            check(api.cursor(c.byref(now)), "GetPhysicalCursorPos(before cleanup)")
            if [now.x, now.y] == target["center"]:
                check(api.move(saved.x, saved.y), "SetPhysicalCursorPos(restore fixture cursor)")
                record["cursorRestored"] = True
            else:
                record["cursorMovedIndependently"] = True
                raise Unavailable("The fixture cursor moved independently before cleanup")


def challenge(api, area, host, proc, shell, job, report):
    first = snapshot(area, "first", proc, report)
    bar, pid = shell
    def sample():
        return api.sample(proc, first["hwnd"], bar, pid)
    def exclusive_sample():
        api.visible_owners(job, proc, report.setdefault("privateWindowOwners", {}))
        return sample()
    before, after = expected_colors(api.name[6:])
    report["expectedRgb"] = [before, after]
    with ExitStack() as states:
        p0 = wait_color(sample, before, 2, report.setdefault("firstColor", {}))
        if p0 is None:
            states.enter_context(overflow(host, area, api, bar, pid, report.setdefault("overflow", {})))
            p0 = wait_color(sample, before, 4, report["firstColor"])
        if p0 is None:
            raise Unavailable("The registered fixture's first colored center was not independently visible")
        (area / "change").touch()
        second = snapshot(area, "second", proc, report)
        p1 = wait_color(sample, after, 4, report.setdefault("secondColor", {}))
        if (not p1 or not same_spot(p0, p1) or second["hresult"] != 0 or second["rect"] != p1["rect"]
                or second["hwnd"] != first["hwnd"]):
            raise Unavailable("The color change did not identify the same visible slot and native icon rectangle")
        (area / "arm").touch()
        armed = snapshot(area, "armed", proc, report)
        if armed["hresult"] or armed["rect"] != p1["rect"] or armed["hwnd"] != first["hwnd"]:
            raise Unavailable("The receiver's icon rectangle changed before arming input")
        gesture(api, exclusive_sample, p1, proc, area, report.setdefault("input", {}))


def trial(target, name, host, output, report):
    if not hosted(target) or not re.fullmatch(r"IfwQa_[a-f0-9]{32}", name):
        raise ValueError("A hosted private Windows rewrite runner and fresh named desktop are required")
    api = Native(name)
    api.require_desktop()
    report["privateContext"] = api.desk.context()
    previous = check(api.desk.awareness(-4), "SetThreadDpiAwarenessContext(per-monitor-v2)")
    try:
        token = name[6:]
        exe, original = paths(target)
        base = json.loads((original / "result.json").read_text(encoding="utf-8"))
        if sha(exe) != base["probeSha256"]:
            raise ValueError("The native fixture no longer matches the original build")
        with private_area(api, token, report) as area, api.own_explorer(area, report.setdefault("explorer", {})) as job:
            with api.shell_owner(job, report["explorer"]) as shell, (output / "native.txt").open("xb") as log:
                api.validate_bar(*shell)
                with api.launch_child([exe, "--hosted-private-tray", area, token, "private"], cwd=area,
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                      creationflags=subprocess.CREATE_NO_WINDOW) as proc:
                    try:
                        if api.shell_path(int(proc._handle)) != exe:
                            raise ValueError("The pinned native receiver image changed")
                        report["subject"] = {"pid": proc.pid, "creationFileTime": api.jobs.process_identity(int(proc._handle))}
                        challenge(api, area, host, proc, shell, job, report)
                    finally:
                        (area / "finish").touch()
                        try:
                            report["subjectExit"] = proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
                            raise RuntimeError("The native receiver did not finish its own icon cleanup")
                        log.flush()
                        metrics = module("service_readback", HERE / "run.py").read_native(output / "native.txt")
                        report["native"] = metrics
                        if (proc.returncode or metrics.get("private_tray.synthetic_open") != 0 or
                                (metrics.get("private_tray.initial.add") and metrics.get("private_tray.remove") is not True)):
                            raise RuntimeError("The native receiver, callback isolation or icon removal failed")
                    if metrics.get("private_tray.pointer_open", 0) < 1:
                        raise RuntimeError("The receiver did not retain the independently observed activation")
    finally:
        check(api.desk.awareness(previous), "SetThreadDpiAwarenessContext(restore)")


def main():
    target, name, host = sys.argv[1:]
    if not hosted(target):
        raise ValueError("The private worker requires the matching hosted rewrite runner")
    output = paths(target)[1] / "activation"
    report = {"status": "failed", "desktop": name, "target": target, "workerPid": os.getpid()}
    try:
        trial(target, name, host, output, report)
        report["status"] = "passed"
    except Unavailable as error:
        report["status"], report["reason"] = "unavailable", str(error)
    except Exception:
        report["error"] = traceback.format_exc(limit=6)
    finally:
        write(output / "worker.json", report)
    return {"passed": 0, "unavailable": 2, "failed": 1}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
