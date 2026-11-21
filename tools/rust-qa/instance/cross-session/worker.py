"""Noninteractive action for the single registered current-account S4U writer test."""

import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import Accounts, guard_id, instance, read, release, subject_env, validate_area, wait, write, writer


def run(area, result):
    config = read(area / "controller.json")
    accounts = Accounts()
    sid, _, identity = accounts.identify(os.getpid())
    result["worker"] = identity
    if sid != config["sid"] or identity["sessionId"] == config["controller"]["sessionId"]:
        raise RuntimeError("Required the same account in a distinct OS session")
    if identity["elevated"]:
        raise RuntimeError("The scheduled process did not receive a non-elevated token")
    profile, exe = area / "profile", area / "build/instance.exe"
    if guard_id(profile) != config["guard"] or instance.sha(exe) != config["binarySha256"]:
        raise RuntimeError("The guard or native executable differs from the controller receipt")
    env = subject_env(area, config["hosted"])
    session = identity["sessionId"]
    write(area / "worker-ready.json", {"worker": identity, "guard": guard_id(profile)})
    wait(area, "start-first.json")
    with writer(accounts, exe, profile, env, sid, session) as (contender, receipt):
        contender.expect("WRITER_BUSY")
        contender.success()
        result["scheduledRefused"] = receipt
    write(area / "scheduled-refused.json", receipt)
    wait(area, "first-released.json")
    with writer(accounts, exe, profile, env, sid, session) as (holder, receipt):
        holder.expect("WRITER_HELD")
        result["scheduledHolder"] = receipt
        write(area / "scheduled-held.json", receipt)
        wait(area, "release-second.json")
        release(holder)
        result["scheduledReleased"] = True
    result["passed"] = True


def main():
    if os.name != "nt" or len(sys.argv) != 2:
        raise SystemExit("Use the private Windows S4U fixture")
    area = Path(sys.argv[1]).resolve(strict=True)
    validate_area(area)
    result = {"passed": False}
    try:
        run(area, result)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        write(area / "worker-done.json", result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
