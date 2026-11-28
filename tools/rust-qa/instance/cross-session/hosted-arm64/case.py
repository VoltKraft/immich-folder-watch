"""Run the established file-lock handover from a normal local logon of the new account."""
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
from fixture import Accounts, HOSTED, participants_exited, read, write
from inputs import DIGEST, TARGET, verify
from native_build import stage
from observe import scheduled
from standard import TEMPORARY, qualifies


def run(root):
    settings = read(root / "launch.json")
    if (root != HERE.parents[5] or root.parent != Path(os.environ["ProgramData"]).resolve()
            or not all(os.environ.get(k) == v for k, v in HOSTED.items())
            or os.environ.get("RUNNER_ARCH") != "ARM64" or os.environ.get("RUNNER_OS") != "Windows"
            or os.environ.get("GITHUB_WORKFLOW") != "Rust Windows ARM64 standard-user writer"
            or os.environ.get("GITHUB_SHA") != settings["revision"]
            or os.environ.get("GITHUB_RUN_ID") != settings["runId"]
            or os.environ.get("GITHUB_RUN_ATTEMPT") != settings["runAttempt"]):
        raise RuntimeError("Expected the staged controller from its original ARM64 job")
    work = root / "work"
    sid, _, identity = Accounts().identify(os.getpid())
    if (not qualifies(identity) or identity["sidSha256"] != settings["sidSha256"]
            or identity["sessionId"] == 0 or identity["sessionId"] != settings["runnerSession"]):
        raise RuntimeError("The credentialed controller did not enter the runner session as the new ordinary user")
    archive = root / "writer.zip"
    verify(archive)
    os.environ["RUNNER_TEMP"] = str(work)
    os.environ["PATH"] = str(Path(settings["dotnet"]).parent) + os.pathsep + os.environ["PATH"]
    output = work / "receipts"
    output.mkdir()
    exe, oracle, build = stage(archive, DIGEST, work / "native", TARGET, os.environ)
    if Path(oracle[0]).resolve() != Path(settings["dotnet"]).resolve():
        raise RuntimeError("Unexpected .NET runtime for the identity oracle")
    area = work / settings["taskName"]
    if area.name != "IfwQaCross_" + uuid.UUID(hex=area.name.removeprefix("IfwQaCross_")).hex:
        raise ValueError("Invalid generated task name")
    area.mkdir()
    result = {"mode": TEMPORARY, "passed": False, "lockSequenceObserved": False, "target": TARGET,
              "revision": settings["revision"], "runId": settings["runId"], "runAttempt": settings["runAttempt"]}
    try:
        scheduled(area, SimpleNamespace(target=TARGET, output=output), result, (exe, oracle, build))
    except Exception as exc:
        result.update(passed=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            result["participantsExited"] = participants_exited(area)
            for name in ("original-bootstrap-done", "worker-done", "scheduler", "cleanup"):
                file = area / (name + ".json")
                if file.is_file():
                    shutil.copyfile(file, output / file.name)
            result["profileGuardRemoved"] = False
            shutil.rmtree(area)
            result["profileGuardRemoved"] = not area.exists()
            shutil.rmtree(work / "native")
            if result["passed"]:
                logons = [read(output / (name + ".json"))["osLogon"]
                          for name in ("original-bootstrap-done", "worker-done")]
                if (result["participantsExited"] != 7 or not result["profileGuardRemoved"]
                        or len({event["authenticationIdSha256"] for event in logons}) != 2
                        or [event["logonType"] for event in logons] != [2, 4]):
                    raise RuntimeError("The two logons and seven process exits were not verified")
        except Exception as exc:
            result.update(passed=False, cleanupError=f"{type(exc).__name__}: {exc}")
        write(output / "case.json", result)
    return result["passed"]


if __name__ == "__main__":
    sys.exit(0 if run(Path(sys.argv[1]).resolve(strict=True)) else 1)
