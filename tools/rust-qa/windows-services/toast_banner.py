"""Observe the existing normal WinRT sender on its disposable Default input desktop."""

from contextlib import ExitStack
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess

from activation import HERE, write
from notification_probe import (arm_event, child, events, ordinary_console, owned_directory,
                                select_powershell, timed_presentation, wait_for_observer)

SOURCE = "tools/rust-qa/windows-services/toast_banner.py"
CLOCK_KEYS = ("showFrequency", "showBeginQpc", "showEndQpc")


def show_timing(item):
    fields = item["fields"]
    if "show" not in item["phases"]:
        if any(k in fields for k in CLOCK_KEYS):
            raise ValueError("Unexpected counters for an unissued WinRT Show")
        return None
    keys = list(fields)
    start = keys.index("showHresult") + 1
    if (keys[start:start + 3] != list(CLOCK_KEYS) or
            any(not re.fullmatch(r"[1-9][0-9]{0,18}", fields[k]) for k in CLOCK_KEYS)):
        raise ValueError("Missing the original WinRT Show counter interval")
    frequency, begin, end = (int(fields[k]) for k in CLOCK_KEYS)
    if end < begin or max(frequency, begin, end) >= 1 << 63:
        raise ValueError("Invalid WinRT Show counters")
    return frequency, begin, end


def assess(receipt, rows, sender, item, session, machine):
    if (sender["operation"] != "post-normal" or receipt["senderLog"] != sender["log"]
            or receipt["senderIdentity"] != [sender["pid"], sender["creation100ns"]]
            or receipt["aumid"] != item["fields"]["aumid"] or item["fields"]["operation"] != "post-normal"):
        raise ValueError("The popup observation does not describe the exact normal WinRT sender")
    provider = receipt.get("observer")
    if provider is None:
        if rows or receipt.get("observerLog") is not None:
            raise ValueError("Unexpected sweeps without an independent observer")
    elif (provider.get("jobEmpty") is not True or provider.get("forced") or tuple(provider["machine"]) != (machine, machine)
            or any(type(provider[k]) is not int or provider[k] <= 0 for k in ("pid", "creation100ns"))
            or provider["pid"] == sender["pid"] or provider["exit"] not in (0, 2)
            or not rows or rows[-1].get("stage") not in ("visible", "unavailable")
            or (provider["exit"] == 0) != (rows[-1]["stage"] == "visible")):
        raise ValueError("The separate native popup observer did not drain normally")
    if any(c["session"] != session or not ordinary_console(c, "Default")
           for c in (receipt["desktopBefore"], receipt["desktopAfter"])):
        return {"status": "unavailable", "reason": "The original Default console was unavailable"}
    if provider is None:
        return {"status": "unavailable", "reason": "No native UI Automation observer was available"}
    timing = show_timing(item)
    if (timing is None or item["hresult"] is not None or item["postResult"]["showHresult"] is None
            or item["fields"].get("showReturned") != "true" or item["fields"].get("suppressPopup") != "false"):
        return {"status": "unavailable", "reason": "The normal sender did not complete a permitted WinRT Show"}
    if not rows or not receipt.get("armBeforeRequest") or rows[-1].get("complete") is not True:
        if provider["exit"] == 0:
            raise ValueError("A successful popup observer omitted its complete, armed raw interval")
        return {"status": "unavailable", "reason": "The independent observer did not cover the normal WinRT Show"}
    if "releaseQpc" not in receipt:
        raise ValueError("Missing the normal sender release")
    counter, begin, end = timing
    token = item["fields"]["aumid"].removeprefix("IFW.RustQA.Toast.")
    if not PureWindowsPath(receipt["windowsDirectory"]).is_absolute():
        raise ValueError("Missing the original Windows directory")
    clocks = dict(receipt)
    event = timed_presentation(rows, token, session, receipt["windowsDirectory"], clocks, counter,
                               (begin, end), winrt_normal=True)
    if (event is None or "samplingWindow" not in clocks or provider["exit"] !=
            (0 if event.get("providerStage", event["stage"]) == "visible" else 2)):
        raise ValueError("The provider exit differs from its recorded physical sweeps")
    return {"status": "visible" if event["stage"] == "visible" and "match" in event else "unavailable",
            "presentation": event, "samplingWindow": clocks["samplingWindow"]}


def observe(api, desktop, area, env, out, index, token, sender, send, session, *, isolated_vm=False):
    basename = f"{index:03}-normal-popup"
    raw_log = out / (basename + ".log")
    receipt = dict(senderLog=sender["log"], aumid="IFW.RustQA.Toast." + token, qpcFrequency=api.frequency,
                   windowsDirectory=os.environ["SystemRoot"], desktopBefore=desktop.context())
    try:
        with ExitStack() as stack:
            provider = None
            if receipt["desktopBefore"]["session"] == session and ordinary_console(receipt["desktopBefore"], "Default"):
                program, receipt["uiaHosts"] = select_powershell(area, "accessibility", env)
                if program:
                    controls = stack.enter_context(owned_directory(api, area, "ifw-rw02-" + token))
                    args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
                            "-File", str(HERE / "notification.ps1"), "-Token", token, "-Fixture", str(area),
                            "-Kind", "WinrtNormal"]
                    if isolated_vm:
                        args.append("-IsolatedVm")
                    receipt.update(observer={}, observerLog=raw_log.name)
                    provider = stack.enter_context(child(api, Path(program), args, area, env, raw_log, receipt["observer"]))
                    # Signal before draining the process, including a disabled sender or a failed read.
                    stack.callback((controls / "notice.finish").touch, exist_ok=True)
                    try:
                        if wait_for_observer(raw_log, provider) and ordinary_console(desktop.context(), "Default"):
                            receipt["armBeforeRequest"] = arm_event(events(raw_log))
                    except TimeoutError:
                        pass
            if receipt.get("armBeforeRequest"):
                receipt["releaseQpc"] = api.clock()
                (controls / "notice.go").touch(exist_ok=False)
            item = send()
            if receipt.get("armBeforeRequest") and item.get("postResult", {}).get("showHresult") is not None:
                receipt["acknowledgedQpc"] = api.clock()
                marker = controls / "notice.sent.pending"
                marker.write_text(token, encoding="ascii")
                marker.rename(controls / "notice.sent")
                try:
                    provider.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        receipt["finishQpc"] = api.clock()
        receipt["desktopAfter"] = desktop.context()
        if "pid" in sender:
            receipt["senderIdentity"] = [sender["pid"], sender["creation100ns"]]
        write(out / (basename + ".json"), receipt)
    try:
        result = assess(receipt, events(raw_log) if raw_log.exists() else [], sender, item, session, sender["machine"][0])
    except (KeyError, TypeError, ValueError) as exc:
        # Let the ordinary independent history reads and exact removals finish. Replay rejects invalid evidence.
        result = {"status": "invalid", "reason": str(exc)}
    return item, result


def archived(directory, index, sender, item, session, machine):
    prefix = f"{index:03}-normal-popup"
    filename = prefix + ".json"
    if not (directory / filename).is_file():
        raise ValueError("Missing the separate WinRT popup observation")
    receipt = json.loads((directory / filename).read_bytes())
    files, rows = {filename}, []
    if "observerLog" in receipt:
        log = prefix + ".log"
        if receipt["observerLog"] != log or not (directory / log).is_file():
            raise ValueError("Unexpected name for the raw popup observer log")
        files.add(log)
        rows = events(directory / log)
    return files, assess(receipt, rows, sender, item, session, machine)
