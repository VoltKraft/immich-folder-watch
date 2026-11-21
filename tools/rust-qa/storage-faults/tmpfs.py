"""Supervise the fixed 8-MiB private Linux tmpfs experiment inside Bubblewrap."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys


def capacity() -> dict:
    value = os.statvfs("/fault")
    return {"block_size": value.f_frsize, "blocks": value.f_blocks,
            "total_bytes": value.f_frsize * value.f_blocks,
            "free_bytes": value.f_frsize * value.f_bfree,
            "available_bytes": value.f_frsize * value.f_bavail}


def timeout(_signal: int, _frame: object) -> None:
    raise TimeoutError("private ENOSPC scenario exceeded 30 seconds")


def main() -> None:
    output = Path(sys.argv[1])
    mode = sys.argv[2]
    if mode not in ("sensitive", "insensitive"):
        raise ValueError("invalid synthetic casing mode")
    mount = [line for line in Path("/proc/self/mountinfo").read_text().splitlines()
             if line.split()[4] == "/fault"]
    before = capacity()
    if len(mount) != 1 or " - tmpfs " not in mount[0] or before["total_bytes"] != 8388608:
        raise RuntimeError("the actual private tmpfs does not have the fixed 8-MiB limit")
    namespaces = {name: os.readlink("/proc/self/ns/" + name) for name in ("user", "mnt", "net", "pid")}
    status = Path("/proc/self/status").read_text()
    effective = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
    if int(effective, 16) != 0:
        raise RuntimeError("test worker inherited effective capabilities")
    # The reviewed seed files are closed snapshots. A normal readonly WAL
    # connection may still need sidecar locking files, so use a private copy
    # rather than opening the readonly bind as a live SQLite connection.
    seed = Path("/fault/seed")
    seed.mkdir()
    seed_copies = {}
    for name in (mode + ".backup.db", mode + ".expected.json", "result.json"):
        source = Path("/seed") / name
        if source.stat().st_size > 1024 * 1024:
            raise RuntimeError("synthetic seed exceeded its separate 1-MiB file limit")
        if name.endswith(".db") and source.with_name(name + "-wal").exists() and source.with_name(name + "-wal").stat().st_size:
            raise RuntimeError("closed synthetic seed has unexpected live WAL")
        shutil.copyfile(source, seed / name)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256((seed / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("private seed copy changed bytes")
        seed_copies[name] = digest
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(30)
    process = subprocess.Popen(["/probe", "worker", str(seed), str(output), mode, "enospc", "/fault"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    events = []
    full = None
    progress = output.parent / (output.name + "-namespace-progress.json")
    error = ""
    report = {"mountinfo": mount[0], "namespaces": namespaces, "capacity_before": before, "events": events, "seed_copies": seed_copies}
    progress.write_text(json.dumps(report, indent=2) + "\n")
    try:
        for line in process.stdout:
            event = json.loads(line)
            events.append(event)
            progress.write_text(json.dumps(report, indent=2) + "\n")
            if event["phase"] == "enospc-observed":
                full = capacity()
                if full["available_bytes"] != 0 or full["free_bytes"] != 0:
                    raise RuntimeError("ENOSPC barrier did not leave the actual filesystem full")
                if event["os_errno"] != 28 or event["sqlite_extended_error"] != 13:
                    raise RuntimeError("missing native ENOSPC / SQLITE_FULL errors")
                process.stdin.write("release-space\n")
                process.stdin.flush()
        code = process.wait(timeout=10)
        error = process.stderr.read()
        if code or full is None:
            raise RuntimeError(f"ENOSPC child failed: {code}: {error}")
        after = capacity()
        if after["available_bytes"] <= 0:
            raise RuntimeError("space was not available after releasing the owned filler")
        report = {"format": "ifw-private-tmpfs-enospc-v1", "mountinfo": mount[0],
                  "namespaces": namespaces, "effective_capabilities": effective,
                  "capacity_before": before, "capacity_at_error": full, "capacity_after": after,
                  "events": events, "exit_code": code, "seed_copies": seed_copies}
        (output / "tmpfs.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Private 8-MiB tmpfs ENOSPC, SQLite failure and same-volume restore passed")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        report["child_exit_code"] = process.returncode
        report["capacity_at_end"] = capacity()
        report["stderr"] = error + process.stderr.read()
        progress.write_text(json.dumps(report, indent=2) + "\n")
        signal.alarm(0)


if __name__ == "__main__":
    main()
