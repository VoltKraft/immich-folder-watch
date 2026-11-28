"""Observe the actual filename selection on a temporary Windows ARM64 input desktop."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import traceback

HERE = Path(__file__).resolve().parent
PRIVATE = runpy.run_path(str(HERE / "private_source.py"))
DISPLAY, DESKTOP, TARGET = (PRIVATE[key] for key in ("DISPLAY", "DESKTOP", "TARGET"))
QA, ROOT = DISPLAY["QA"], DISPLAY["ROOT"]
BUILD = ROOT / "artifacts/rust/gui-native" / TARGET
OUTPUT = BUILD / "windows-selection-private"
SUBJECT = DESKTOP["GUI_BINARY"]
READ = DISPLAY["TEXT"]["read"]
WRITE = DISPLAY["write_json"]


def verify_selection(session, worker, field, name):
    PRIVATE["verify_restoration"](session, name)
    if (session["workerPid"] != worker["pid"] or session["workerExit"] or not session["jobClosed"]
            or not DESKTOP["ordinary_console"](worker["before"], name)
            or not DESKTOP["ordinary_console"](worker["after"], name)
            or worker["before"]["session"] != session["beforeSwitch"]["session"]
            or worker["after"]["session"] != worker["before"]["session"] or worker["exit"]
            or not worker["hiddenWindowDestroyed"] or not worker["profileRemoved"]
            or worker["transport"] != {"status": "observed", "code": 0, "transport": "console"}):
        raise ValueError("Expected the same private worker, console session and completed cleanup")
    if (field["status"] != "passed" or field["binarySha256"].lower() != session["build"]["binarySha256"]
            or field["observerDesktop"] != name or not field["profileRemoved"] or not field["closedAlive"]
            or field["primaryExit"] or field["secondaryExit"] or field["primaryPid"] == field["secondaryPid"]):
        raise ValueError("The selection, native launcher identity or private process lifetime differs")
    initial = "Grüße – Sommer.jpg"
    for stage, hwnd, value, at, text in (
            ("beforeClose", field["firstHwnd"], initial, 2, "üße"),
            ("afterReopen", field["reopenedHwnd"], initial, 2, "üße"),
            ("afterShiftLeft", field["reopenedHwnd"], initial, 1, "rüße"),
            ("afterReplacement", field["reopenedHwnd"], "Gx – Sommer.jpg", 2, "")):
        state = field["stages"][stage]
        if (state["pid"] != field["primaryPid"] or state["hwnd"] != hwnd or state["foregroundHwnd"] != hwnd
                or not all(state[k] is True for k in ("inputDesktop", "foreground", "focusedElementMatches", "hasKeyboardFocus"))
                or state["value"] != value or state["document"] != value
                or state["selection"] != {"start": at, "text": text}):
            raise ValueError("Unexpected filename focus, document or selection during " + stage)


def observe_worker(api, name, binary):
    record = {"pid": os.getpid(), "before": api.context()}
    try:
        record["transport"] = DISPLAY["protocol"](api, record["before"]["session"])
        if not DISPLAY["eligible_input"](record["before"], record["transport"], name):
            raise ValueError("Only the generated private input desktop on the original console may receive keys")
        with api.enumeration_witness(name, record), DISPLAY["private_profile"](OUTPUT, "uia-", record) as profile:
            env = DISPLAY["environment"](profile)
            for key in ("RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT", "RUNNER_TEMP", "GITHUB_ACTIONS",
                        "GITHUB_REPOSITORY", "GITHUB_REF"):
                env[key] = os.environ[key]
            env["PSModuleAnalysisCachePath"] = str(profile / "ModuleAnalysisCache")
            program, record["observerHosts"] = DISPLAY["select_powershell"](profile, "accessibility", env)
            if not program:
                raise RuntimeError("No local PowerShell host can load UI Automation")
            args = ["-Binary", binary, "-OutputDirectory", OUTPUT / "field", "-HostedDesktop", name, "-QaRoot", QA]
            record["exit"] = DISPLAY["powershell"](program, QA / "windows-text/reopen-selection.ps1",
                                                   args, env, profile, OUTPUT / "observer.log", 150)
        record["after"] = api.context()
        return record["exit"]
    finally:
        WRITE(OUTPUT / "worker.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-desktop", help=argparse.SUPPRESS)
    parser.add_argument("--archive", action="store_true", help="use the separately verified original compiler archive")
    args = parser.parse_args()
    if (not DISPLAY["hosted"]() or os.getenv("RUNNER_ARCH") != "ARM64"
            or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        parser.error("Select the hosted Windows ARM64 rewrite runner")
    binary = BUILD / "selection-replay/native-gui-assessment.exe" if args.archive else SUBJECT
    if DESKTOP["pe_machine"](binary) != 0xaa64:
        parser.error("The selected subject must be a native ARM64 image")
    api = DESKTOP["Desktop"]()
    if args.worker_desktop:
        return observe_worker(api, args.worker_desktop, binary)
    OUTPUT.mkdir(exist_ok=False)
    session = dict(verified=False, source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                   attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    try:
        current = DISPLAY["TEXT"]["check_build"](TARGET, SUBJECT, BUILD)
        session["build"] = READ(binary.parent / "replay.json") if args.archive else current
        if (session["build"]["binarySha256"] != DISPLAY["sha256"](binary) or session["build"]["target"] != TARGET
                or (args.archive and session["build"]["currentReceiptSha256"] != current["receiptSha256"])):
            raise ValueError("The selected GUI differs from its verified native compiler receipt")
        with DESKTOP["named_input_desktop"](api, session) as name:
            flags = ["--archive"] if args.archive else []
            DESKTOP["run_worker"](Path(__file__).resolve(), [*flags, "--worker-desktop", name], name, ROOT, session,
                                  timeout_seconds=220)
        session["returnedDesktop"] = api.context()
        if session["workerExit"]:
            raise RuntimeError(f"The native selection worker exited {session['workerExit']}. See observer.log and worker.json.")
        verify_selection(session, READ(OUTPUT / "worker.json"), READ(OUTPUT / "field/selection.json"), name)
        session["verified"] = True
        return 0
    except Exception:
        session["error"] = traceback.format_exc()
        print(session["error"], file=sys.stderr)
        return 1
    finally:
        WRITE(OUTPUT / "session.json", session)


if __name__ == "__main__":
    sys.exit(main())
