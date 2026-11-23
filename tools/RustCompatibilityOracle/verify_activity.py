"""Read the archived C# worker download, its two standalone backups and its test result."""

import argparse
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import subprocess
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
BASE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
TEST_PROJECT = "src/ImmichFolderWatch.Tests.Core"
TEST_FILE = TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests.ActivityBackup.cs"
TEST_CLASS = "ImmichFolderWatch.Tests.Core.Services.FolderWatchWorkerPersistenceTests"
TEST_METHOD = "Download_RetainsBeforeAndAfterBackupsAndRestartsFromLatest"
LEGACY_INPUTS = (
    "src/ImmichFolderWatch.Core", "src/ImmichFolderWatch.Immich", "src/ImmichFolderWatch.App.Shared",
    "src/ImmichFolderWatch.App.Linux/Platform", TEST_PROJECT + "/ImmichFolderWatch.Tests.Core.csproj",
    TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests*.cs", ":!" + TEST_FILE,
    "Directory.Build.props", "Directory.Build.targets", "global.json", "NuGet.Config",
)
FILES = {"before.db", "after.db", "activity.json", "photo.jpg"}
ACCOUNT = sha256(b"https://immich.example/api\ntest-key").hexdigest()
CREATED = "2004-02-04T06:08:10.0000000+00:00"
MODIFIED = "2004-02-06T06:08:10.0000000+00:00"
MAPPING_FIELDS = (
    "accountScope", "sourcePath", "sourceKey", "relativePath", "relativePathKey", "assetId",
    "albumName", "fileSize", "lastWriteTimeUtc", "direction", "status", "lastSynchronizedAtUtc",
    "tombstoneExpiresAtUtc",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def equal(actual, expected, label):
    # JSON also distinguishes boolean values from SQLite integers.
    require(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), label)


def artifact_hashes(root):
    require({p.name for p in root.iterdir()} == FILES, "activity directory must contain exactly four original files")
    require(all((root / name).is_file() and not (root / name).is_symlink() for name in FILES), "regular files required")
    return {name: sha256((root / name).read_bytes()).hexdigest() for name in sorted(FILES)}


def verify_trx(trx, manifest_hash):
    run = ElementTree.parse(trx)
    name = TEST_CLASS + "." + TEST_METHOD
    definition, = (e for e in run.findall("./{*}TestDefinitions/{*}UnitTest") if e.get("name") == name)
    method = definition.find("{*}TestMethod")
    require((method.get("className"), method.get("name")) == (TEST_CLASS, TEST_METHOD), "incorrect TRX method")
    execution_id = definition.find("{*}Execution").attrib["id"]
    result, = (e for e in run.findall("./{*}Results/{*}UnitTestResult") if e.get("testId") == definition.attrib["id"])
    require((result.get("testName"), result.get("outcome"), result.get("executionId")) == (name, "Passed", execution_id),
            "activity test did not pass in this TRX execution")
    stdout = result.findtext("./{*}Output/{*}StdOut", "")
    markers = [line.strip() for line in stdout.splitlines() if line.strip().startswith("IFW_ACTIVITY_SHA256=")]
    equal(markers, ["IFW_ACTIVITY_SHA256=" + manifest_hash], "test result does not identify the original activity file")
    return execution_id


def schema(db):
    return [(kind, name, owner, " ".join(sql.split()) if sql else None) for kind, name, owner, sql in
            db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name")]


def read_backup(path, expected_schema):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], f"damaged {path.name}")
        require(db.execute("PRAGMA user_version").fetchone() == (1,), f"unexpected schema version in {path.name}")
        require(schema(db) == expected_schema, f"schema differs from the reviewed legacy corpus in {path.name}")
        for table in ("owned_albums", "sync_timestamp_repairs"):
            require(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,), f"unexpected {table} row")
        entries = [dict(zip(MAPPING_FIELDS, row, strict=True)) for row in db.execute("SELECT * FROM sync_entries")]
        return entries, db.execute("SELECT account_scope, last_successful_sync_utc FROM sync_account_status").fetchall()


def check_transfer(observed, downloads):
    equal([observed["downloads"], observed["uploads"]], [downloads, 0], "incorrect transfer counters")
    require(type(observed["albumLists"]) is int and observed["albumLists"] > 0, "missing successful album observation")


def verify(root, trx, platform, arch, revision):
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "supply the full Git revision that executed the test")
    git("diff", "--exit-code", "--quiet", BASE, revision, "--", *LEGACY_INPUTS)
    test_blob = git("rev-parse", "--verify", revision + ":" + TEST_FILE).decode().strip()
    hashes = artifact_hashes(root)
    execution_id = verify_trx(trx, hashes["activity.json"])
    case = json.loads((root / "activity.json").read_bytes())
    equal([case["format"], case["caseId"], case["platform"], case["osArchitecture"], case["processArchitecture"]],
          ["ifw-csharp-worker-download-activity-v1", "restored-latest-download", platform, arch, arch], "wrong case or native target")
    equal([case["testAssemblyVersion"], case["workerAssemblyVersion"]], ["3.0.4+" + revision] * 2,
          "running test and shipping worker assemblies must identify the recorded source revision")
    require(bool(case["osDescription"].strip()), "missing OS description")
    require(case["accountScope"] == ACCOUNT, "incorrect account identity")
    windows = platform == "windows"
    source = case["sourcePath"]
    native_path = PureWindowsPath(source) if windows else PurePosixPath(source)
    require(native_path.is_absolute() and native_path.name == "watch" and
            re.fullmatch("immich-folder-watch-worker-tests-[a-f0-9]{32}", native_path.parent.name), "wrong synthetic watch root")
    source_key = source
    if windows:
        # Use the qualified Windows scalar map, including non-ASCII characters in a native temp path.
        table = git("show", revision + ":tools/rust-qa/legacy/casing/unicode-15.1.0.tsv").decode().splitlines()
        source_key = source.translate({int(a, 16): int(b, 16) for a, b in (line.split() for line in table[1:])})

    with closing(sqlite3.connect(":memory:")) as golden:
        golden.executescript(git("show", f"{revision}:rust/tests/fixtures/legacy/{platform}/sqlite/sensitive.sql").decode())
        expected_schema = schema(golden)
    equal(read_backup(root / "before.db", expected_schema), [[], []], "before backup already contains activity")
    equal(case["before"], {"databaseSha256": hashes["before.db"], "mappingCount": 0, "accountStatusCount": 0,
                           "fileExisted": False}, "incorrect before state")
    require(hashes["after.db"] != hashes["before.db"], "identical before and after backups")
    after = case["after"]
    require(after["databaseSha256"] == hashes["after.db"], "after backup hash differs")
    entries, accounts = read_backup(root / "after.db", expected_schema)
    entry, = entries
    (account, history), = accounts
    synchronized = entry["lastSynchronizedAtUtc"]
    for stamp in (synchronized, history):
        require(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}\+00:00", stamp), "invalid UTC timestamp encoding")
        datetime.fromisoformat(stamp)
    require(account == ACCOUNT and synchronized <= history, "wrong account or transfer history order")
    written = MODIFIED if windows else CREATED
    expected = [ACCOUNT, source, source_key, "photo.jpg", "PHOTO.JPG" if windows else "photo.jpg",
                "remote", "Camera", 6, written, 1, 0, synchronized, None]
    equal(entry, dict(zip(MAPPING_FIELDS, expected, strict=True)), "unexpected stored mapping")
    require((root / "photo.jpg").read_bytes() == b"remote", "downloaded media bytes differ")
    file_state = {"name": "photo.jpg", "size": 6, "sha256": hashes["photo.jpg"],
                  "lastWriteTimeUtc": written, "creationTimeUtc": CREATED if windows else None}
    restart = case["restart"]
    for state, downloads in ((after, 1), (restart, 0)):
        equal([state["mapping"], state["lastSuccessfulSyncUtc"], state["file"]], [entry, history, file_state],
              "mapping, account history or original native file observations differ")
        check_transfer(state, downloads)
    equal(case["staleRead"], {"mappingCount": 0, "accountStatusCount": 0, "file": file_state}, "wrong stale backup control")
    equal([restart["totalDownloads"], restart["totalUploads"]], [1, 0], "incorrect cumulative transfer counts")
    equal(artifact_hashes(root), hashes, "originals changed during readback")
    return {"revision": revision, "reference": BASE, "activityTestBlob": test_blob, "platform": platform,
            "architecture": arch, "testExecutionId": execution_id, "trxSha256": sha256(trx.read_bytes()).hexdigest(),
            "fileSha256": hashes, "lastSynchronizedAtUtc": synchronized, "lastSuccessfulSyncUtc": history}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("trx", type=Path)
    parser.add_argument("platform", choices=("linux", "windows"))
    parser.add_argument("arch", choices=("x64", "arm64"))
    parser.add_argument("revision")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.trx, args.platform, args.arch, args.revision), indent=2))
