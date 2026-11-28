"""Run and replay a SQLite backup between two reconciliations of the same C# worker profile."""

import argparse
from dataclasses import dataclass
from hashlib import sha256 as byte_digest
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from evidence import write_json

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/RustCompatibilityOracle"))
from verify_activity import (TEST_CLASS, TEST_METHOD, UPLOAD_METHOD, equal, git, original_bytes, original_directory,
                             require, reviewed_schema, standalone_database, verify)
from verify_rollback import ASSEMBLIES, DELETION_METHOD, REPAIR_METHOD, verify as verify_rollback


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    stale_reason: str

    @property
    def stem(self):
        return "ifw-worker" if self.name == "download" else "ifw-worker-" + self.name

    @property
    def receipt_format(self):
        role = "activity" if self.name == "download" else self.name
        return "ifw-rust-worker-" + role + "-backup-v1"

    @property
    def roundtrip_format(self):
        role = "activity" if self.name == "download" else self.name
        return "ifw-worker-" + role + "-roundtrip-v1"


SCENARIOS = {
    case.name: case for case in (
        Scenario("download", TEST_METHOD, "no completed worker download"),
        Scenario("upload", UPLOAD_METHOD, "no completed worker upload"),
        Scenario("deletion", DELETION_METHOD, "no worker tombstone"),
        Scenario("repair", REPAIR_METHOD, "no pending worker timestamp repair"),
    )
}


def scenario(legacy_upload, kind):
    if kind is None:
        kind = "upload" if legacy_upload else "download"
    require(kind in SCENARIOS and (not legacy_upload or kind == "upload"), "invalid worker activity selection")
    return SCENARIOS[kind]


def load(path, limit=4096):
    return json.loads(original_bytes(path, limit))


def db_hash(path):
    return byte_digest(original_bytes(path, 16 << 20)).hexdigest()


def publish(directory, message):
    staged = directory / "ready.tmp"
    with staged.open("x", encoding="utf-8") as out:
        json.dump(message, out)
    staged.rename(directory / "ready.json")


def check_request(exchange, upload=False, *, kind=None):
    original_directory(exchange)
    request = load(exchange / "request.json")
    expected = scenario(upload, kind).stem + "-backup-request-v1"
    require(request["format"] == expected and re.fullmatch("[0-9a-f]{32}", request["token"]),
            "invalid C# exchange marker")
    for name in ("before", "after"):
        require(db_hash(exchange / (name + ".db")) == request[name + "Sha256"], f"wrong {name} donor")
    return request


def stale_control(data, request, exit_code, upload=False, *, kind=None):
    prefix = b"IFW_WORKER_STALE="
    markers = [json.loads(line[len(prefix):]) for line in data.splitlines() if line.startswith(prefix)]
    case = scenario(upload, kind)
    reason = f'Error: "{case.stale_reason}"'.encode("ascii")
    expected = case.stem + "-backup-stale-v1"
    require(type(exit_code) is int and exit_code != 0 and reason in data.splitlines() and
            markers == [{"format": expected, "token": request["token"],
                         "sourceSha256": request["beforeSha256"]}], "unrelated or missing Rust stale-backup refusal")


def run_backup(probe, directory, env, *, upload=False, kind=None):
    exchange = directory / "exchange"
    request = check_request(exchange, upload, kind=kind)
    returned = exchange / "returned.db"
    for name in ("before", "after"):
        stderr = directory / (name + "-stderr.log")
        stdout = directory / ("before-stdout.log" if name == "before" else "rust-backup.json")
        with stdout.open("xb") as out, stderr.open("xb") as err:
            result = subprocess.run([probe, exchange, name, request[name + "Sha256"]], cwd=ROOT, env=env,
                                    stdout=out, stderr=err, timeout=15)
        if name == "before":
            stale_control(original_bytes(stderr, 4096), request, result.returncode, upload, kind=kind)
            require(not returned.exists(), "Rust created an output for the stale backup")
            write_json(directory / "stale-exit.json", {"exitCode": result.returncode})
        else:
            result.check_returncode()
    rust = load(directory / "rust-backup.json", 16384)
    restored_hash = db_hash(returned)
    expected = scenario(upload, kind).receipt_format
    require((rust["format"], rust["token"], rust["sourceSha256"], rust["restoredSha256"]) ==
            (expected, request["token"], request["afterSha256"], restored_hash), "Rust returned unrelated backup bytes")
    publish(exchange, {"format": "ifw-rust-worker-backup-ready-v1", "token": request["token"],
                       "afterSha256": request["afterSha256"], "restoredSha256": restored_hash})


def replay(directory, target, revision, *, upload=False, kind=None):
    """Read the finalized C# and Rust artifacts without starting either executable."""
    case = scenario(upload, kind)
    platform = "windows" if "-windows-" in target else "linux"
    machine = target.split("-")[0]
    architecture = {"x86_64": "x64", "aarch64": "arm64"}[machine]
    exchange = directory / "exchange"
    original_directory(directory)
    original_directory(directory / "test-results")
    original_directory(exchange)
    require({p.name for p in exchange.iterdir()} == {"before.db", "after.db", "request.json", "returned.db", "ready.json"},
            "incomplete exchange or unexpected database companion")
    request = check_request(exchange, upload, kind=kind)
    restored_hash = db_hash(exchange / "returned.db")
    ready = load(exchange / "ready.json")
    require(ready == {"format": "ifw-rust-worker-backup-ready-v1", "token": request["token"],
                      "afterSha256": request["afterSha256"], "restoredSha256": restored_hash}, "unrelated reply")
    inputs = json.loads(git("show", f"{revision}:tools/rust-qa/storage/inputs.json"))
    require(target in inputs["target_graphs"], "unsupported native target")
    rust_bytes = original_bytes(directory / "rust-backup.json", 16384)
    rust = json.loads(rust_bytes)
    expected = scenario(upload, kind).receipt_format
    require((rust["format"], rust["token"], rust["sourceSha256"], rust["restoredSha256"],
             rust["sqliteSourceId"], rust["os"], rust["arch"]) ==
            (expected, request["token"], request["afterSha256"], restored_hash,
             inputs["sqlite"]["source_id"], platform, machine), "unexpected native Rust backup origin")
    require(rust["sqliteVersion"] == inputs["sqlite"]["version"] and
            "OMIT_LOAD_EXTENSION" in rust["compileOptions"] and "ENABLE_LOAD_EXTENSION" not in rust["compileOptions"],
            "wrong SQLite version or extension-loading options")
    stale_bytes = original_bytes(directory / "before-stderr.log", 4096)
    stale_control(stale_bytes, request, load(directory / "stale-exit.json")["exitCode"], upload, kind=kind)
    expected_rows = {"sync_entries": 1, "sync_account_status": 1, "owned_albums": 0,
                     "sync_timestamp_repairs": int(case.name == "repair")}
    equal(rust["tableRows"], expected_rows, "wrong Rust table observations")
    originals, trx = directory / "csharp", directory / "test-results/core-reference.trx"
    if case.name in ("deletion", "repair"):
        reference = verify_rollback(case.name, originals, trx, directory / "assemblies",
                                    platform, architecture, revision, rust_backup_hash=restored_hash)
    else:
        reference = verify(originals, trx, platform, architecture, revision,
                           rust_backup_hash=restored_hash, upload=case.name == "upload")
    latest = "pending.db" if case.name == "repair" else "after.db"
    require(reference["fileSha256"]["before.db"] == request["beforeSha256"] and
            reference["fileSha256"][latest] == request["afterSha256"], "C# worker donor substitution")
    schema = reviewed_schema(revision, platform)
    require(original_rows(exchange / "returned.db", schema, restored_hash) ==
            original_rows(exchange / "after.db", schema, request["afterSha256"]),
            "Rust output lost the original schema, mapping, journal or account history")
    require(db_hash(exchange / "returned.db") == restored_hash, "returned bytes changed during readback")
    return {"format": case.roundtrip_format,
            "target": target, "csharp": reference,
            "restoredSha256": restored_hash, "rustReceiptSha256": byte_digest(rust_bytes).hexdigest(),
            "staleControlSha256": byte_digest(stale_bytes).hexdigest()}


def original_rows(path, schema, digest):
    # The reviewed cases have at most one row per table, including the original journal string.
    with standalone_database(path, schema, digest) as db:
        return [db.execute("SELECT * FROM " + table).fetchall() for table in
                ("sync_entries", "sync_account_status", "owned_albums", "sync_timestamp_repairs")]


def execute(directory, probe, assembly, dotnet, env, case):
    directory.mkdir(mode=0o700)
    exchange = directory / "exchange"
    exchange.mkdir(mode=0o700)
    results = directory / "test-results"
    results.mkdir()
    if case.name in ("repair", "deletion"):
        archive = directory / "assemblies"
        archive.mkdir(mode=0o700)
        names = list(ASSEMBLIES.values())
        if case.name == "deletion":
            names.append("ImmichFolderWatch.Immich.dll")
        for name in names:
            shutil.copyfile(Path(assembly).with_name(name), archive / name)
    prefix = "IFW_QA_ACTIVITY_" if case.name == "download" else "IFW_QA_" + case.name.upper() + "_ACTIVITY_"
    test_env = dict(env, **{prefix + "EXCHANGE": str(exchange), prefix + "OUTPUT": str(directory / "csharp")})
    args = [dotnet, "vstest", assembly, "/Tests:" + TEST_CLASS + "." + case.method,
            "/Logger:trx;LogFileName=core-reference.trx", "/ResultsDirectory:" + str(results)]
    from worker_test_process import test_process
    with (directory / "worker.log").open("xb") as log, test_process(args, cwd=ROOT, env=test_env, log=log) as test:
        try:
            deadline = time.monotonic() + 90
            while not (exchange / "request.json").exists():
                require(test.poll() is None, "C# worker exited before publishing the donor backups")
                require(time.monotonic() < deadline, "timed out waiting for the shipping worker transfer")
                time.sleep(.05)
            run_backup(probe, directory, env, kind=case.name)
            code = test.wait(timeout=90)
        except BaseException as error:
            if test.poll() is None and not (exchange / "ready.json").exists():
                # Wake the worker on a failed trial so it can close its private profile.
                try:
                    publish(exchange, {"format": "ifw-worker-backup-failed-v1"})
                    test.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired) as cleanup:
                    error.add_note(f"Could not wake or drain the failed worker: {cleanup}")
            raise
    require(code == 0, "shipping worker did not confirm the restored backup; inspect worker.log")


def run(directory, probe, assembly, dotnet, env, target, revision, *, upload=False, kind=None):
    case = scenario(upload, kind)
    execute(directory, probe, assembly, dotnet, env, case)
    result = replay(directory, target, revision, kind=case.name)
    write_json(directory / "readback.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=replay.__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("target")
    parser.add_argument("revision")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--upload", action="store_true")
    selection.add_argument("--kind", choices=tuple(SCENARIOS))
    args = parser.parse_args()
    print(json.dumps(replay(args.directory, args.target, args.revision, upload=args.upload, kind=args.kind), indent=2))
