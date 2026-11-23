"""Reobserve a single silent Shell notification late in the original disposable Windows job."""
from contextlib import ExitStack, contextmanager
import ctypes as c
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import time
import uuid

from activation import DESKTOP, HERE, QA, ROOT, TARGET, module, sha
sys.path[:0] = [str(HERE), str(QA / "windows-performance"), str(DESKTOP), str(QA / "windows-launcher"), str(QA)]
for module_name, expected_file in {
        "build": QA / "windows-performance/build.py", "native": QA / "windows-performance/native.py",
        "named_process": QA / "windows-launcher/named_process.py", "job": DESKTOP / "job.py", "win32": DESKTOP / "win32.py",
        "windows_observer": QA / "windows_observer.py", "notification_host": HERE / "notification_host.py"}.items():
    found = importlib.util.find_spec(module_name)
    if found is None or found.origin is None or Path(found.origin).resolve() != expected_file:
        raise ImportError(f"The notification observer resolved an unverified dependency: {module_name}")
from build import pe_machine
from named_process import start
from native import CleanupUnconfirmed, Win32, checked, owned_directory, pin_new_marker, pin_path
from notification_host import ShellWitness, compare_early, native_host, stable_registration
from win32 import Desktop, bind, ordinary_console
from windows_observer import select_powershell

READ = module("notification_service", HERE / "run.py").read_native

STATES = {1: "NOT_PRESENT", 2: "BUSY", 3: "RUNNING_D3D_FULL_SCREEN", 4: "PRESENTATION_MODE",
          5: "ACCEPTS_NOTIFICATIONS", 6: "QUIET_TIME", 7: "APP"}


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
                   for key in ("compiler", "inventory", "format", "clippy", "notification-points", "balloon-id", "build"))):
        raise ValueError("The completed early native build did not identify this job, revision and qualified binary")
    if early.get("checkoutVerified") is not True or early["sourceFiles"] != record["observerInputs"]:
        raise ValueError("The early build and late observer did not verify the same checkout inputs")
    verified = {}
    for name in ("compiler.txt", "graph.json", "build.txt", "balloon-id.txt", "notification-points.txt"):
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
                  earlyMeasureUptimeMs=early["measureUptimeMs"], graphSha256=canonical)
    if "native.txt" in early["evidenceFiles"]:
        native = original / "native.txt"
        if sha(native) != early["evidenceFiles"]["native.txt"]:
            raise ValueError("The retained early service observation changed")
        observed = READ(native)
        record["earlyNotification"] = {key: observed.get(key) for key in (
            "tray.notification_state", "tray.notification_state_hresult", "tray.initial.add",
            "tray.notification_request", "tray.callbacks.balloon_show")}
        record["earlyNotification"]["nativeSha256"] = sha(native)
        record["earlyNotification"]["host"] = native_host(observed, "tray")


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
def fixture_profile(api, temp, token, record):
    name = "ifw-shell-" + token
    try:
        with owned_directory(api, temp, name) as area:
            yield area
    finally:
        record["profileRemoved"] = not os.path.lexists(temp / name)


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
            try:
                if process is not None:
                    try:
                        record["exit"] = process.wait(timeout=14)
                    except subprocess.TimeoutExpired:
                        record["forced"] = True
                        process.kill()
                        record["exit"] = process.wait(timeout=5)
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
        except Exception as exc:
            record["cleanupError"] = dict(type=type(exc).__name__, message=str(exc))
            raise CleanupUnconfirmed("The notification fixture could not confirm the child and job were idle and released") from exc


def inside(point, bounds):
    return bounds[0] <= point[0] < bounds[2] and bounds[1] <= point[1] < bounds[3]


def check_match(match, token, session, winroot):
    host = match["host"]
    base = PureWindowsPath(winroot)
    files = {"explorer.exe", "System32/ShellHost.exe", "SystemApps/ShellExperienceHost_cw5n1h2txyewy/ShellExperienceHost.exe",
             "SystemApps/Microsoft.Windows.ShellExperienceHost_cw5n1h2txyewy/ShellExperienceHost.exe",
             "SystemApps/MicrosoftWindows.Client.CBS_cw5n1h2txyewy/ShellHost.exe",
             "SystemApps/Microsoft.Windows.StartMenuExperienceHost_cw5n1h2txyewy/StartMenuExperienceHost.exe"}
    if (match["desktop"] != "Default" or not match.get("rootId") or not match["container"] or host["sameUser"] is not True
            or host["session"] != session or not all(type(host[k]) is int and host[k] > 0 for k in ("hwnd", "pid", "creation"))
            or not host["windowClass"]
            or PureWindowsPath(host["image"]) not in {base / name for name in files}):
        raise ValueError("The visible match did not identify an original same-user Shell notification host")
    for field, expected in (("title", "IFW notice " + token), ("body", "Synthetic IFW notification " + token)):
        item = match[field]
        native, provider = item["nativeHit"], item["providerHit"]
        if (item["text"] != expected or item["pid"] != host["pid"] or item["offscreen"] is not False or not item["runtimeId"]
                or not item.get("directParent") or not isinstance(native, dict) or not isinstance(provider, dict)
                or native.get("root") != host["hwnd"] or native.get("pid") != host["pid"]
                or any(type(native.get(k)) is not int or native[k] <= 0 for k in ("hwnd", "monitor", "tid"))
                or provider.get("pid") != host["pid"] or len(item["point"]) != 2 or len(item["bounds"]) != 4
                or any(type(v) is not int for v in item["point"])
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in item["bounds"])
                or not inside(item["point"], item["bounds"])):
            raise ValueError(f"The exact notification {field} lacked independently visible physical bounds")
        path = provider.get("runtimePath")
        kind = provider.get("kind")
        if (not isinstance(path, list) or not 1 <= len(path) <= 8 or any(not isinstance(p, str) or not p for p in path)
                or len(set(path)) != len(path) or kind not in ("label", "descendant", "sharedParent")
                or kind == "label" and path != [item["runtimeId"]]
                or kind == "descendant" and (len(path) < 2 or path[-1] != item["runtimeId"]
                                             or match["container"] in path or match["rootId"] in path)
                or kind == "sharedParent" and path != [match["container"]]):
            raise ValueError(f"The notification {field} provider hit could not be attributed to its label")
    a, b = match["title"], match["body"]
    if (a["runtimeId"] == b["runtimeId"] or a["point"] == b["point"] or a["bounds"] == b["bounds"]
            or a["runtimeId"] in b["providerHit"]["runtimePath"] or b["runtimeId"] in a["providerHit"]["runtimePath"]):
        raise ValueError("The title and body did not have distinct physically sampled labels")
    if any(item["providerHit"]["kind"] == "sharedParent" for item in (a, b)):
        if (match["rootId"] == match["container"] or a["directParent"] != match["container"]
                or b["directParent"] != match["container"] or inside(a["point"], b["bounds"]) or inside(b["point"], a["bounds"])):
            raise ValueError("The shared provider parent did not independently locate both labels")


def arm_event(items):
    if len(items) == 1:
        event = items[0]
        if (event.get("stage") == "armed" and event.get("preexistingMatch") is False
                and type(event.get("tick")) is int and event["tick"] >= 0):
            return event
    return None


def observed_presentation(items, token, session, winroot, armed_before_request, release, finish):
    final = [e for e in items if e["stage"] in ("visible", "unavailable")]
    if len(final) > 1:
        raise ValueError("Ambiguous notification presentation outcome")
    event = final[0] if final else None
    if event is not None and event["stage"] == "visible":
        if armed_before_request is None:
            return dict(stage="unavailable", providerStage="visible",
                        reason="The observer had not confirmed its baseline before the request was released")
        if (items != [armed_before_request, event]
                or arm_event([armed_before_request]) is None or release is None
                or not armed_before_request["tick"] <= release <= event["match"]["tick"] <= finish):
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
    samples = result.get("registrationHost", {})
    original = samples.get("beforeLaunch", {})
    observations["stableRegistrationHost"] = stable_registration(samples, native, session)
    observations["earlyHostComparison"] = compare_early(result.get("earlyNotification", {}).get("host"), original)
    observations["rendererBound"] = False
    if observations["independentlyVisible"]:
        renderer = event["match"]["host"]
        observations["rendererBound"] = bool(
            PureWindowsPath(renderer["image"]) != PureWindowsPath(winroot) / "explorer.exe"
            or original.get("verified") is True and (renderer["pid"], renderer["creation"], renderer["session"])
            == (original["taskbar_pid"], original["taskbar_creation"], original["taskbar_session"]))
    if (native.get("notice.pid") != result["subject"]["pid"] or native.get("notice.icon_id") != 23
            or native.get("notice.owner_hwnd") != result["receiver"]["hwnd"]
            or type(native.get("notice.tid")) is not int or native["notice.tid"] <= 0
            or native["notice.tid"] != result["receiver"]["readback"]["tid"]
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
    if (observations["stableRegistrationHost"] and observations["rendererBound"] and observations["independentlyVisible"]
            and observations["show"] > 0 and type(state) is int
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
    with fixture_profile(api, temp, token, result) as area, ExitStack() as pins:
        pin_new_marker(pins, api, area / "synthetic.fixture", token)
        pins.enter_context(pin_path(api, exe, False))
        if sha(exe) != result["binarySha256"]:
            raise ValueError("The retained native executable differs from the original build")
        env = dict(os.environ, TEMP=str(area), TMP=str(area), IFW_QA_LATE_NOTIFICATION="1",
                   IFW_QA_ISOLATED="1", IFW_QA_INVENTORY_TOKEN=token,
                   POWERSHELL_TELEMETRY_OPTOUT="1", POWERSHELL_UPDATECHECK="Off")
        program, result["uiaHosts"] = select_powershell(area, "accessibility", env)
        witness = ShellWitness(api, desk, before["session"], os.environ["SystemRoot"], pins)
        samples = result["registrationHost"] = {"beforeLaunch": witness.sample()}
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
                if (not owner or owner["pid"] != proc.pid or owner["tid"] != metrics.get("notice.tid")
                        or owner["class"] != "IFW RW02 synthetic tray receiver" or desk.pid_session(owner["pid"]) != before["session"]
                        or desk.name(desk.thread_desktop(owner["tid"])) != "Default" or not ordinary_console(desk.context(), "Default")):
                    raise ValueError("The registered receiver did not belong to the retained subject on the original desktop")
                samples["beforeRequest"] = witness.sample()
                result["armBeforeRequest"] = arm_event(events(path)) if path.is_file() else None
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
                try:
                    samples["afterRequest"] = witness.sample()
                finally:
                    finish.touch(exist_ok=True)
                    result["finishTick"] = tick()
                    # Preserve the visible evidence before any receiver, icon or job teardown.
                    items = result["observerEvents"] = events(path) if path.is_file() else []
                    result["presentation"] = observed_presentation(items, token, before["session"], os.environ["SystemRoot"],
                                                                  result.get("armBeforeRequest"), result.get("releaseTick"),
                                                                  result["finishTick"])
        samples["afterQuit"] = witness.sample()
    result["contextAfter"] = desk.context()
    items = events(path) if path.is_file() else []
    result["observerEvents"] = items
    event = observed_presentation(items, token, before["session"], os.environ["SystemRoot"], result.get("armBeforeRequest"),
                                  result["releaseTick"], result["finishTick"])
    status = outcome(READ(native_log), event, token, before["session"], os.environ["SystemRoot"], result)
    if provider is not None:
        if event is None or result["observer"]["exit"] != (0 if event.get("providerStage", event["stage"]) == "visible" else 2):
            raise RuntimeError("The independent observer failed to complete")
    if not result["profileRemoved"]:
        raise CleanupUnconfirmed("The notification profile could not be removed")
    if not ordinary_console(result["contextAfter"], "Default"):
        result["reason"] = "The original input desktop could not be confirmed at the end of the observation"
        return "unavailable"
    return status
