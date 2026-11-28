"""Read the original ARM64 console's notification state before and around the ordinary WinRT Show."""

from contextlib import contextmanager
import ctypes as c
import json
import os
from pathlib import Path
from threading import Event, Thread
import time

from activation import ART, HERE, ROOT, TARGET, paths, sha, write
from notification_probe import Desktop, Win32, bind, ordinary_console
from service_sources import verify_checkout
import toast_history

ARM = TARGET["ARM64"][0]
WORKFLOW = "Rust Windows ARM64 notification after quiet time"
SOURCE = "tools/rust-qa/windows-services/toast_eligibility.py"
OBSERVERS = ("toast_eligibility.py", "toast_console.py", "toast_console.ps1", "toast_settings.ps1")
LIMIT = 65 * 60
INTERVAL = 30
ACCEPTS = 5


class NotificationState:
    def __init__(self):
        api = Win32()
        if api.machine(-1) != (TARGET["ARM64"][1],) * 2:
            raise ValueError("The eligibility observer requires native ARM64 Python")
        self.query = bind(c.WinDLL("shell32"), "SHQueryUserNotificationState", c.c_int32, c.POINTER(c.c_int32))
        self.counter = bind(api.kernel, "QueryPerformanceCounter", c.c_int32, c.POINTER(c.c_int64))
        frequency = bind(api.kernel, "QueryPerformanceFrequency", c.c_int32, c.POINTER(c.c_int64))
        self.frequency = self.read_counter(frequency)

    @staticmethod
    def read_counter(call):
        value = c.c_int64()
        if not call(c.byref(value)) or value.value <= 0:
            raise OSError("The Windows performance counter was unavailable")
        return value.value

    def sample(self):
        state = c.c_int32()
        begin = self.read_counter(self.counter)
        hr = self.query(c.byref(state))
        end = self.read_counter(self.counter)
        return dict(beginQpc=begin, endQpc=end, hresult=hr, state=state.value if hr == 0 else None)


def dedicated():
    toast_history.request_identity(ARM)
    if (os.environ.get("GITHUB_WORKFLOW") != WORKFLOW or os.environ.get("GITHUB_JOB") != "observe"
            or os.environ.get("IFW_QA_TOAST_ELIGIBILITY") != "wait" or os.environ.get("IFW_QA_TOAST_POLICY") != "permitted"):
        raise ValueError("Use the dedicated ARM64 notification eligibility job")


def identity(desktop):
    head = os.environ["GITHUB_SHA"]
    (_, original) = paths(ARM)
    build = json.loads((original / "result.json").read_bytes())
    sources = verify_checkout(ROOT, [HERE / name for name in OBSERVERS], head)
    if (build["target"] != ARM or build["head"] != head or build["workflowRun"] != os.environ["GITHUB_RUN_ID"]
            or build["workflowAttempt"] != os.environ["GITHUB_RUN_ATTEMPT"] or build["checkoutVerified"] is not True
            or any(build["sourceFiles"].get(name) != digest for name, digest in sources.items())
            or not ordinary_console(desktop, "Default")):
        raise ValueError("The observer must run on the source-bound native sender's original console")
    return dict(target=ARM, head=head, run=build["workflowRun"], attempt=build["workflowAttempt"],
                workflow=WORKFLOW, job=os.environ["GITHUB_JOB"], session=desktop["session"], sources=sources,
                nativeBuildSha256=sha(original / "result.json"))


def wait_for_accepts(report, sample, console, save, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    while True:
        if not console():
            report["status"] = "console-changed"
            save()
            return False
        row = sample()
        elapsed = clock() - start
        report["samples"].append({**row, "elapsedSeconds": elapsed})
        if row["hresult"] != 0:
            report["status"] = "query-failed"
        elif elapsed > LIMIT:
            report["status"] = "deadline"
        elif row["state"] == ACCEPTS:
            report["status"] = "accepts-notifications"
        elif elapsed >= LIMIT:
            report["status"] = "deadline"
        save()
        if report["status"] != "waiting":
            return report["status"] == "accepts-notifications"
        sleep(min(INTERVAL, LIMIT - elapsed))


def wait():
    dedicated()
    desk, state = Desktop(), NotificationState()
    before = desk.context()
    report = dict(**identity(before), desktopBefore=before, frequency=state.frequency,
                  status="waiting", limitSeconds=LIMIT, intervalSeconds=INTERVAL, samples=[])
    out = ART / ("toast-eligibility-" + ARM)
    out.mkdir(exist_ok=False)
    path = out / "wait.json"

    def save():
        temporary = path.with_suffix(".tmp")
        write(temporary, report)
        temporary.replace(path)

    def console():
        here = report["desktopAfter"] = desk.context()
        return ordinary_console(here, "Default") and here["session"] == before["session"]

    return wait_for_accepts(report, state.sample, console, save)


def check_unsent_policy():
    from toast_console import verify_policy
    dedicated()
    desktop = Desktop().context()
    verified = identity(desktop)
    directory = ART / ("toast-history-" + ARM)
    if (directory / "result.json").exists():
        raise ValueError("Use the original sender for policy verification after a send")
    return verify_policy(directory, "permitted", native={**verified, "desktop": desktop, "observerInputs": verified["sources"]},
                         sent=False)


@contextmanager
def during_sender():
    dedicated()
    desk, state = Desktop(), NotificationState()
    before = desk.context()
    out = ART / ("toast-eligibility-" + ARM)
    prior = json.loads((out / "wait.json").read_bytes())
    report = dict(**identity(before), desktopBefore=before, frequency=state.frequency, samples=[])
    if any(prior[key] != value for key, value in report.items() if key not in ("desktopBefore", "samples")):
        raise ValueError("The waiting console or native source changed before sending")
    if prior["status"] != "accepts-notifications" or prior["samples"][-1]["state"] != ACCEPTS:
        raise ValueError("The original console did not become eligible")
    report["waitSha256"] = sha(out / "wait.json")
    path = out / "sender.json"
    if path.exists():
        raise ValueError("The sender requires a fresh eligibility trace")
    ready, stop = Event(), Event()

    def observe():
        try:
            while True:
                report["samples"].append(state.sample())
                ready.set()
                if stop.wait(.025):
                    break
            report["samples"].append(state.sample())
        except Exception as exc:
            report["samplerError"] = str(exc)
            ready.set()

    thread = Thread(target=observe, daemon=True)
    thread.start()
    try:
        if not ready.wait(5) or not report["samples"] or report["samples"][0]["state"] != ACCEPTS:
            raise ValueError("The Shell did not permit notifications before starting the original sender")
        yield
    finally:
        stop.set()
        thread.join(5)
        report["samplerStopped"] = not thread.is_alive()
        report["desktopAfter"] = desk.context()
        write(path, report)


def bracket(rows, timing):
    frequency, begin, end = timing
    last = 0
    left, right = None, None
    overlapping = []
    for row in rows:
        if not last <= row["beginQpc"] <= row["endQpc"] or type(row["hresult"]) is not int:
            raise ValueError("Unordered Shell notification samples")
        if (row["hresult"] != 0 and row["state"] is not None
                or row["hresult"] == 0 and type(row["state"]) is not int):
            raise ValueError("The Shell state disagrees with its HRESULT")
        last = row["endQpc"]
        if last <= begin:
            left = row
        if right is None and row["beginQpc"] >= end:
            right = row
        if row["beginQpc"] < end and row["endQpc"] > begin:
            overlapping.append(row)
    if left is None or right is None or begin - left["beginQpc"] > frequency / 2 or right["endQpc"] - end > frequency / 2:
        raise ValueError("Missing a completed Shell query within 500 ms on each side of the ordinary Show")
    return dict(before=left, after=right, overlapping=overlapping, beforeMs=(begin - left["endQpc"]) * 1000 / frequency,
                afterMs=(right["beginQpc"] - end) * 1000 / frequency)


def accepted_wait(waited, trace):
    rows = waited["samples"]
    if (waited["status"] != "accepts-notifications" or (waited["limitSeconds"], waited["intervalSeconds"]) != (LIMIT, INTERVAL)
            or not rows or not trace["samples"] or rows[-1]["state"] != ACCEPTS or rows[-1]["elapsedSeconds"] > LIMIT
            or rows[-1]["endQpc"] > trace["samples"][0]["beginQpc"] or trace["samples"][0]["state"] != ACCEPTS):
        return False
    last_qpc, last_seconds = 0, 0
    for index, row in enumerate(rows):
        if (row["hresult"] != 0 or type(row["state"]) is not int or (row["state"] == ACCEPTS and index != len(rows) - 1)
                or not last_qpc <= row["beginQpc"] <= row["endQpc"] or not last_seconds <= row["elapsedSeconds"]):
            return False
        last_qpc, last_seconds = row["endQpc"], row["elapsedSeconds"]
    return True


def verify(directory, frames):
    from toast_console import check_venue, normal_show, verify_policy
    out = directory.parent / ("toast-eligibility-" + ARM)
    wait_path = out / "wait.json"
    waited = json.loads(wait_path.read_bytes())
    native = json.loads((directory / "result.json").read_bytes())
    trace = json.loads((out / "sender.json").read_bytes())
    physical = json.loads((frames / "physical.json").read_text(encoding="utf-8-sig"))
    check_venue(native, physical)
    verify_policy(directory, "permitted")
    binary = directory.parent / "build" / ARM / "release/ifw-windows-services-probe.exe"
    if sha(binary) != native["binarySha256"]:
        raise ValueError("The archived executable differs from the sender that issued the ordinary Show")
    expected = dict(head=native["head"], run=native["run"], attempt=native["attempt"], target=ARM,
                    workflow=WORKFLOW, job="observe", session=native["desktop"]["session"],
                    nativeBuildSha256=sha(directory / "native-build.json"))
    names = [Path(SOURCE).with_name(name).as_posix() for name in OBSERVERS]
    files = {name: native["observerInputs"][name] for name in names}
    for receipt in (waited, trace):
        if (any(receipt[key] != value for key, value in expected.items()) or receipt["sources"] != files
                or any(not ordinary_console(receipt[key], "Default") or receipt[key]["session"] != expected["session"]
                       for key in ("desktopBefore", "desktopAfter"))):
            raise ValueError("An eligibility observation belongs to a different console, build, job or observer")
    if (not accepted_wait(waited, trace)
            or trace["waitSha256"] != sha(wait_path) or trace["samplerStopped"] is not True or "samplerError" in trace
            or physical["workflow"] != WORKFLOW or physical["job"] != "observe"
            or physical["session"] != expected["session"] or physical["token"] != native["token"]):
        raise ValueError("The eligibility wait and original sender observations do not agree")
    confirm = json.loads((directory.parent / ("toast-settings-" + ARM + "-confirmpermitted.json")).read_text(encoding="utf-8-sig"))
    if (any(confirm[k] != expected[k] for k in ("head", "run", "attempt", "session", "workflow", "job"))
            or confirm["scriptSha256"] != files["tools/rust-qa/windows-services/toast_settings.ps1"]
            or confirm["action"] != "ConfirmPermitted" or confirm["afterSender"] is not False or confirm["status"] != "observed"
            or not (confirm["opened"] and confirm["closed"] and confirm["pid"] > 0 and confirm["hwnd"])
            or any(confirm[k]["count"] != 1 or confirm[k]["state"] != value for k, value in
                   (("notifications", "On"), ("doNotDisturb", "Off")))):
        raise ValueError("The permitted console settings were not confirmed after the wait")
    toast_history.replay(directory, native)
    proc, item = normal_show(directory, native)
    timing = toast_history.toast_banner.show_timing(item)
    if item["fields"]["showHresult"] != "0" or item["fields"]["suppressPopup"] != "false" or not (
            timing[0] == trace["frequency"] == waited["frequency"] == physical["frequency"]):
        raise ValueError("Different counter domains or missing successful ordinary WinRT Show")
    observed = bracket(trace["samples"], timing)
    diagnostics = physical["diagnostics"]
    if (diagnostics["samples"] <= 0 or not timing[2] <= diagnostics["firstQpc"] <= diagnostics["lastQpc"] <= timing[2] + 10 * timing[0]
            or any(type(diagnostics[k]) is not int or diagnostics[k] < 0 for k in
                   ("visibleCoreWindowVisits", "shellWindowVisits", "viewQueries", "normalViewMatches", "onscreenViewVisits"))):
        raise ValueError("No measured physical Shell window and toast-view samples in the ordinary Show interval")
    result = dict(**observed, token=native["token"], senderPid=proc["pid"], timing=timing, physicalStatus=physical["status"],
                  diagnostics=diagnostics, eligible=all(row["state"] == ACCEPTS for row in
                                                      [observed["before"], *observed["overlapping"], observed["after"]]))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--wait", action="store_true")
    modes.add_argument("--check-unsent-policy", action="store_true")
    modes.add_argument("--verify", type=Path, nargs=2, metavar=("NATIVE", "PHYSICAL"))
    args = parser.parse_args()
    if args.wait:
        raise SystemExit(0 if wait() else 2)
    if args.check_unsent_policy:
        print(json.dumps(check_unsent_policy(), indent=2))
        raise SystemExit(0)
    result = verify(*args.verify)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["eligible"] else 2)
