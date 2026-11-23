"""Bind each ordinary-user observation to the same installed reader, runtime and VM."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def verify_phase(record, phase, trial, reader, app_commit, runtime_commit):
    app = record["app"]
    if (record["status"] != "passed" or record["phase"] != phase or record["trial"] != trial
            or app["id"] != "org.example.IfwPortalLease//test" or app["readerSha256"] != reader
            or app["commit"] != app_commit or app["runtimeCommit"] != runtime_commit):
        raise ValueError(f"Wrong installed app, runtime, guest or observation for {phase}")


def original_backing(home, phase):
    from contextlib import ExitStack
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(home, flags)
        stack.callback(os.close, fd)
        for name in ("ifw-portal-" + phase, "source", "album"):
            fd = os.open(name, flags, dir_fd=fd)
            stack.callback(os.close, fd)
        file = os.open("original.jpg", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file, "rb") as stream:
            meta = os.fstat(stream.fileno())
            if not stat.S_ISREG(meta.st_mode) or meta.st_size != len(b"Synthetic upload fixture\n"):
                raise ValueError("Unexpected original test file")
            return {"device": meta.st_dev, "inode": meta.st_ino, "size": meta.st_size,
                    "sha256": hashlib.sha256(stream.read(meta.st_size + 1)).hexdigest()}


def collect(seed, output, app_commit, runtime_commit, candidate_status, restore_status, dpkg_state, home):
    inputs = json.loads((seed / "inputs.json").read_text())
    trial = (seed.parent / "trial-id").read_text().strip()
    stage = (seed.parent / "stage").read_text().strip()
    phases = {"lease": ["stock", "candidate", "restored"], "lease-stock": ["stock"]}[stage]
    result = dict(status="failed", trial=trial, inputs=inputs, appCommit=app_commit, runtimeCommit=runtime_commit,
                  candidateExit=candidate_status, restoreExit=restore_status, finalDpkg=dpkg_state,
                  phases={}, errors={}, finalBacking={})
    try:
        if (not re.fullmatch(r"[a-f0-9]{64}", app_commit) or runtime_commit != inputs["runtime"]["commit"]
                or not re.fullmatch(r"[a-f0-9]{32}", trial)):
            raise ValueError("Unexpected seed or installed commit")
        for phase in phases:
            path = output / (phase + ".json")
            try:
                raw = path.read_bytes()
                result["phases"][phase] = hashlib.sha256(raw).hexdigest()
                phase_result = json.loads(raw)
                verify_phase(phase_result, phase, trial, inputs["reader"], app_commit, runtime_commit)
                result["finalBacking"][phase] = original_backing(home, phase)
                if result["finalBacking"][phase] != phase_result["originalBacking"]:
                    raise ValueError("The original backing changed across the package transitions")
            except (OSError, KeyError, TypeError, ValueError) as error:
                result["errors"][phase] = str(error)
        if result["errors"]:
            raise ValueError(f"Invalid installed lease observations: {result['errors']}")
        if candidate_status or restore_status or dpkg_state != "install ok installed 1.18.4-1ubuntu2.24.04.3":
            raise ValueError("An offline package transition failed or left an unexpected final package")
        result["status"] = "passed"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        (output / "lease-result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    seed, output, app, runtime, candidate, restored, dpkg = sys.argv[1:]
    collect(Path(seed), Path(output), app, runtime, int(candidate), int(restored), dpkg, Path("/home/ifwqa"))
