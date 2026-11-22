"""Exercise the existing Rust file guard using one account in two actual Windows OS sessions."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

from batch import batch_rights, eligible
from fixture import (Accounts, HERE, HOSTED, MARKER, ROOT, guard_id, instance, read,
                     subject_env, verified_process, wait, write, participants_exited)
from standard import AMBIENT, EXISTING, STANDARD, qualifies, required_authority, unchanged_authority
from worker import PHASES

TARGETS = {"X64": "x86_64-pc-windows-msvc", "ARM64": "aarch64-pc-windows-msvc"}


def prepare(area, args, result, mode, reference=None):
    profile = area / "profile"
    profile.mkdir(mode=0o700)
    (profile / ".ifw-instance-fixture").write_bytes(MARKER)
    (profile / "writer.lock").touch(mode=0o600, exist_ok=False)
    for name in ("tmp", "roaming", "local"):
        (area / "synthetic-home" / name).mkdir(parents=True)
    env = subject_env(area, HOSTED)
    accounts = Accounts()
    sid, _, baseline = accounts.identify(os.getpid())
    result["controller"] = baseline
    if mode == EXISTING and not qualifies(baseline):
        raise RuntimeError("The original existing session must already be an ordinary Windows user")
    if reference is None:
        exe, oracle, build = instance.build(args, area / "build", env)
    else:
        original_image, oracle, build = reference
        exe = area / "build/instance.exe"
        exe.parent.mkdir()
        shutil.copyfile(original_image, exe)
        if instance.sha(exe) != build["rust_binary_sha256"]:
            raise RuntimeError("The new private profile did not receive the frozen Rust writer")
    result["build"] = build
    arch = "arm64" if args.target.startswith("aarch64-") else "x64"
    actual = subprocess.check_output([*oracle, "identity", profile, arch], cwd=area, env=env, text=True,
                                     timeout=25).strip()
    if actual != sid:
        raise RuntimeError("The independently compiled identity oracle and native token disagree")
    result["oracleSidMatched"] = True
    result["guard"] = guard_id(profile)
    write(area / "controller.json", {"controller": baseline, "mode": mode, "hosted": HOSTED, "guard": result["guard"],
                                     "binarySha256": build["rust_binary_sha256"], "pythonSha256": instance.sha(Path(sys.executable)),
                                     "workerSha256": instance.sha(HERE / "worker.py"),
                                     "consoleLevelsSha256": instance.sha(HERE / "console_levels.py"), "expires": time.time() + 300})
    return env, accounts, sid, exe


def native_handover(area, accounts, sid, exe, task, result):
    baselines = {}
    for role in ("scheduled", "original"):
        result[role + "Bootstrap"] = wait(area, role + "-bootstrap.json", timeout=110,
                                          scheduler=task if role == "scheduled" else None, collect_bootstrap=True)
    for role in PHASES:
        active_task = task if role == "scheduled" else None
        ready = wait(area, role + "-ready.json", timeout=110, scheduler=active_task)
        parent = result[role + "Bootstrap"]
        claimed = ready["worker"]
        actual = verified_process(accounts, claimed["pid"], sid, Path(sys.executable), parent["sessionId"], claimed["created100ns"])
        if (ready["guard"] != result["guard"] or actual != claimed
                or not required_authority(result["mode"], actual, parent)
                or (result["mode"] == AMBIENT and (parent != actual or
                    (role == "original" and not unchanged_authority(actual, result["controller"]))))
                or (actual["sessionId"] == result["controller"]["sessionId"]) != (role == "original")):
            raise RuntimeError("The independently inspected participant differs from the trial authority or session")
        if result["mode"] == EXISTING and (not qualifies(parent) or actual["sessionId"] == 0):
            raise RuntimeError("A pre-existing ordinary, interactive Windows session is required")
        baselines[role] = actual
        result[role + "WorkerObservedByController"] = actual

    events = result["observedWriterEvents"] = []
    writers = result["writersObservedBeforeResume"] = {}

    def finished(name, expected, active_task=None):
        receipt = wait(area, name + "-finished.json", scheduler=active_task)
        actual = writers[name]
        if receipt != {"event": expected, "exitCode": 0, "pid": actual["pid"],
                       "created100ns": actual["created100ns"], "guard": result["guard"]}:
            raise RuntimeError("Native exit, lock response, writer identity or guard differs")
        events.append({"phase": name, **receipt})

    def phase(name, hold):
        role = name.split("-")[0]
        active_task = task if role == "scheduled" else None
        write(area / (name + "-launch.json"), True)
        claimed = wait(area, name + "-created.json", scheduler=active_task)
        actual = verified_process(accounts, claimed["pid"], sid, exe, baselines[role]["sessionId"], claimed["created100ns"])
        if (actual != claimed or not required_authority(result["mode"], actual, baselines[role])
                or instance.sha(exe) != result["build"]["rust_binary_sha256"]):
            raise RuntimeError("The independently inspected suspended native writer differs")
        if any((old["pid"], old["created100ns"]) == (actual["pid"], actual["created100ns"]) for old in writers.values()):
            raise RuntimeError("Each phase requires a separately created native writer")
        writers[name] = actual
        write(area / (name + "-verified.json"), True)
        if hold:
            held = wait(area, name + "-held.json", scheduler=active_task)
            if held != actual or held != verified_process(accounts, actual["pid"], sid, exe, actual["sessionId"], actual["created100ns"]):
                raise RuntimeError("The live holder identity or authority changed")
            current_guard = guard_id(area / "profile")
            if current_guard != result["guard"]:
                raise RuntimeError("The file identity changed while the writer held the lock")
            events.append({"phase": name, "event": "WRITER_HELD", "pid": actual["pid"],
                           "created100ns": actual["created100ns"], "guard": current_guard})
        else:
            finished(name, "WRITER_BUSY", active_task)
        return actual

    def finish(name):
        write(area / (name + "-release.json"), True)
        finished(name, "WRITER_RELEASED")

    result["firstHolder"] = phase("original-hold", True)
    result["scheduledRefusedWhileOriginalHeld"] = phase("scheduled-refuse", False)
    finish("original-hold")
    result["firstReleased"] = True
    result["scheduledHolderObservedByController"] = phase("scheduled-hold", True)
    result["originalRefusedWhileScheduledHeld"] = phase("original-refuse", False)
    finish("scheduled-hold")
    result["originalReacquiredAfterScheduledRelease"] = phase("original-last", True)
    finish("original-last")
    for role in PHASES:
        if not wait(area, role + "-done.json")["passed"]:
            raise RuntimeError("A native participant failed to finish")
    if guard_id(area / "profile") != result["guard"]:
        raise RuntimeError("The pre-existing guard file changed identity")
    result["lockSequenceObserved"] = True


def original(area, env):
    return subprocess.Popen([sys.executable, "-I", "-B", HERE / "worker.py", "--original", area],
                            cwd=area, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def finish_process(proc):
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def scheduled(area, args, result, reference):
    env, accounts, sid, exe = prepare(area, args, result, result["mode"], reference)
    result["batchRightsBefore"] = batch_rights(accounts)
    if not eligible(result["batchRightsBefore"]):
        raise RuntimeError("Current account lacks an existing effective batch-logon assignment")
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("The local system Windows PowerShell is required")
    scheduler_args = [powershell, "-NoLogo", "-NoProfile", "-NonInteractive",
                      "-File", str(HERE / "scheduler.ps1"), "-Area", str(area)]
    with (args.output / "scheduler.log").open("ab") as logfile:
        logfile.write((result["mode"] + "\n").encode("ascii"))
        logfile.flush()
        task = subprocess.Popen(scheduler_args, cwd=area, env=env, stdin=subprocess.DEVNULL,
                                stdout=logfile, stderr=subprocess.STDOUT)
        result["schedulerStarted"] = True
        controller_side = None
        completed = False
        try:
            controller_side = original(area, env)
            native_handover(area, accounts, sid, exe, task, result)
            if not wait(area, "worker-done.json")["passed"] or not wait(area, "original-bootstrap-done.json")["passed"]:
                raise RuntimeError("The participants did not complete")
            completed = True
        finally:
            try:
                if not completed:
                    (area / "abort").touch()
                if controller_side:
                    finish_process(controller_side)
                    result["originalBootstrapExit"] = controller_side.returncode
            finally:
                try:
                    finish_process(task)
                    result["schedulerExit"] = task.returncode
                finally:
                    cleanup = subprocess.run([*scheduler_args, "-VerifyCleanup"], cwd=area, env=env,
                                             stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
                                             timeout=45, check=False)
                    result["cleanupExit"] = cleanup.returncode
                    result["batchRightsAfter"] = batch_rights(accounts)
                    if result["batchRightsAfter"] != result["batchRightsBefore"]:
                        raise RuntimeError("The observed current-account batch-logon assignment changed")
    if (result["schedulerExit"] or result["originalBootstrapExit"] or result["cleanupExit"]
            or read(area / "scheduler.json").get("lastTaskResult") != 0
            or not read(area / "scheduler.json").get("cleanupVerified")
            or not read(area / "cleanup.json").get("cleanupVerified")):
        raise RuntimeError("Task result or removal readback failed")
    result["passed"] = True


def hosted_case(args, runner_temp, mode, reference):
    area = runner_temp / ("IfwQaCross_" + uuid.uuid4().hex)
    area.mkdir(mode=0o700)
    prefix = "ambient-" if mode == AMBIENT else ""
    result = {"passed": False, "attempted": True, "mode": mode, "target": args.target, "source": os.environ["GITHUB_SHA"],
              "ambientGuardPassed": None, "standardUserGuardPassed": None, "lockSequenceObserved": False,
              "temporaryProfileRemoved": False}
    try:
        scheduled(area, args, result, reference)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        # The unprefixed raw standard-user names remain available to existing readers.
        try:
            role_names = [role + suffix for role in PHASES
                          for suffix in ("-bootstrap.json", "-basic-user.json", "-attempt.json", "-done.json", "-ready.json")]
            phase_names = [name + suffix for phases in PHASES.values() for name, _ in phases
                           for suffix in ("-created.json", "-held.json", "-finished.json")]
            for name in ("worker-done.json", "scheduler.json", "cleanup.json", "original-bootstrap-done.json", *role_names, *phase_names):
                if (area / name).is_file():
                    shutil.copyfile(area / name, args.output / (prefix + name))
        except OSError:
            result.update(passed=False, receiptError=traceback.format_exc())
        try:
            result["participantExitsVerified"] = participants_exited(area)
            if result.get("schedulerStarted") and ("schedulerExit" not in result or result.get("cleanupExit") != 0 or
                    not (area / "cleanup.json").is_file() or not read(area / "cleanup.json").get("cleanupVerified")):
                raise RuntimeError("Could not verify removal of the exact private scheduled task")
            shutil.rmtree(area)
            result["temporaryProfileRemoved"] = not area.exists()
        except (OSError, RuntimeError):
            result.update(passed=False, cleanupError=traceback.format_exc())
        result["passed"] = bool(result["passed"] and result["lockSequenceObserved"] and result["temporaryProfileRemoved"])
        result["ambientGuardPassed" if mode == AMBIENT else "standardUserGuardPassed"] = result["passed"]
        write(args.output / ("ambient-case.json" if mode == AMBIENT else "standard-case.json"), result)
    return result


def summarize(ambient, standard):
    def complete(case, mode, field):
        return case.get("mode") == mode and all(case.get(key) is True for key in (
            "attempted", field, "passed", "lockSequenceObserved", "temporaryProfileRemoved"))
    ambient_pass = complete(ambient, AMBIENT, "ambientGuardPassed")
    standard_pass = complete(standard, STANDARD, "standardUserGuardPassed")
    return {**standard, "passed": ambient_pass and standard_pass, "ambientGuardPassed": ambient_pass,
            "standardUserGuardPassed": standard_pass, "ambientCase": "ambient-case.json",
            "standardUserCase": "standard-case.json"}


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
    metadata = {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"], "target": args.target,
                "sources": {p.relative_to(ROOT).as_posix(): instance.sha(p)
                            for p in sorted([*HERE.glob("*.py"), HERE / "scheduler.ps1"])}}
    ambient, standard = {}, {}
    build = None
    try:
        with tempfile.TemporaryDirectory(prefix="IfwQaCrossBuild_", dir=runner_temp) as temp:
            build = Path(temp)
            for name in ("tmp", "roaming", "local"):
                (build / "synthetic-home" / name).mkdir(parents=True)
            reference = instance.build(args, build / "build", subject_env(build, HOSTED))
            ambient = hosted_case(args, runner_temp, AMBIENT, reference)
            if not ambient["temporaryProfileRemoved"]:
                raise RuntimeError("The first trial did not confirm cleanup of its owned resources")
            standard = hosted_case(args, runner_temp, STANDARD, reference)
    except Exception:
        metadata["harnessError"] = traceback.format_exc()
    metadata["sharedBuildRemoved"] = None if build is None else not build.exists()
    for name, case, mode, fact in (("ambient", ambient, AMBIENT, "ambientGuardPassed"),
                                   ("standard", standard, STANDARD, "standardUserGuardPassed")):
        if not case:
            write(args.output / (name + "-case.json"), {"mode": mode, "attempted": False, "target": args.target,
                                                        "source": metadata["source"], "ambientGuardPassed": None,
                                                        "standardUserGuardPassed": None, fact: False,
                                                        "reason": metadata.get("harnessError", "Missing case")})
    result = {**summarize(ambient, standard), **metadata}
    if "harnessError" in result or result["sharedBuildRemoved"] is not True:
        result["passed"] = False
    write(args.output / "result.json", result)
    files = sorted(p for p in args.output.iterdir() if p.is_file())
    (args.output / "evidence.sha256").write_text("".join(f"{instance.sha(p)}  {p.name}\n" for p in files), encoding="utf-8")
    print(f"Same-account native writer results, ambient={result['ambientGuardPassed']}, standard={result['standardUserGuardPassed']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
