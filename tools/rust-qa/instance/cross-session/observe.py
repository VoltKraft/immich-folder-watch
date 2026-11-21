"""Exercise the existing Rust file guard using one account in two actual Windows OS sessions."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import uuid

from batch import batch_rights, eligible
from fixture import (Accounts, HERE, HOSTED, MARKER, ROOT, guard_id, instance, read, release,
                     subject_env, verified_process, wait, write, writer)

TARGETS = {"X64": "x86_64-pc-windows-msvc", "ARM64": "aarch64-pc-windows-msvc"}


def verify_initial_refusal(area, accounts, sid, baseline, task, result):
    ready = wait(area, "worker-ready.json", timeout=75, scheduler=task)
    remote = ready["worker"]
    if (remote["sessionId"] == baseline["sessionId"] or remote["elevated"]
            or ready["guard"] != result["guard"]):
        raise RuntimeError("A distinct, non-elevated native Windows session on the same guard is required")
    actual_worker = verified_process(accounts, remote["pid"], sid, Path(sys.executable), remote["sessionId"])
    if actual_worker != remote:
        raise RuntimeError("The controller's live token observation disagrees with the S4U worker")
    result["scheduledWorkerObservedByController"] = actual_worker
    write(area / "start-first.json", True)
    refused = wait(area, "scheduled-refused.json", scheduler=task)
    if refused["sessionId"] != remote["sessionId"] or refused["sidSha256"] != baseline["sidSha256"]:
        raise RuntimeError("Scheduled contender did not belong to the verified worker account and session")
    result["scheduledRefusedWhileOriginalHeld"] = refused


def handover(area, exe, env, accounts, sid, baseline, subject, task, result):
    verify_initial_refusal(area, accounts, sid, baseline, task, result)
    release(subject)
    result["firstReleased"] = True
    write(area / "first-released.json", True)
    remote = result["scheduledWorkerObservedByController"]
    claimed = wait(area, "scheduled-held.json", scheduler=task)
    actual = verified_process(accounts, claimed["pid"], sid, exe, remote["sessionId"])
    if actual != claimed or actual["elevated"]:
        raise RuntimeError("S4U holder identity differed between the sessions")
    result["scheduledHolderObservedByController"] = actual
    profile = area / "profile"
    with writer(accounts, exe, profile, env, sid, baseline["sessionId"]) as (contender, identity):
        contender.expect("WRITER_BUSY")
        contender.success()
        result["originalRefusedWhileScheduledHeld"] = identity
    write(area / "release-second.json", True)
    worker = wait(area, "worker-done.json", scheduler=task)
    if not worker["passed"] or not worker["scheduledReleased"]:
        raise RuntimeError("The scheduled holder did not release cleanly")
    with writer(accounts, exe, profile, env, sid, baseline["sessionId"]) as (last, identity):
        last.expect("WRITER_HELD")
        release(last)
        result["originalReacquiredAfterScheduledRelease"] = identity
    if guard_id(profile) != result["guard"]:
        raise RuntimeError("The empty persistent guard file changed identity")


def scheduled(area, args, result):
    profile = area / "profile"
    profile.mkdir(mode=0o700)
    (profile / ".ifw-instance-fixture").write_bytes(MARKER)
    (profile / "writer.lock").touch(mode=0o600, exist_ok=False)
    for name in ("tmp", "roaming", "local"):
        (area / "synthetic-home" / name).mkdir(parents=True)
    hosted = {key: os.environ[key] for key in HOSTED}
    env = subject_env(area, hosted)
    exe, oracle, build = instance.build(args, area / "build", env)
    result["build"] = build
    accounts = Accounts()
    sid, _, baseline = accounts.identify(os.getpid())
    result["controller"] = baseline
    result["batchRightsBefore"] = batch_rights(accounts)
    if not eligible(result["batchRightsBefore"]):
        raise RuntimeError("Current account lacks an existing effective batch-logon assignment")
    arch = "arm64" if args.target.startswith("aarch64-") else "x64"
    actual = subprocess.check_output([*oracle, "identity", profile, arch], cwd=area, env=env, text=True,
                                     timeout=25).strip()
    if actual != sid:
        raise RuntimeError("The independently compiled identity oracle and native token disagree")
    result["oracleSidMatched"] = True
    result["guard"] = guard_id(profile)
    write(area / "controller.json", {"controller": baseline, "sid": sid, "hosted": hosted,
                                     "guard": result["guard"], "binarySha256": build["rust_binary_sha256"]})
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("The local system Windows PowerShell is required")
    scheduler_args = [powershell, "-NoLogo", "-NoProfile", "-NonInteractive",
                      "-File", str(HERE / "scheduler.ps1"), "-Area", str(area)]
    with writer(accounts, exe, profile, env, sid, baseline["sessionId"]) as (first, info):
        first.expect("WRITER_HELD")
        result["firstHolder"] = info
        with (args.output / "scheduler.log").open("wb") as logfile:
            task = subprocess.Popen(scheduler_args, cwd=area, env=env, stdin=subprocess.DEVNULL,
                                    stdout=logfile, stderr=subprocess.STDOUT)
            completed = False
            try:
                handover(area, exe, env, accounts, sid, baseline, first, task, result)
                completed = True
            finally:
                # The worker sees this file while waiting and closes its own child through Child.__exit__.
                if not completed:
                    (area / "abort").touch()
                try:
                    task.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # The independent readback below owns the exact same registered name and action.
                    task.kill()
                    task.wait(timeout=10)
                result["schedulerExit"] = task.returncode
                cleanup = subprocess.run([*scheduler_args, "-VerifyCleanup"], cwd=area, env=env,
                                         stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
                                         timeout=45, check=False)
                result["cleanupExit"] = cleanup.returncode
                result["batchRightsAfter"] = batch_rights(accounts)
                if result["batchRightsAfter"] != result["batchRightsBefore"]:
                    raise RuntimeError("The observed current-account batch-logon assignment changed")
    if (result["schedulerExit"] or result["cleanupExit"]
            or read(area / "scheduler.json").get("lastTaskResult") != 0
            or not read(area / "scheduler.json").get("cleanupVerified")
            or not read(area / "cleanup.json").get("cleanupVerified")):
        raise RuntimeError("Task result or removal readback failed")
    result["passed"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=list(TARGETS.values()))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.name != "nt" or any(os.getenv(k) != v for k, v in HOSTED.items())
            or TARGETS.get(os.getenv("RUNNER_ARCH")) != args.target):
        parser.error("The matching native GitHub-hosted Windows rewrite job is required")
    args.output = args.output.resolve()
    if args.output != (ROOT / "artifacts/rust/instance-native" / args.target / "cross-session").resolve():
        parser.error("Use the target-specific cross-session evidence directory")
    args.output.mkdir(parents=True, exist_ok=False)
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    area = runner_temp / ("IfwQaCross_" + uuid.uuid4().hex)
    area.mkdir(mode=0o700)
    result = {"passed": False, "source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
              "target": args.target, "sources": {
                  p.relative_to(ROOT).as_posix(): instance.sha(p)
                  for p in sorted([*HERE.glob("*.py"), HERE / "scheduler.ps1"])}}
    try:
        scheduled(area, args, result)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        # Exclude controller.json with its transient account SID. Retain the independent worker and scheduler receipts.
        for name in ("worker-done.json", "scheduler.json", "cleanup.json"):
            if (area / name).is_file():
                shutil.copyfile(area / name, args.output / name)
        try:
            shutil.rmtree(area)
            result["temporaryProfileRemoved"] = not area.exists()
        except OSError:
            result.update(passed=False, cleanupError=traceback.format_exc())
        write(args.output / "result.json", result)
        files = sorted(p for p in args.output.iterdir() if p.is_file())
        (args.output / "evidence.sha256").write_text("".join(
            f"{instance.sha(p)}  {p.name}\n" for p in files), encoding="utf-8")
    if not result["passed"]:
        print(result.get("error", result.get("cleanupError", "S4U trial failed")), file=sys.stderr)
        return 1
    print("Rust file-lock exclusion and handover passed across two same-account Windows sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
