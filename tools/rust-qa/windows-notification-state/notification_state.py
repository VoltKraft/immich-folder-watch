"""Observe the original Server 2022 notification state before the late presentation trials."""
from contextlib import ExitStack
import ctypes as c
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
SERVICES = HERE.parent / "windows-services"
sys.path.insert(0, str(SERVICES))
from activation import ROOT, hosted, paths, write
from notification_probe import Desktop, STATES, Win32, bind, bind_build
from notification_host import HOST_FIELDS, ShellWitness, compare_early
from service_sources import service_files, verify_checkout

TARGET = "x86_64-pc-windows-msvc"
INTERVAL_MS = 30_000
LIMIT_MS = 65 * 60_000


def observe(report, early, sample_host, query, ticks, sleep):
    start = ticks()
    deadline = start + LIMIT_MS
    report.update(startTick=start, intervalMs=INTERVAL_MS, deadlineTick=deadline, samples=[])
    while True:
        row = {"startTick": ticks()}
        report["samples"].append(row)
        before = row["before"] = sample_host()
        row["earlyHostComparison"] = compare_early(early, before)
        if (not before.get("verified") or row["earlyHostComparison"] != "same-explorer-and-taskbar"
                or any(before.get(k) != early.get(k) for k in HOST_FIELDS)):
            return "original-desktop-or-shell-unavailable"
        state = c.c_int32()
        row["queryStartTick"] = ticks()
        hr = row["hresult"] = query(c.byref(state))
        row["queryEndTick"] = ticks()
        row["state"] = state.value if hr == 0 else None
        row["stateName"] = STATES.get(row["state"])
        after = row["after"] = sample_host()
        if not after.get("verified") or any(after.get(k) != before[k] for k in HOST_FIELDS):
            return "original-desktop-or-shell-changed"
        if hr != 0:
            return "query-failed"
        if state.value == 5:
            return "accepts-notifications"
        if state.value != 6:
            return "other-state"
        remaining = deadline - ticks()
        if remaining <= 0:
            return "quiet-time-deadline"
        sleep(min(INTERVAL_MS, remaining) / 1000)


def observe_original(report):
    report["stage"] = "open-desktop-and-query-api"
    api, desk = Win32(), Desktop()
    ticks = bind(api.kernel, "GetTickCount64", c.c_uint64)
    query = bind(c.WinDLL("shell32"), "SHQueryUserNotificationState", c.c_int32, c.POINTER(c.c_int32))
    with ExitStack() as stack:
        witness = ShellWitness(api, desk, desk.context()["session"], os.environ["SystemRoot"], stack)
        early = report.get("earlyNotification", {}).get("host", {})
        report["stage"] = "sample-original-shell"
        try:
            report["status"] = observe(report, early, witness.sample, query, ticks, time.sleep)
        finally:
            report["endTick"] = ticks()
        report["stage"] = "release-original-shell"
    report["stage"] = "finished"


def main():
    if (not hosted(TARGET) or os.getenv("ImageOS") != "win22"
            or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"):
        sys.exit("Use the dedicated hosted Windows Server 2022 x64 rewrite runner")
    out = ROOT / "artifacts/rust/server-2022-notifications/notification-state.json"
    head = os.environ["GITHUB_SHA"]
    report = dict(head=head, target=TARGET, run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                  status="failed", stage="bind-original-build")
    try:
        report["observerInputs"] = verify_checkout(ROOT, service_files(), head, SERVICES)
        report["stateObserverInput"] = verify_checkout(ROOT, [Path(__file__).resolve()], head)
        bind_build(TARGET, *paths(TARGET), report)
        try:
            observe_original(report)
        except (AttributeError, OSError) as exc:
            if report["stage"] == "release-original-shell":
                raise
            report.update(status="native-lookup-unavailable", errorType=type(exc).__name__, error=str(exc))
    except Exception as exc:
        report.update(status="failed", errorType=type(exc).__name__, error=str(exc))
        raise
    finally:
        write(out, report)
    print("Server 2022 notification state", report["status"], flush=True)


if __name__ == "__main__":
    main()
