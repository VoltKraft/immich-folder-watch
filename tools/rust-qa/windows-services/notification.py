"""Reobserve a single silent Shell notification late in the original disposable Windows job."""
import argparse
from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import time
import uuid

from activation import DESKTOP, HERE, QA, ROOT, TARGET, hosted, module, paths, sha, write

sys.path.extend([str(QA / "windows-performance"), str(DESKTOP), str(QA / "windows-launcher"), str(QA)])
from build import pe_machine
from named_process import start
from native import CleanupUnconfirmed, Win32, checked, owned_directory, pin_new_marker, pin_path
from win32 import Desktop, bind, ordinary_console
from windows_observer import select_powershell

READ = module("notification_service", HERE / "run.py").read_native
DEPS = [DESKTOP / name for name in ("win32.py", "job.py")] + [
    QA / "windows-launcher/named_process.py", QA / "windows-performance/native.py",
    QA / "windows-performance/build.py", QA / "windows_observer.py"]
STATES = {1: "NOT_PRESENT", 2: "BUSY", 3: "RUNNING_D3D_FULL_SCREEN", 4: "PRESENTATION_MODE",
          5: "ACCEPTS_NOTIFICATIONS", 6: "QUIET_TIME", 7: "APP"}


def source_files():
    local = [*HERE.glob("*.py"), *HERE.glob("*.ps1"), *(HERE / "src").glob("*.rs"),
             HERE / "Cargo.toml", HERE / "Cargo.lock", HERE / "inputs.json"]
    return local + [QA / "gui/src/tray-icon.argb", QA / "gui/src/windows_tray_shell.rs",
                    QA / "audit-graph.py", QA / "check-toolchain.py", ROOT / "rust/toolchain-inputs.json"]


def bind_build(target, exe, original, record):
    file = original / "result.json"
    early = json.loads(file.read_bytes())
    pins = json.loads((HERE / "inputs.json").read_bytes())
    compiler = json.loads((ROOT / "rust/toolchain-inputs.json").read_bytes())
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (early["hosted"] is not True or source != early["head"] or source != os.environ["GITHUB_SHA"]
            or early["target"] != target or early["workflowRun"] != os.environ["GITHUB_RUN_ID"]
            or early["workflowAttempt"] != os.environ["GITHUB_RUN_ATTEMPT"] or early["runner"] != os.environ["RUNNER_NAME"]
            or early["probeSha256"] != sha(exe) or early["locked"] != pins["lockSha256"]
            or early["canonicalGraphSha256"] != pins["targetGraphs"][target]
            or any(type(early["steps"].get(key)) is not int or early["steps"][key] != 0
                   for key in ("compiler", "inventory", "format", "clippy", "balloon-id", "build"))):
        raise ValueError("The completed early native build did not identify this job, revision and qualified binary")
    for path in source_files():
        if early["sourceFiles"][path.relative_to(ROOT).as_posix()] != sha(path):
            raise ValueError(f"Early service input changed: {path.name}")
    verified = {}
    for name in ("compiler.txt", "graph.json", "build.txt", "balloon-id.txt"):
        digest = sha(original / name)
        if digest != early["evidenceFiles"][name]:
            raise ValueError(f"Early native evidence changed: {name}")
        verified[name] = digest
    version = dict(row.split(": ", 1) for row in (original / "compiler.txt").read_text(encoding="utf-8").splitlines() if ": " in row)
    graph = json.loads((original / "graph.json").read_bytes())
    canonical = hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if ((version["host"], version["release"], version["commit-hash"]) != (target, compiler["version"], compiler["commit"])
            or canonical != pins["targetGraphs"][target]):
        raise ValueError("The early compiler identity or dependency graph differed from the reviewed target")
    control = (original / "balloon-id.txt").read_text(encoding="utf-8")
    if not re.search(r"^test [\w:]+::balloon_callbacks_belong_to_the_registered_v4_icon \.\.\. ok$", control, re.M):
        raise ValueError("The early native test did not execute the version-4 callback identity control")
    record.update(earlyResultSha256=sha(file), binarySha256=early["probeSha256"], compiler=version,
                  earlyEvidence=verified, earlyProbeCompleted=early["probeCompleted"],
                  earlyMeasureUptimeMs=early["measureUptimeMs"], graphSha256=canonical,
                  observerInputs={p.relative_to(ROOT).as_posix(): sha(p) for p in [*source_files(), *DEPS]})
    if "native.txt" in early["evidenceFiles"]:
        native = original / "native.txt"
        if sha(native) != early["evidenceFiles"]["native.txt"]:
            raise ValueError("The retained early service observation changed")
        observed = READ(native)
        record["earlyNotification"] = {key: observed.get(key) for key in (
            "tray.notification_state", "tray.notification_state_hresult", "tray.initial.add",
            "tray.notification_request", "tray.callbacks.balloon_show")}
        record["earlyNotification"]["nativeSha256"] = sha(native)


def wait(check, label, duration):
    end = time.monotonic() + duration
    while True:
        value = check()
        if value:
            return value
        if time.monotonic() >= end:
            raise TimeoutError(label)
        time.sleep(.04)


def events(path):
    lines = path.read_bytes().splitlines(keepends=True)
    return [json.loads(row[len(b"NOTICE_OBSERVER "):]) for row in lines
            if row.startswith(b"NOTICE_OBSERVER ") and row.endswith(b"\n")]


@contextmanager
def child(api, exe, args, area, env, log, record):
    job, process = api.new_job(), None
    try:
        with log.open("xb") as stream:
            process = start(exe, args, cwd=area, env=env, stream=stream, desktop="Default", primary=True)
            api.assign_suspended(job, process, exe)
            machine = api.machine(int(process._handle))
            record.update(pid=process.pid, creation100ns=api.process_identity(int(process._handle)), machine=machine)
            if machine != api.machine(-1):
                raise RuntimeError("The observer and the retained subject must execute natively on this runner")
            process.resume()
            yield process
    finally:
        try:
            if process is not None:
                try:
                    record["exit"] = process.wait(timeout=14) if process.poll() is None else process.poll()
                except subprocess.TimeoutExpired:
                    record["forced"] = True
                    process.kill()
                    process.wait(timeout=5)
                if not api.wait_job_empty(job, 3):
                    record["forced"] = True
                    checked(api.terminate_job(job, 1))
                record["jobEmpty"] = api.wait_job_empty(job, 5)
                if not record["jobEmpty"] or record.get("forced"):
                    raise CleanupUnconfirmed("A notification fixture job did not drain naturally")
        finally:
            try:
                if process is not None:
                    process.close()
            finally:
                checked(api.close(job))


def check_match(match, token, session, winroot):
    host = match["host"]
    base = PureWindowsPath(winroot)
    files = {"explorer.exe", "System32/ShellHost.exe", "SystemApps/ShellExperienceHost_cw5n1h2txyewy/ShellExperienceHost.exe",
             "SystemApps/Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy/ShellExperienceHost.exe",
             "SystemApps/MicrosoftWindows.Client.CBS_cw5n1h2txyewy/ShellHost.exe"}
    if (match["desktop"] != "Default" or not match["container"] or host["sameUser"] is not True or host["session"] != session
            or not all(host[key] > 0 for key in ("hwnd", "pid", "creation")) or not host["windowClass"]
            or PureWindowsPath(host["image"]) not in {base / name for name in files}):
        raise ValueError("The visible match did not identify an original same-user Shell notification host")
    for field, expected in (("title", "IFW notice " + token), ("body", "Synthetic IFW notification " + token)):
        item = match[field]
        left, top, right, bottom = item["bounds"]
        x, y = item["point"]
        if (item["text"] != expected or item["pid"] != host["pid"] or item["offscreen"] is not False or not item["runtimeId"]
                or item["nativeHit"] is not True or item["providerHit"] is not True
                or not all(math.isfinite(n) for n in (left, top, right, bottom, x, y))
                or not (left <= x < right and top <= y < bottom)):
            raise ValueError(f"The exact notification {field} lacked independently visible physical bounds")
    if match["title"]["runtimeId"] == match["body"]["runtimeId"]:
        raise ValueError("The title and body resolved to the same accessibility item")


def observed_presentation(items, token, session, winroot, release, finish):
    final = [e for e in items if e["stage"] in ("visible", "unavailable")]
    if len(final) > 1:
        raise ValueError("Ambiguous notification presentation outcome")
    event = final[0] if final else None
    if event is not None and event["stage"] == "visible":
        arms = [e["tick"] for e in items if e["stage"] == "armed" and e["preexistingMatch"] is False]
        if len(arms) != 1 or release is None or not arms[0] <= release <= event["match"]["tick"] <= finish:
            raise ValueError("The visible match was outside the original request and observer interval")
        check_match(event["match"], token, session, winroot)
    return event


def outcome(native, event, token, session, winroot, result):
    observations = result["observations"] = {}
    state = native.get("notice.notification_state")
    observations.update(queryState=state, queryName=STATES.get(state), queryHresult=native.get("notice.notification_state_hresult"),
                        add=native.get("notice.initial.add"), version4=native.get("notice.initial.version4"),
                        requested=native.get("notice.requested"), show=native.get("notice.balloon_show"),
                        hide=native.get("notice.balloon_hide"), timeout=native.get("notice.balloon_timeout"),
                        click=native.get("notice.balloon_click"), independentlyVisible=False)
    if event is not None and event["stage"] == "visible":
        check_match(event["match"], token, session, winroot)
        observations["independentlyVisible"] = True
    if (native.get("notice.pid") != result["subject"]["pid"] or native.get("notice.icon_id") != 23
            or native.get("notice.owner_hwnd") != result["receiver"]["hwnd"]
            or native.get("notice.thread_desktop") != "Default" or native.get("notice.session") != session
            or type(observations["add"]) is not bool or type(observations["requested"]) is not bool
            or (state is None) == (observations["queryHresult"] is None)
            or (observations["add"] and type(observations["version4"]) is not bool)
            or any(type(observations[k]) is not int or observations[k] < 0 for k in ("show", "hide", "timeout", "click"))):
        raise ValueError("Incomplete or mismatched native notification observation")
    registered = observations["add"] and observations["version4"] is True
    if (registered and native.get("notice.notification_request") is not observations["requested"]
            or (not registered and (observations["requested"] or "notice.notification_request" in native))
            or not observations["requested"] and (observations["show"] or observations["independentlyVisible"])):
        raise ValueError("The real notification request and the observed presentation disagree")
    if (native.get("notice.receiver_closed") is not True or (observations["add"] and native.get("notice.remove") is not True)
            or not observations["add"] and "notice.remove" in native or result["subject"].get("exit") != 0
            or result["subject"].get("jobEmpty") is not True):
        raise CleanupUnconfirmed("The original icon, receiver or native process did not confirm normal cleanup")
    if (observations["independentlyVisible"] and observations["show"] > 0 and type(state) is int
            and native.get("notice.taskbar_created") == 0):
        return "passed"
    return "unavailable"


def measure(target, exe, original, out, result):
    api, desk = Win32(), Desktop()
    native_machine = TARGET[os.environ["RUNNER_ARCH"]][1]
    if api.machine(-1) != (native_machine, native_machine) or pe_machine(exe) != native_machine:
        raise ValueError("A genuinely native Python and service binary are required")
    before = result["contextBefore"] = desk.context()
    if not ordinary_console(before, "Default"):
        result["reason"] = "The original unlocked runner console is unavailable"
        return "unavailable"
    token = result["token"] = uuid.uuid4().hex
    tick = bind(api.kernel, "GetTickCount64", c.c_uint64)
    result["lateUptimeMs"] = tick()
    result["sinceEarlyMeasureMs"] = result["lateUptimeMs"] - result["earlyMeasureUptimeMs"]
    if result["sinceEarlyMeasureMs"] < 0:
        raise ValueError("The late trial does not share the original runner uptime epoch")
    temp = Path(os.environ["RUNNER_TEMP"])
    path = out / "observer.log"
    native_log = out / "native.txt"
    with owned_directory(api, temp, "ifw-shell-" + token) as area, ExitStack() as pins:
        pin_new_marker(pins, api, area / "synthetic.fixture", token)
        pins.enter_context(pin_path(api, exe, False))
        if sha(exe) != result["binarySha256"]:
            raise ValueError("The retained native executable differs from the original build")
        env = dict(os.environ, TEMP=str(area), TMP=str(area), IFW_QA_LATE_NOTIFICATION="1",
                   IFW_QA_ISOLATED="1", IFW_QA_INVENTORY_TOKEN=token,
                   POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
        program, result["uiaHosts"] = select_powershell(area, "accessibility", env)
        provider, result["observer"], result["subject"] = None, {}, {}
        finish = area / "notice.finish"
        with ExitStack() as children:
            try:
                if program:
                    args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
                            "-File", str(HERE / "notification.ps1"), "-Token", token, "-Fixture", str(area)]
                    provider = children.enter_context(child(api, Path(program), args, area, env, path, result["observer"]))
                    try:
                        wait(lambda: events(path) or provider.poll() is not None, "The notification observer did not arm", 20)
                    except TimeoutError as exc:
                        result["observer"]["armError"] = str(exc)
                if not ordinary_console(desk.context(), "Default"):
                    raise RuntimeError("The active console changed before the notification launch")
                args = ["--hosted-notification", str(area), token, "private"]
                proc = children.enter_context(child(api, exe, args, area, env, native_log, result["subject"]))
                ready = area / "notice.ready"
                wait(lambda: ready.exists() or proc.poll() is not None, "The native receiver did not register", 12)
                if not ready.is_file() or ready.read_bytes() != token.encode("ascii"):
                    raise ValueError("The native receiver did not identify its synthetic profile")
                metrics = READ(native_log)
                hwnd = metrics["notice.owner_hwnd"]
                owner = desk.window(hwnd)
                result["receiver"] = dict(hwnd=hwnd, readback=owner)
                if (not owner or owner["pid"] != proc.pid or owner["class"] != "IFW RW02 synthetic tray receiver"
                        or desk.name(desk.thread_desktop(owner["tid"])) != "Default" or not ordinary_console(desk.context(), "Default")):
                    raise ValueError("The registered receiver did not belong to the retained subject on the original desktop")
                if metrics.get("notice.taskbar_present") is True:
                    bar = desk.window(metrics["notice.taskbar_hwnd"])
                    result["registrationHost"] = dict(readback=bar, sameSessionAndDesktop=bool(
                        bar and bar["pid"] == metrics["notice.taskbar_pid"] and bar["tid"] == metrics["notice.taskbar_tid"]
                        and bar["class"] == "Shell_TrayWnd" and metrics.get("notice.taskbar_session") == before["session"]
                        and desk.name(desk.thread_desktop(bar["tid"])) == "Default"))
                result["releaseTick"] = tick()
                (area / "notice.go").touch(exist_ok=False)
                sent = area / "notice.sent"
                wait(lambda: sent.exists() or proc.poll() is not None, "The Shell request did not return", 10)
                if not sent.is_file() or sent.read_bytes() != token.encode("ascii"):
                    raise ValueError("The single Shell request did not complete on the retained subject")
                if provider is not None:
                    wait(lambda: proc.poll() is not None or provider.poll() is not None or
                         any(e["stage"] in ("visible", "unavailable") for e in events(path)), "Notification observer exceeded its deadline", 18)
            finally:
                finish.touch(exist_ok=True)
                result["finishTick"] = tick()
                # Preserve an already observed presentation even if icon or job teardown subsequently fails.
                items = result["observerEvents"] = events(path) if path.is_file() else []
                event = observed_presentation(items, token, before["session"], os.environ["SystemRoot"],
                                              result.get("releaseTick"), result["finishTick"])
                result["presentation"] = event
    result["profileRemoved"] = not os.path.lexists(temp / ("ifw-shell-" + token))
    result["contextAfter"] = desk.context()
    items = events(path) if path.is_file() else []
    result["observerEvents"] = items
    event = observed_presentation(items, token, before["session"], os.environ["SystemRoot"], result["releaseTick"], result["finishTick"])
    status = outcome(READ(native_log), event, token, before["session"], os.environ["SystemRoot"], result)
    if provider is not None:
        if event is None or result["observer"]["exit"] != (0 if event["stage"] == "visible" else 2):
            raise RuntimeError("The independent observer failed to complete")
    if not result["profileRemoved"]:
        raise CleanupUnconfirmed("The notification profile could not be removed")
    if not ordinary_console(result["contextAfter"], "Default"):
        result["reason"] = "The original input desktop could not be confirmed at the end of the observation"
        return "unavailable"
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=[name for name, _ in TARGET.values()])
    target = parser.parse_args().target
    if not hosted(target) or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch":
        parser.error("Use the native disposable rewrite runner")
    exe, original = paths(target)
    out = original.parent / ("notification-" + target)
    out.mkdir(exist_ok=False)
    result = dict(status="failed", target=target, head=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                  attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    try:
        bind_build(target, exe, original, result)
        result["status"] = measure(target, exe, original, out, result)
    except Exception as exc:
        result["error"] = dict(type=type(exc).__name__, message=str(exc))
    finally:
        if (out / "native.txt").is_file():
            try:
                result["native"] = READ(out / "native.txt")
            except (OSError, ValueError) as exc:
                result.update(status="failed", nativeReadError=str(exc))
        result["evidenceFiles"] = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
        write(out / "result.json", result)
    print(result["status"], result.get("error") or result.get("reason") or "")
    return {"passed": 0, "unavailable": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
