"""Run one fixed GUI observation on the disposable Windows console the application actually owns."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from job import run_worker
from run import GUI_BINARY, ROOT, TARGET, digest, named_input_desktop, pe_machine
from win32 import Desktop, ordinary_console
from worker import HERE, QA, hosted, named_desktop, write


# Bounds include the subprocess's normal shutdown. Language servicing runs outside this job.
TIMEOUTS = {"keyboard": 220, "recovery": 320, "mixed": 600, "text": 260,
            "reader": 720, "ime-installed": 245, "ime-japanese": 245, "warm": 900}


def paths(target, case):
    folder = ROOT / "artifacts/rust/gui-native" / target
    return folder, folder / "windows-session" / case


def command(target, case):
    folder, _ = paths(target, case)
    if case == "keyboard":
        return [QA / "observe-windows-gui.py", GUI_BINARY, folder / "windows-input", "--input-only"]
    if case == "recovery":
        return [QA / "observe-windows-gui.py", GUI_BINARY, folder / "windows-recovery", "--device-recovery"]
    if case == "mixed":
        return [QA / "font-coverage/observe.py", target, "--bidi-candidate", "--require-bidi"]
    if case == "text":
        return [QA / "windows-text/run.py", target]
    if case == "warm":
        return [QA / "windows-warm-window/observe.py", target]
    if case == "reader":
        return [QA / "windows-reader/run.py", "--binary", GUI_BINARY, "--output",
                ROOT / "artifacts/rust/windows-reader" / ("native-" + target)]
    if case in ("ime-installed", "ime-japanese"):
        return [QA / "windows-ime/run.py", GUI_BINARY, folder / "windows-ime" / case.removeprefix("ime-")]
    raise ValueError("Unknown GUI observation")


def obstruction(context, original):
    """Use private input only for a positively identified foreign window on an unlocked Default."""
    observed = original.get("context", {})
    if (not ordinary_console(context, "Default") or not ordinary_console(observed, "Default")
            or observed["session"] != context["session"] or original.get("status") != "observed"):
        return None
    pid = original.get("subjectPid")
    if type(pid) is not int or pid <= 0:
        return None
    last = None
    for phase in ("before", "raised"):
        snapshot = original.get(phase) or {}
        point = snapshot.get("fieldPoint") or {}
        owner = point.get("root") or {}
        if (snapshot.get("subject", {}).get("pid") != pid or point.get("owned") is not False
                or type(owner.get("pid")) is not int or owner["pid"] <= 0 or owner["pid"] == pid
                or not owner.get("hwnd") or not owner.get("executable")):
            return None
        identity = (owner["pid"], owner["hwnd"], owner["executable"])
        if last is not None and identity != last:
            return None
        last = identity
    return {"pid": last[0], "hwnd": last[1], "executable": last[2]}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def placement(folder, build, context, report):
    root = folder / "windows-desktop"
    results = root / "results.json"
    original = root / "original/observation.json"
    index = root / "evidence.sha256"
    if not all(p.is_file() for p in (results, original, index)):
        return None
    runner = read(results)
    entries = dict((name, sha) for sha, name in
                   (line.split("  ", 1) for line in index.read_text(encoding="utf-8").splitlines()))
    if (runner.get("source") != build["source"] or runner.get("run") != os.environ["GITHUB_RUN_ID"]
            or runner.get("attempt") != os.getenv("GITHUB_RUN_ATTEMPT")
            or runner.get("binarySha256") != build["binarySha256"]
            or runner.get("original", {}).get("workerExit") != 0
            or any(digest(path) != entries.get(path.relative_to(root).as_posix()) for path in (results, original))):
        return None
    report["originalObservationSha256"] = entries["original/observation.json"]
    return obstruction(context, read(original))


def run_case(target, case, output, named):
    api = Desktop()
    record = {"processId": os.getpid(), "context": api.context(), "case": case}
    try:
        if not named_desktop(named) or not ordinary_console(record["context"], named):
            raise RuntimeError("The child did not inherit the selected unlocked input desktop")
        with api.enumeration_witness(named, record):
            with (output / "probe.log").open("xb") as log:
                record["exit"] = subprocess.run([sys.executable, *command(target, case)], cwd=ROOT,
                                                creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                                                stdout=log, stderr=subprocess.STDOUT, check=False).returncode
            if not ordinary_console(api.context(), named):
                raise RuntimeError("The input desktop changed before the observation finished")
        return record["exit"]
    finally:
        write(output / "worker.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=[value[0] for value in TARGET.values()])
    parser.add_argument("case", choices=TIMEOUTS)
    parser.add_argument("--named", help=argparse.SUPPRESS)
    args = parser.parse_args()
    triple = TARGET.get(os.getenv("RUNNER_ARCH"))
    if (not hosted() or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"
            or not triple or args.target != triple[0] or pe_machine(GUI_BINARY) != triple[1]):
        parser.error("Use the matching disposable native Windows rewrite job")
    folder, output = paths(args.target, args.case)
    if args.named:
        return run_case(args.target, args.case, output, args.named)
    output.mkdir(parents=True, exist_ok=False)
    report = {"target": args.target, "case": args.case}
    try:
        build = read(folder / "build.json")
        if (build["source"] != os.environ["GITHUB_SHA"] or build["binarySha256"] != digest(GUI_BINARY)
                or build["target"] != args.target):
            raise RuntimeError("The native executable differs from this job's build receipt")
        api = Desktop()
        report.update(source=build["source"], binarySha256=build["binarySha256"], controller=api.context())
        obstruction_record = placement(folder, build, report["controller"], report)
        if obstruction_record:
            report.update(selected="private", obstruction=obstruction_record)
            with named_input_desktop(api, report) as name:
                exit_code = run_worker(Path(__file__).resolve(), [args.target, args.case, "--named", name],
                                       name, ROOT, report, timeout_seconds=TIMEOUTS[args.case])
                child = read(output / "worker.json")
                if (child.get("processId") != report["workerPid"] or child.get("case") != args.case
                        or not ordinary_console(child["context"], name) or child.get("hiddenWindowDestroyed") is not True
                        or exit_code != child.get("exit")):
                    raise RuntimeError("The independently observed native desktop worker did not complete")
        else:
            report["selected"] = "original"
            exit_code = subprocess.run([sys.executable, *command(args.target, args.case)],
                                       cwd=ROOT, check=False).returncode
        report["probeExit"] = exit_code
        return exit_code
    except Exception:
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        write(output / "placement.json", report)


if __name__ == "__main__":
    sys.exit(main())
