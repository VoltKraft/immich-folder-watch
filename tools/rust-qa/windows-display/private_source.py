"""Measure a stationary ARM64 source frame on a new input desktop and restore the original console."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import traceback

HERE = Path(__file__).resolve().parent
DISPLAY = runpy.run_path(str(HERE / "run.py"))
DESKTOP = DISPLAY["TEXT"]["DESKTOP"]
TARGET = "aarch64-pc-windows-msvc"


def verify_restoration(session, name):
    original = session["beforeSwitch"]
    endpoint = session["returnedDesktop"]
    if (not DISPLAY["named_desktop"](name) or not DESKTOP["ordinary_console"](original, "Default")
            or not DESKTOP["ordinary_console"](endpoint, "Default") or endpoint["session"] != original["session"]
            or session["created"]["requested"] != name or session["created"]["actual"] != name
            or session["afterSwitch"]["inputDesktop"] != name or session["cleanup"]["inputAfterRestore"] != "Default"
            or not all(session["cleanup"].get(k) is True for k in ("switchBack", "namedClosed", "originalHandleClosed"))
            or not session.get("switchToFixture")):
        raise ValueError("The private input desktop or return to the original unlocked console differs")


def verify_session(session, observation, name):
    verify_restoration(session, name)
    owner = observation["originalWindow"]
    membership = observation["privateWindowBefore"]
    original = session["beforeSwitch"]
    if (session["workerExit"] != 0 or session.get("jobClosed") is not True or observation["privateWorkerPid"] != session["workerPid"]
            or observation["requestedPrivateDesktop"] != name or not DESKTOP["ordinary_console"](observation["desktop"], name)
            or observation["protocol"] != {"status": "observed", "code": 0, "transport": "console"}
            or owner["session"] != original["session"] or observation["subject"] != session["subject"]
            or observation["host"] != "github-hosted" or observation["target"] != TARGET
            or observation["build"]["source"] != session["source"] or observation["run"] != session["run"]
            or observation["attempt"] != session["attempt"] or observation["status"] != "observed"
            or observation["requiredQualifications"] != ["source-frame"] or observation["unmetQualifications"]):
        raise ValueError("The source observation differs from its requested worker, console or native build")
    if (observation["privateWindowAfter"] != membership or membership["desktop"] != name
            or (membership["pid"], membership["hwnd"]) != (owner["pid"], owner["hwnd"])
            or membership["counts"] != {"window": 1, "witness": 1}
            or membership["witness"] != observation["hiddenEnumerationWindow"] or observation["hiddenWindowDestroyed"] is not True):
        raise ValueError("The private GUI membership or hidden witness changed")
    if (observation["mixedDpiPassed"] is not None or observation["rdpRenderingObserved"] is not None
            or observation["rdpSessionObserved"] is not False
            or not all(observation[k] is True for k in ("inventoryPassed", "sourceFrameObserved", "profileRemoved", "drained", "closedToSupervisor"))
            or observation["subjectExit"] != 0):
        raise ValueError("The stationary source frame, process drain or scope of measurement differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained", action="store_true")
    parser.add_argument("--worker-desktop", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not DISPLAY["hosted"]() or os.environ.get("RUNNER_ARCH") != "ARM64"
            or os.environ.get("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.environ.get("GITHUB_REF") != "refs/heads/rewrite/rust"
            or DESKTOP["pe_machine"](DESKTOP["GUI_BINARY"]) != 0xaa64):
        parser.error("Use the native ARM64 rewrite runner with its original GUI build")
    build = DISPLAY["ROOT"] / "artifacts/rust/gui-native" / TARGET
    if args.worker_desktop:
        return DISPLAY["assess"](TARGET, build, ["source-frame"], require_interactive=False,
                                 retained=args.retained, private=args.worker_desktop)
    directory = build / ("windows-display-retained-private" if args.retained else "windows-display-private")
    directory.mkdir(exist_ok=False)
    session = dict(subject="retained" if args.retained else "canonical", source=os.environ["GITHUB_SHA"],
                   run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"], verified=False)
    api = DESKTOP["Desktop"]()
    try:
        with DESKTOP["named_input_desktop"](api, session) as name:
            flags = ["--retained"] if args.retained else []
            DESKTOP["run_worker"](Path(__file__).resolve(), [*flags, "--worker-desktop", name], name,
                                  DISPLAY["ROOT"], session, timeout_seconds=240)
        session["returnedDesktop"] = api.context()
        path = directory / "observation/result.json"
        session["observationSha256"] = DISPLAY["sha256"](path)
        verify_session(session, json.loads(path.read_bytes()), name)
        session["verified"] = True
        return 0
    except Exception:
        session["error"] = traceback.format_exc()
        print(session["error"], file=sys.stderr)
        return 1
    finally:
        DISPLAY["write_json"](directory / "session.json", session)


if __name__ == "__main__":
    sys.exit(main())
