"""Install, repair and remove an original shipping package in its native test environment."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELEASE = json.loads((HERE / "release.json").read_bytes())
TABLES = ("owned_albums", "sync_account_status", "sync_entries", "sync_timestamp_repairs")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def digest(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def reparse(info):
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def evidence_hashes(directory):
    files = {}
    def visit(folder):
        for entry in sorted(folder.iterdir()):
            info = entry.lstat()
            check(not reparse(info) and not stat.S_ISLNK(info.st_mode), f"linked evidence entry: {entry.name}")
            if stat.S_ISDIR(info.st_mode):
                visit(entry)
            else:
                check(stat.S_ISREG(info.st_mode), f"unexpected evidence file type: {entry.name}")
                files[entry.relative_to(directory).as_posix()] = digest(entry)
    visit(directory)
    return files


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def native_target():
    os_name = {"Windows": "windows", "Linux": "linux"}[platform.system()]
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine().lower()]
    return f"{os_name}-{arch}"


def database_state(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        check(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "corrupt synthetic state")
        check(db.execute("PRAGMA user_version").fetchone() == (1,), "unexpected synthetic database version")
        tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        check(tables == set(TABLES), "unexpected synthetic tables")
        return {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in TABLES}


def prepare_seed(system, directory):
    fixtures = ROOT / "rust/tests/fixtures/legacy" / system
    sql = (fixtures / "sqlite/sensitive.sql").read_bytes()
    config = (fixtures / "config/defaults.written.yaml").read_bytes()
    directory.mkdir(mode=0o700)
    (directory / "config.yaml").write_bytes(config)
    database = directory / "sync-state.db"
    with closing(sqlite3.connect(database)) as db:
        db.executescript(sql.decode("utf-8"))
    rows = database_state(database)
    check(all(rows.values()), "the profile must exercise every shipping table")
    return {"configSha256": hashlib.sha256(config).hexdigest(), "sqlSha256": hashlib.sha256(sql).hexdigest(),
            "databaseSha256": digest(database), "rows": rows}


def prepare_package(target, directory, local_package):
    asset = RELEASE["assets"][target]
    package = directory / asset["name"]
    if local_package:
        info = local_package.lstat()
        check(stat.S_ISREG(info.st_mode) and not reparse(info) and info.st_size == asset["bytes"],
              "expected an original release package of the pinned size")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(local_package, flags), "rb") as source, package.open("xb") as copy:
            opened = os.fstat(source.fileno())
            check(stat.S_ISREG(opened.st_mode) and os.path.samestat(info, opened)
                  and opened.st_size == asset["bytes"], "release package changed before opening")
            remaining = asset["bytes"]
            while remaining:
                chunk = source.read(min(1_048_576, remaining))
                check(chunk, "release package ended before its pinned size")
                copy.write(chunk)
                remaining -= len(chunk)
            check(not source.read(1), "release package grew beyond its pinned size")
    else:
        url = f"https://github.com/{RELEASE['repository']}/releases/download/{RELEASE['tag']}/{asset['name']}"
        subprocess.run(["curl", "--disable", "--fail", "--silent", "--show-error", "--location",
                        "--proto", "=https", "--proto-redir", "=https", "--max-time", "180",
                        "--max-filesize", str(asset["bytes"]), "--output", str(package), url], check=True)
    check(package.stat().st_size == asset["bytes"] and digest(package) == asset["sha256"],
          "original release package size or SHA-256 mismatch")
    return package


def check_retained(output, seed_info, files):
    check(json.loads((output / "native/result.json").read_bytes())["status"] == "passed", "native package test failed")
    for filename, key in (("config.yaml", "configSha256"), ("sync-state.db", "databaseSha256")):
        check(files["native/retained/" + filename] == seed_info[key] == files["seed/" + filename],
              f"retained {filename} differs from the original synthetic profile")
    check(database_state(output / "native/retained/sync-state.db") == seed_info["rows"], "retained application state differs")


def run(target, output, local_package):
    check(native_target() == target, "test requires the matching native operating system and process architecture")
    revision = git("rev-parse", "HEAD").decode().strip()
    tag_commit = git("rev-parse", RELEASE["tag"] + "^{commit}").decode().strip()
    check(tag_commit == RELEASE["commit"], "release tag differs from the reviewed package source")
    dependencies = [".github/workflows/rust-legacy-install.yaml", "tools/rust-qa/performance/linux.py",
                    "tools/rust-qa/hosted-linux-namespace.sh", "tools/rust-qa/hosted-linux-namespace.apparmor",
                    "packaging/windows/Test-InstallerUpgradeContract.ps1"]
    source_changes = git("status", "--porcelain", "--", str(HERE), "rust/tests/fixtures/legacy", *dependencies).decode().splitlines()
    hosted = os.environ.get("GITHUB_ACTIONS") == "true"
    if hosted:
        check(os.environ.get("GITHUB_SHA") == revision and not source_changes, "hosted fixture source changed")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    native = output / "native"
    receipt = {"format": "ifw-shipping-install-v1", "target": target, "source": revision,
               "modifiedSources": source_changes, "release": RELEASE["commit"], "asset": RELEASE["assets"][target],
               "releaseTag": RELEASE["tag"], "releaseId": RELEASE["releaseId"], "nativeMachine": platform.machine(),
               "pythonVersion": platform.python_version(), "sqliteVersion": sqlite3.sqlite_version,
               "fixtureInputs": {str(p.relative_to(ROOT).as_posix()): digest(p) for p in
                                 [HERE / name for name in ("run.py", "release.json", "linux.py", "windows.ps1")] +
                                 [ROOT / name for name in dependencies]},
               "workflowRun": os.environ.get("GITHUB_RUN_ID"), "workflowAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
               "status": "failed"}
    hashes = {}
    try:
        seed = output / "seed"
        system = target.split("-")[0]
        receipt["seed"] = prepare_seed(system, seed)
        with tempfile.TemporaryDirectory(prefix="ifw-old-", dir=os.environ.get("RUNNER_TEMP") if hosted else None) as work:
            package = prepare_package(target, Path(work), local_package)
            try:
                if system == "windows":
                    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(HERE / "windows.ps1"),
                               "-Package", str(package), "-Seed", str(seed), "-Evidence", str(native)]
                    subprocess.run(command, cwd=ROOT, check=True)
                else:
                    from linux import run_native
                    run_native(package, native, receipt["seed"])
            finally:
                hashes = evidence_hashes(output)
        check_retained(output, receipt["seed"], hashes)
        receipt["status"] = "passed"
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        write_json(output / "result.json", receipt)
        hashes["result.json"] = digest(output / "result.json")
        write_json(output / "evidence-hashes.json", hashes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=RELEASE["assets"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--package", type=Path, help="Use a local copy of the original hash-pinned release asset")
    args = parser.parse_args()
    run(args.target, args.output.absolute(), args.package)
