"""Independently compare both ordinary logons, five frozen ARM64 writers and all lock events."""
import hashlib
import json
from pathlib import Path
import re
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


def replay(folder):
    compiler = verify(folder / "writer.zip")
    sources = read(folder / "observer-sources.json")
    required = {"worker.py", "fixture.py", "observe.py", "standard.py", "batch.py", "scheduler.ps1",
                "scheduler_cleanup.ps1", "native_build.py", "console_levels.py", "hosted-arm64/case.py",
                "hosted-arm64/logon.py", "hosted-arm64/inputs.py", "hosted-arm64/batch_account.py",
                "hosted-arm64/run.ps1", "hosted-arm64/replay.py"}
    require(all("tools/rust-qa/instance/cross-session/" + source in sources for source in required),
            "Incomplete observer source manifest")
    require(".github/workflows/rust-windows-arm64-writer.yaml" in sources, "Missing native workflow source")
    require(all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h for name, h in sources.items()),
            "Unexpected original observer sources")
    host, case = [read(folder / name) for name in ("host.json", "case.json")]
    require(all(host.get(k) is True for k in ("accountCreated", "accountRemoved", "taskRemoved", "profileRemoved",
                    "stageRemoved", "serviceRestored", "userProcessesExited")) and not any(k.startswith("cleanupFailure") for k in host)
            and "error" not in host and host["controllerExit"] == 0, "The isolated host or its cleanup failed")
    require(host["grant"] == {"before":[], "after":["SeBatchLogonRight"]} and
            host["restore"] == {"before":["SeBatchLogonRight"], "after":[]}, "Temporary assignment was not restored")
    require(all(case[k] == host[k] for k in ("revision", "runId", "runAttempt"))
            and re.fullmatch(r"[0-9a-f]{40}", case["revision"])
            and re.fullmatch(r"[0-9a-f]{64}", host["sidSha256"])
            and case["mode"] == "hosted-temporary-standard" and case["target"] == "aarch64-pc-windows-msvc",
            "Unexpected run or test identity")
    require(case["build"] == compiler | {"nativeArchiveSha256":DIGEST}, "Native subject differs from original")
    require(case["passed"] and case["oracleSidMatched"] and case["lockSequenceObserved"] and case["profileGuardRemoved"]
            and case["participantsExited"] == 7 and case["batchRightsBefore"] == case["batchRightsAfter"]
            and case["batchRightsBefore"]["directAllow"] and not case["batchRightsBefore"]["directDeny"]
            and not case["batchRightsBefore"]["groupDeny"], "The native case is incomplete")
    require(case["originalBootstrapExit"] == case["schedulerExit"] == case["cleanupExit"] == 0
            and read(folder / "cleanup.json")["cleanupVerified"], "Task or participant exit failed")
    scheduler = read(folder / "scheduler.json")
    require(scheduler["registered"] and scheduler["cleanupVerified"] and scheduler["lastTaskResult"] == 0
            and scheduler["definition"]["logonType"] == 2 and scheduler["definition"]["runLevel"] == 0
            and scheduler["definition"]["fixedActionMatched"] and scheduler["definition"]["currentSidMatched"],
            "The task did not use the expected standard-user S4U principal")
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
    return {"sessions":sessions, "writers":len(writers), "lockEvents":len(EVENTS), "originalArchive":DIGEST}


if __name__ == "__main__":
    print(json.dumps(replay(Path(sys.argv[1])), indent=2))
