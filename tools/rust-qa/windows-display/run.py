"""Measure the canonical Windows GUI on the displays and transport of an existing test session."""

import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import json
import math
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
sys.path[:0] = [str(QA / "windows-text"), str(QA / "windows-desktop"), str(QA / "windows-performance"), str(QA)]
from native import Win32, pin_path, start_owned_subject
from storage.evidence import sha256, write_json
from win32 import Desktop, check, rect_values
from worker import hosted, powershell, shared_windows
from windows_observer import select_powershell
from topology import Topology, active_input, contains, physical_coordinates, protocol

TEXT = runpy.run_path(str(QA / "windows-text/run.py"))
FIRST, SECOND = "IFW MMMM 27.jpg", "IFW IIII 27.jpg"


def wait_for(read, label, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if value:
            return value
        time.sleep(.075)
    raise TimeoutError("Waiting for " + label)


def environment(profile):
    keys = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "PROGRAMFILES",
            "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
            "COMMONPROGRAMW6432", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keys}
    env.update(USERPROFILE=str(profile), HOME=str(profile), TEMP=str(profile), TMP=str(profile),
               IFW_QA_ISOLATED="1", WGPU_DX12_COMPILER="Fxc", POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
    for key in ("APPDATA", "LOCALAPPDATA"):
        (profile / key).mkdir()
        env[key] = str(profile / key)
    return env


def owned_layout(api, display, hwnd, pid):
    owner = w.DWORD()
    if not api.owner(hwnd, c.byref(owner)) or owner.value != pid or not api.visible(hwnd):
        raise RuntimeError("Expected the sole visible window of the pinned Rust process")
    outer, client = w.RECT(), w.RECT()
    check(api.window_rect(hwnd, c.byref(outer)), "GetWindowRect")
    check(api.client_rect(hwnd, c.byref(client)), "GetClientRect")
    top, bottom = w.POINT(client.left, client.top), w.POINT(client.right, client.bottom)
    check(api.to_screen(hwnd, c.byref(top)), "ClientToScreen(top)")
    check(api.to_screen(hwnd, c.byref(bottom)), "ClientToScreen(bottom)")
    return {"pid": pid, "hwnd": hwnd, "session": api.pid_session(pid), "monitor": hex(check(
            display.from_window(hwnd, 0), "MonitorFromWindow")), "dpi": api.dpi(hwnd), "awareness": display.awareness(hwnd),
            "perMonitorV2": bool(display.equal_context(display.get_context(hwnd), -4)),
            "outer": rect_values(outer), "client": [top.x, top.y, bottom.x, bottom.y],
            "dwmFrame": api.dwm(hwnd, 9, w.RECT()), "dwmCloaked": api.dwm(hwnd, 14, w.DWORD())}


def choose_monitor(inventory, current):
    monitors = inventory["monitors"]
    source = next((m for m in monitors if m["handle"] == current), None)
    if source is None:
        raise ValueError("The application HWND does not occupy an enumerated display")
    for other in monitors:
        if other["handle"] != current and other["dpi"] != source["dpi"]:
            return source, other
    return source, None


def monitor_state(inventory):
    return {m["handle"]: (m["bounds"], m["work"], m["dpi"], m["primary"]) for m in inventory["monitors"]}


def field_geometry(stage, layout, monitor, initial):
    if (stage.get("status") != "observed" or stage.get("pid") != layout["pid"] or stage.get("hwnd") != layout["hwnd"]
            or stage.get("field") != "Dateiname" or stage.get("expectedText") != initial or stage.get("dpi") != layout["dpi"]
            or layout["awareness"] != 2 or layout["monitor"] != monitor["handle"] or layout["dpi"] != monitor["dpi"]
            or not contains(layout["client"], stage["rect"]) or not contains(monitor["bounds"], stage["rect"])):
        raise ValueError("The measured UIA filename, app HWND, physical geometry or monitor DPI differs")
    rect = stage["rect"]
    return {"logicalFieldSizeAt96": [round((rect[2] - rect[0]) * 96 / layout["dpi"], 3),
                                     round((rect[3] - rect[1]) * 96 / layout["dpi"], 3)]}


def scaled_geometry(original, moved):
    factor = moved["dpi"] / original["dpi"]
    if factor == 1:
        raise ValueError("The window did not change DPI")
    measurements = {}
    for label, key, axis, rounding in (("fieldHeight", "rect", 1, 1), ("prefixHeight", "prefixRect", 1, 1),
                                      ("prefixWidth", "prefixRect", 0, 3)):
        a, b = original[key], moved[key]
        old, new = a[axis + 2] - a[axis], b[axis + 2] - b[axis]
        # Both physical measurements include pixel rounding. The fixed width covers three glyph advances.
        limit = rounding * (1 + factor)
        if old <= 0 or new <= 0 or abs(new - factor * old) > limit:
            raise ValueError(f"The measured physical {label} does not follow the monitor DPI change")
        measurements[label] = {"before": old, "after": new, "expected": old * factor, "rounding": limit}
    return measurements


def frame_evidence(record, profile, screen_dpi):
    if not (record["focusAtEntry"] is True and record["focusAtExit"] is True and record["textAfter"] == SECOND
            and record["expectedText"] == FIRST and record["before"]["width"] == record["after"]["width"]
            and record["before"]["height"] == record["after"]["height"] and record["before"]["sha256"] != record["after"]["sha256"]):
        raise ValueError("The preserved focus, text or fixed native crop changed unexpectedly")
    delta = record["difference"]
    if (not math.ceil(6 * screen_dpi / 96) <= delta["columns"] <= record["after"]["width"]
            or not math.ceil(3 * screen_dpi / 96) <= delta["rows"] <= record["after"]["height"]
            or not max(delta["rows"], delta["columns"]) <= delta["pixels"] <= delta["rows"] * delta["columns"]):
        raise ValueError("Stationary glyph differences do not extend beyond the blinking caret")
    if record["phase"] not in ("Frame", "SourceFrame"):
        raise ValueError("Unexpected private field capture role")
    images = []
    for role in ("before", "after"):
        image = profile / (record["phase"] + ".json." + role + ".png")
        with image.open("rb") as stream:
            head = stream.read(24)
        expected = record[role]
        if (sha256(image) != expected["sha256"] or head[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"
                or int.from_bytes(head[16:20], "big") != expected["width"] or int.from_bytes(head[20:24], "big") != expected["height"]
                or not 0 < expected["width"] <= 1024 or not 0 < expected["height"] <= 128):
            raise ValueError("The independently hashed synthetic field frame differs")
        images.append(image)
    return images


def stop_subject(proc, _rust):
    if proc.poll() is None:
        try:
            proc.stdin.write(b"Q")
            proc.stdin.flush()
            proc.wait(timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait(timeout=10)


def measure(target, output, profile, report, *, require_interactive):
    api, display, processes = Desktop(), Topology(), Win32()
    binary = TEXT["DESKTOP"]["GUI_BINARY"].resolve(strict=True)
    env = environment(profile)
    with ExitStack() as resources:
        resources.enter_context(physical_coordinates(api))
        resources.enter_context(pin_path(processes, binary, False))
        report["build"] = TEXT["check_build"](target, binary, output.parent)
        context = api.context()
        report["desktop"] = {**context, **{key: (context[key] if context[key] in ("Default", "WinSta0") else "other")
                                           for key in ("inputDesktop", "threadDesktop", "windowStation")}}
        transport = report["protocol"] = protocol(api, context["session"])
        report["rdpSessionObserved"] = None if transport["status"] != "observed" else transport["code"] == 2
        if require_interactive and not active_input(context, transport):
            raise RuntimeError("The selected test VM must already have an active, unlocked console or RDP input desktop")
        inventory = report["topology"] = display.inventory(api)
        ps, attempts = select_powershell(profile, "accessibility")
        report["observerHosts"] = [{k: v for k, v in row.items() if k != "diagnostic"} for row in attempts]
        if not ps:
            raise RuntimeError("The system UI Automation observer could not start")
        log = output / "subject.log"
        stream = resources.enter_context(log.open("wb"))
        child = None
        def exited():
            if child:
                report["subjectExit"] = child.poll()
                report["drained"] = any(s.startswith("DRAINED passes=") for s in logs())
        def logs():
            return log.read_text(encoding="utf-8", errors="replace").splitlines()
        resources.callback(exited)
        child = start_owned_subject(resources, processes, binary, profile, env, stream, True, stop_subject)
        observer = shared_windows()(child.pid, api.thread_desktop(api.thread()))
        resources.callback(observer.close)
        processes.resume_owned_process(child.pid)
        child.stdin.write(b"T")
        child.stdin.flush()
        def visible():
            if child.poll() is not None:
                raise RuntimeError("Rust GUI exited before the requested observation")
            return observer.visible(waiting_for_first=True)
        hwnd = wait_for(visible, "owned visible Rust assessment HWND")
        try:
            adapter = wait_for(lambda: next((s for s in logs() if s.startswith("ADAPTER Dx12 ")), None), "native DX12 adapter")
            report["adapter"] = adapter
            base = report["originalWindow"] = owned_layout(api, display, hwnd, child.pid)
            if base["session"] != context["session"]:
                raise RuntimeError("The Rust window is outside the observer's existing session")
            if report["rdpSessionObserved"]:
                report["rdpRenderer"] = {"session": base["session"], "hwnd": hwnd, "adapter": adapter, "dpi": base["dpi"]}
            source, destination = choose_monitor(inventory, base["monitor"])
            def input_available():
                now = api.context()
                return now["session"] == context["session"] and protocol(api, now["session"]) == transport and active_input(now, transport)
            def stage(name, layout, monitor, expected):
                if visible() != hwnd or (name != "Read" and not input_available()):
                    raise RuntimeError("The owned HWND, input desktop or WTS transport changed")
                record_path = profile / (name + ".json")
                code = powershell(ps, HERE / "field.ps1", ["-SubjectId", child.pid, "-WindowHandle", hwnd,
                                  "-Phase", name, "-OutputFile", record_path], env, profile, output / (name + ".log"), 75)
                record = report.setdefault("stages", {})[name] = json.loads(record_path.read_text(encoding="utf-8-sig"))
                if code or record.get("phase") != name:
                    raise RuntimeError("UIA " + name + " failed: " + record.get("error", "unknown observer error"))
                record.update(field_geometry(record, layout, monitor, expected))
                return record
            initial = TEXT["PLAN"]["initial"]
            stage("Read", base, source, initial)
            config = inventory["displayConfig"]
            if (config["status"] == "failed" or (config["status"] == "observed" and
                    not any(row.get("monitor") == source["index"] and row["active"] for row in config["paths"]))):
                raise RuntimeError("The active DisplayConfig query or source-to-HMONITOR observation failed")
            if destination and config["status"] == "observed" and not any(
                    row.get("monitor") == destination["index"] and row["active"] for row in config["paths"]):
                raise RuntimeError("The different-DPI destination has no matching active DisplayConfig path")
            report["inventoryPassed"] = True
            rdp = report["rdpSessionObserved"]
            if not destination:
                report["mixedDpiReason"] = "Only one active monitor" if len(inventory["monitors"]) == 1 else "All active monitors have the same window DPI"
            if not rdp:
                report["rdpReason"] = "The current WTS protocol did not report RDP"
            if not input_available():
                report["interactionPrerequisite"] = "An unlocked existing Default input desktop receiving input is required"
            else:
                def record_frame(name, layout, monitor):
                    frame = stage(name, layout, monitor, FIRST)
                    for image in frame_evidence(frame, profile, layout["dpi"]):
                        shutil.copyfile(image, output / image.name)
                    if not input_available() or owned_layout(api, display, hwnd, child.pid) != layout:
                        raise RuntimeError("Session, monitor or physical window metrics changed during the stationary frame control")
                    return frame

                if destination:
                    report["mixedDpiPassed"] = False
                if rdp:
                    report["rdpRenderingObserved"] = False
                report["sourceFrameObserved"] = False
                try:
                    prime = stage("Prime", base, source, initial)
                    if not prime["focusAtExit"] or prime["textAfter"] != FIRST:
                        raise RuntimeError("Could not establish native filename focus and initial text")
                    on_source = record_frame("SourceFrame", base, source)
                    if on_source.get("textRestored") != FIRST:
                        raise ValueError("The frame control did not restore the fixed filename")
                    report["sourceFrameObserved"] = True
                    if rdp:
                        report["rdpRenderingObserved"] = True
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
                    report["sourceFrameError"] = str(error)
                    if destination or rdp:
                        raise

                if destination:
                    if visible() != hwnd or not input_available() or owned_layout(api, display, hwnd, child.pid) != base:
                        raise RuntimeError("The subject or display changed before the move")
                    work = destination["work"]
                    scale = destination["dpi"] / source["dpi"]
                    width, height = base["outer"][2] - base["outer"][0], base["outer"][3] - base["outer"][1]
                    left = work[0] + max(0, round((work[2] - work[0] - width * scale) / 2))
                    top = work[1] + max(0, round((work[3] - work[1] - height * scale) / 2))
                    # Position only this verified HWND. Windows and winit choose its new size.
                    check(api.position(hwnd, None, left, top, 0, 0, 0x215), "SetWindowPos(owned Rust HWND)")
                    def moved():
                        current = owned_layout(api, display, hwnd, child.pid)
                        return current if current["monitor"] == destination["handle"] and current["dpi"] == destination["dpi"] else None
                    current = report["movedWindow"] = wait_for(moved, "the same HWND at its new monitor DPI")
                    frame = record_frame("Frame", current, destination)
                    report["physicalScaling"] = scaled_geometry(prime, frame)
                    after = report["topologyAfterInteraction"] = display.inventory(api)
                    if monitor_state(after) != monitor_state(inventory):
                        raise RuntimeError("The active monitor inventory changed during this observation")
                    report["mixedDpiPassed"] = True
        finally:
            if child.poll() is None and observer.visible() == hwnd:
                observer.close_window(hwnd)
                def hidden():
                    return observer.visible() is None and any(line.startswith("WINDOW_RELEASED passes=") for line in logs())
                report["closedToSupervisor"] = bool(wait_for(hidden, "native close and renderer release"))
    if report["subjectExit"] or not report["drained"] or not report.get("closedToSupervisor"):
        raise RuntimeError("The owned Rust supervisor did not close and drain normally")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TEXT["TARGETS"]))
    parser.add_argument("--isolated-vm", action="store_true", help="explicitly authorized disposable Windows VM and current test desktop")
    args = parser.parse_args()
    hosted_job = hosted() and os.getenv("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch" and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust"
    if (os.name != "nt" or not (hosted_job or args.isolated_vm)
            or (os.getenv("GITHUB_ACTIONS") == "true" and not hosted_job)):
        parser.error("Use the native rewrite job or an expressly authorized isolated Windows test VM")
    output = ROOT / "artifacts/rust/gui-native" / args.target / "windows-display"
    output.mkdir(exist_ok=False)
    inputs = [*sorted(HERE.glob("*.py")), HERE / "field.ps1", QA / "windows-text/run.py", QA / "windows-text/evidence.py",
              QA / "windows-text/Pointer.cs", QA / "windows-performance/native.py", QA / "observe-windows-gui.py",
              QA / "observe-windows-input.ps1", QA / "windows_observer.py", QA / "windows-desktop/run.py",
              QA / "windows-desktop/win32.py", QA / "windows-desktop/worker.py"]
    report = {"status": "failed", "target": args.target, "run": os.getenv("GITHUB_RUN_ID"), "attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
              "inventoryPassed": False, "sourceFrameObserved": None, "mixedDpiPassed": None, "rdpRenderingObserved": None,
              "inputs": {p.relative_to(ROOT).as_posix(): sha256(p) for p in inputs}}
    profile = None
    try:
        with tempfile.TemporaryDirectory(prefix="ifw-display-", dir=output) as tmp:
            profile = Path(tmp)
            measure(args.target, output, profile, report, require_interactive=not hosted_job)
        report["status"] = "observed"
    except Exception:
        report["error"] = traceback.format_exc()
    report["profileRemoved"] = None if profile is None else not profile.exists()
    write_json(output / "result.json", report)
    (output / "evidence.sha256").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file()),
                                           encoding="utf-8", newline="\n")
    print(report.get("error") or f"Inventory observed, mixed DPI={report['mixedDpiPassed']}, RDP rendering={report['rdpRenderingObserved']}")
    return 0 if report["status"] == "observed" and report["inventoryPassed"] and report["profileRemoved"] else 1


if __name__ == "__main__":
    sys.exit(main())
