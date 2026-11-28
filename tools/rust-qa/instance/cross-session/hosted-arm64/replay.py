"""Replay the two-logon writer protocol and the disposable host cleanup independently."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
from fixture import ROOT, read
from inputs import DIGEST, verify
from standard import qualifies, unchanged_authority

EVENTS = [("original-hold", "HELD"), ("scheduled-refuse", "BUSY"), ("original-hold", "RELEASED"),
          ("scheduled-hold", "HELD"), ("original-refuse", "BUSY"), ("scheduled-hold", "RELEASED"),
          ("original-last", "HELD"), ("original-last", "RELEASED")]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replay_functional(folder):
    compiler = verify(folder / "writer.zip")
    sources = read(folder / "observer-sources.json")
    host, case = [read(folder / name) for name in ("host.json", "case.json")]
    revision = case["revision"]
    require(re.fullmatch("[0-9a-f]{40}", revision), "Invalid measured revision")
    required = {"worker.py", "fixture.py", "observe.py", "standard.py", "batch.py", "scheduler.ps1",
                "scheduler_cleanup.ps1", "native_build.py", "console_levels.py", "hosted-arm64/case.py",
                "hosted-arm64/logon.py", "hosted-arm64/inputs.py", "hosted-arm64/batch_account.py",
                "hosted-arm64/run.ps1", "hosted-arm64/replay.py"}
    expected = {"tools/rust-qa/instance/cross-session/" + source for source in required}
    expected.update(compiler["source_sha256"])
    expected.update((".github/workflows/rust-windows-arm64-writer.yaml", "global.json"))
    require(set(sources) == expected, "Unexpected observer source manifest")
    # The native checkout uses CRLF for sources without an eol rule. Reconstruct the
    # exact bytes at the archived commit when the independent replay runs on Linux.
    for name, digest in sources.items():
        original = subprocess.check_output(["git", "-c", "core.autocrlf=true", "cat-file", "--filters",
                                            revision + ":" + name], cwd=ROOT)
        require(hashlib.sha256(original).hexdigest() == digest, f"Unexpected original observer source {name}")
    require(host.get("accountCreated") is True and "error" not in host and host["controllerExit"] == 0
            and host["grant"] == {"before": [], "after": ["SeBatchLogonRight"]}, "Ordinary logon setup failed")
    require(all(case[k] == host[k] for k in ("revision", "runId", "runAttempt"))
            and re.fullmatch(r"[0-9a-f]{40}", case["revision"])
            and re.fullmatch(r"[0-9a-f]{64}", host["sidSha256"])
            and case["mode"] == "hosted-temporary-standard" and case["target"] == "aarch64-pc-windows-msvc",
            "Unexpected run or test identity")
    require(case["build"] == compiler | {"nativeArchiveSha256":DIGEST}, "Native subject differs from original")
    require(case["passed"] and case["oracleSidMatched"] and case["lockSequenceObserved"] and case["profileGuardRemoved"]
            and case["participantsExited"] == 7 and case["batchRightsSource"] == "temporary SID in host.json",
            "The native case is incomplete")
    require(case["originalBootstrapExit"] == host["taskLastResult"] == 0, "Task or participant exit failed")
    require(host["taskFolderTrusteesMatched"] and re.fullmatch(r"\\IfwWriterArm_[0-9a-f]{32}", host["taskFolder"])
            and re.fullmatch(r"\{?[0-9a-fA-F-]{36}\}?", host["taskInstance"]), "Unexpected task folder or instance")
    definition = host["taskDefinition"]
    require(definition == {"logonType": 1, "runLevel": 0, "currentSidMatched": True, "fixedActionMatched": True,
                           "triggers": 0, "actionCount": 1}, "Unexpected authenticated task principal or action")
    sid = host["sidSha256"]
    sessions = {"original":host["runnerSession"], "scheduled":0}
    require(sessions["original"] > 0 and qualifies(case["controller"])
            and case["controller"]["sidSha256"] == sid and case["controller"]["sessionId"] == sessions["original"],
            "The original controller was not the new ordinary user")
    logons = []
    for role, file in (("original", "original-bootstrap-done"), ("scheduled", "worker-done")):
        command = read(folder / (file + ".json"))
        user = case[role+"WorkerObservedByController"]
        require(command["passed"] and command["mode"] == "inherited-standard-user" and
                command["bootstrap"] == case[role+"Bootstrap"] == user and qualifies(user)
                and user["sidSha256"] == sid and user["sessionId"] == user["tokenSessionId"] == sessions[role],
                "The actual ordinary participant differs")
        logon = command["osLogon"]
        require(logon["wtsSessionId"] == sessions[role] and logon["logonType"] == (2 if role == "original" else 4)
                and re.fullmatch("[0-9a-f]{64}", logon["authenticationIdSha256"]), "Unexpected WTS or local logon type")
        logons.append(logon["authenticationIdSha256"])
    require(logons[0] != logons[1], "The test reused a single authenticated logon")
    writers = case["writersObservedBeforeResume"]
    require(set(writers) == {p for p, _ in EVENTS} and len({(w["pid"], w["created100ns"]) for w in writers.values()}) == 5,
            "Expected five original native writers")
    for name, writer in writers.items():
        role = name.split("-")[0]
        require(writer["image"].lower() == "instance.exe" and writer["sidSha256"] == sid and qualifies(writer)
                and unchanged_authority(writer, case[role+"WorkerObservedByController"]), "Writer image, SID or token changed")
    guard = case["guard"]
    require(all(int(guard[k]) > 0 for k in ("fileId", "volume")), "Invalid original guard identity")
    require(len(case["observedWriterEvents"]) == len(EVENTS), "Missing lock events")
    for (name, event), actual in zip(EVENTS, case["observedWriterEvents"], strict=True):
        expected = {"phase":name, "event":"WRITER_"+event, "guard":guard, "pid":writers[name]["pid"],
                    "created100ns":writers[name]["created100ns"]}
        if event != "HELD":
            expected["exitCode"] = 0
        require(actual == expected, "Unexpected lock event, file identity or writer identity")
    return {"passed": True, "sessions": sessions, "logonTypes": [2, 4], "writers": len(writers),
            "lockEvents": len(EVENTS), "guard": guard, "participantsExited": case["participantsExited"],
            "originalArchive": DIGEST}


def replay_cleanup(folder):
    host = read(folder / "host.json")
    fields = ("accountRemoved", "taskRemoved", "profileRemoved", "stageRemoved", "serviceRestored",
              "userProcessesExited", "taskFolderRemoved", "profileDirectoryRemoved")
    # A missing observation in an older archive stays visible and cannot satisfy the cleanup gate.
    observations = {key: host.get(key) for key in fields}
    observations["batchRightRestored"] = host.get("restore") == {"before": ["SeBatchLogonRight"], "after": []}
    failures = {key: value for key, value in host.items() if key.startswith("cleanupFailure")}
    return {"passed": all(value is True for value in observations.values()) and not failures,
            "observations": observations, "failures": failures, "profileStates": host.get("profileStates"),
            "profileWaitSeconds": host.get("profileWaitSeconds")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--check", choices=("functional", "cleanup", "all"), default="all")
    args = parser.parse_args()
    result = {}
    if args.check in ("functional", "all"):
        result["functional"] = replay_functional(args.folder)
    if args.check in ("cleanup", "all"):
        result["cleanup"] = replay_cleanup(args.folder)
    print(json.dumps(result, indent=2))
    sys.exit(0 if all(check["passed"] for check in result.values()) else 1)
