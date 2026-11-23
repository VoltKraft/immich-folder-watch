"""Observe a genuine private-desktop keyboard launch of the retained Windows GUI."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import sys

import observe
from input_gesture import InputUnavailable, accept_key, keyboard_launcher
from job import run_worker
from named_process import Kernel, environment_block
from win32 import Desktop, check, ordinary_console

HERE, QA, ROOT = observe.HERE, observe.QA, observe.ROOT
ART = ROOT / "artifacts/rust"
SCRIPT = HERE / "input_launch.py"


def read(path):
    return json.loads(path.read_bytes())


def check_build(target, original, current):
    keys = ("revision", "target", "run", "attempt", "subject", "gui", "buildReceipt", "graph", "lock")
    if (current["target"] != target or current["subject"] != "retained"
            or any(original[key] != current[key] for key in keys)):
        raise ValueError("The ordinary second launch and gesture trial must use the same retained native build")


def check_handoff(cycle, worker):
    gesture = cycle["inputGesture"]
    child = gesture["created"]
    before = gesture["beforeCreate"]
    start = cycle["secondaryLaunch"]
    focused = cycle["keyboardFocus"]
    if (start != dict(api="CreateProcessW", callerPid=worker, source="foreground-key-handler")
            or child["parentPid"] != worker or gesture["callerPid"] != worker
            or child["creation100ns"] != cycle["secondaryCreation100ns"]
            or child["pid"] != cycle["secondaryPid"] or child["foreground"] != gesture["hwnd"]
            or before["hwnd"] != gesture["hwnd"] or before["thread"] != gesture["callerThread"]
            or before["tick"] > child["tick"] or child["parentCreation100ns"] <= 0
            or child["image"] != "native-gui-assessment.exe"):
        raise ValueError("The ordinary child did not originate in the observed foreground input handler")
    if (cycle["foregroundHandoff"]["grant"] != "granted" or cycle["foregroundHandoff"]["requestAccepted"] is not True
            or cycle["initialWindow"] != cycle["reopenedWindow"] or cycle["foregroundObservation"]["observed"] is not True
            or not all(focused["lastSample"][k] is True for k in ("foreground", "active", "focused"))
            or focused["observed"] is not True):
        raise ValueError("Windows did not transfer both foreground and keyboard focus to the original GUI")
    if (cycle["stage"] != "drained" or gesture["windowDestroyed"] is not True
            or gesture["queued"] != 2 or len(gesture["keys"]) != 2):
        raise ValueError("The input window or the gesture did not finish its bounded lifetime")
    if gesture["beforeQueue"] != dict(owner=True, privateInput=True, foreground=True, focus=True, visible=True,
                                      centerOwned=True, foregroundAfter=True):
        raise ValueError("The original keyboard target was not owned and focused when the gesture was queued")
    rows = []
    for event in gesture["keys"]:
        if event["dispatchThread"] != gesture["callerThread"]:
            raise ValueError("The key did not reach the original foreground UI thread")
        accept_key(rows, gesture["hwnd"], gesture["marker"], event)


def worker(target, name, out):
    """Accept only the supervisor's fixed, pinned profile on its newly created input desktop."""
    api, desk = observe.recorder.Win32(), Desktop()
    record = {"pid": os.getpid(), "creation100ns": api.process_identity(-1), "contextBefore": desk.context(), "activation": {}}
    try:
        token = name.removeprefix("IfwQa_")
        root = Path(os.environ["RUNNER_TEMP"]) / ("ifw-rw02-" + token)
        trial, gui = root / "rust-1", root / "subject/native-gui-assessment.exe"
        admission = read(out / "profile.json")
        if (not re.fullmatch(r"IfwQa_[0-9a-f]{32}", name) or not ordinary_console(record["contextBefore"], name)
                or os.environ.get("IFW_QA_INVENTORY_TOKEN") != token or os.environ.get("IFW_QA_ISOLATED") != "1"
                or os.environ.get("IFW_QA_WINDOWS_LAUNCHER") != "1" or os.environ.get("IFW_QA_LAUNCHER_SID") != observe.recorder.sid()
                or Path(os.environ["IFW_QA_INVENTORY_ROOT"]) != root or Path(os.environ["TEMP"]) != trial
                or os.environ.get("IFW_QA_INVENTORY_TRIAL") != "rust-1" or (root / "inventory.owner").read_bytes() != token.encode("ascii")
                or admission["desktop"] != name or admission["supervisor"] != os.getppid()
                or admission["target"] != target or admission["revision"] != os.environ["GITHUB_SHA"]
                or admission["run"] != os.environ["GITHUB_RUN_ID"] or admission["attempt"] != os.environ["GITHUB_RUN_ATTEMPT"]
                or api.machine(-1) != (observe.TARGETS[target], observe.TARGETS[target])):
            raise ValueError("The worker did not inherit its own staged native profile and named input desktop")
        build = read(ART / "windows-warm-window" / target / "build.json")
        if (build["binary"] != admission["gui"] or admission["config"] != observe.recorder.sha(trial / "config.yaml")
                or any(observe.recorder.sha(path) != admission[key] for key, path in (
                    ("gui", gui), ("worker", gui.with_name("ifw-performance-worker.exe"))))):
            raise ValueError("The worker's program or isolated configuration differs from the supervisor's pinned originals")
        with desk.enumeration_witness(name, record):
            fixture = observe.recorder.load_windows_fixture()
            observe.cycle(api, desk, name, check(desk.thread_desktop(desk.thread()), "GetThreadDesktop"),
                          int(record["hiddenEnumerationWindow"], 16), fixture, gui, observe.system_console_path(api.kernel),
                          trial, os.environ.copy(), out, "keyboard", record["activation"], subject="retained",
                          keyboard_launcher=keyboard_launcher)
        check_handoff(record["activation"], record["pid"])
        record["status"] = "passed"
    except Exception as error:
        record.update(status="unavailable" if isinstance(error, (InputUnavailable, observe.ShowOrderUnavailable))
                      and not observe.CleanupUnconfirmed.in_chain(error) else "failed", failures=observe.failures(error))
    finally:
        record["contextAfter"] = desk.context()
        if not ordinary_console(record["contextAfter"], name):
            record.update(status="failed", cleanupError="The worker could not confirm its original input desktop")
        observe.recorder.write(out / "worker.json", record)
    return {"passed": 0, "failed": 1, "unavailable": 2}[record["status"]]


def run(target, out, result):
    desktop_script = QA / "windows-desktop/run.py"
    sources = (SCRIPT, HERE / "input_gesture.py", desktop_script, QA / "windows-desktop/worker.py")
    with observe.native_subject(target, out, result, sources, subject="retained") as (api, desk, built, inventory, revision):
        ordinary = ART / "windows-launcher-retained" / target / "result.json"
        check_build(target, read(ordinary), result)
        result["ordinaryLauncherSha256"] = observe.recorder.sha(ordinary)
        result["originalContext"] = desk.context()
        if not ordinary_console(result["originalContext"], "Default"):
            raise InputUnavailable("The disposable runner lacks an unlocked Default input desktop")
        named = runpy.run_path(str(desktop_script), run_name="input_launch_desktop")["named_input_desktop"]
        placement = result["placement"] = {}
        with named(desk, placement) as name:
            token = name.removeprefix("IfwQa_")
            profile = result["profileTrial"] = {}
            with observe.staged_profile(profile, api, built, inventory, token=token) as (gui, trial, env):
                admission = out / "profile.json"
                observe.recorder.write(admission, dict(target=target, revision=revision, gui=inventory["gui"],
                                       worker=inventory["worker"], config=observe.recorder.sha(trial / "config.yaml"),
                                       desktop=name, supervisor=os.getpid(), run=result["run"], attempt=result["attempt"]))
                with observe.recorder.pin_path(api, admission, False):
                    host = result["workerJob"] = {}
                    code = run_worker(SCRIPT, [target, "--named", name], name, ROOT, host, timeout_seconds=240,
                                      environment_block=environment_block(Kernel(), env))
                    report = read(out / "worker.json")
                    if report["pid"] != host["workerPid"] or not host["jobClosed"]:
                        raise ValueError("The native gesture report must belong to the launched worker")
                    if code == 2 and report["status"] == "unavailable":
                        raise InputUnavailable(report["failures"][0]["message"])
                    if code != 0 or report["status"] != "passed":
                        raise ValueError("The native gesture worker failed. Inspect worker.json and the original logs")
                    cycle = report["activation"]
                    if cycle["inputGesture"]["created"]["parentCreation100ns"] != report["creation100ns"]:
                        raise ValueError("The suspended child's parent did not match the native worker identity")
                    observe.qualify((out / "keyboard-secondary.log").read_text(encoding="utf-8").splitlines(),
                                    (out / "keyboard-primary.log").read_text(encoding="utf-8").splitlines(), cycle)
                    check_handoff(cycle, host["workerPid"])
        if not profile["cleanupConfirmed"] or placement["cleanup"]["inputAfterRestore"] != "Default":
            raise ValueError("The private profile or original input desktop was not restored")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=observe.TARGETS)
    parser.add_argument("--named", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not observe.recorder.hosted() or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"
            or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"):
        parser.error("Use the disposable native Windows rewrite workflow")
    out = ART / "windows-launcher-input" / args.target
    if args.named:
        return worker(args.target, args.named, out)
    out.mkdir(exist_ok=False, parents=True)
    result = dict(status="failed", target=args.target)
    try:
        run(args.target, out, result)
        result["status"] = "passed"
    except InputUnavailable as error:
        result.update(status="unavailable", error=str(error))
    except Exception as error:
        result["failures"] = observe.failures(error)
    finally:
        result["evidenceFiles"] = {p.name: observe.recorder.sha(p) for p in sorted(out.iterdir()) if p.is_file()}
        observe.recorder.write(out / "result.json", result)
    return {"passed": 0, "failed": 1, "unavailable": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
