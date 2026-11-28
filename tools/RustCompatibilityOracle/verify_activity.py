"""Read a shipping worker's archived transfer, standalone backups and xUnit result."""

import argparse
from contextlib import closing, contextmanager
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import stat
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
BASE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
TEST_PROJECT = "src/ImmichFolderWatch.Tests.Core"
TEST_FILE = TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests.ActivityBackup.cs"
TEST_CLASS = "ImmichFolderWatch.Tests.Core.Services.FolderWatchWorkerPersistenceTests"
TEST_METHOD = "Download_RetainsBeforeAndAfterBackupsAndRestartsFromLatest"
UPLOAD_METHOD = "Upload_PeerRetainsReceivedBytesWhenWorkerRestartsFromLatestBackup"
UPLOAD_FILE = TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests.UploadActivity.cs"
REPAIR_FILE = TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests.RepairBackup.cs"
DELETION_FILE = TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests.DeletionBackup.cs"
LEGACY_INPUTS = (
    "src/ImmichFolderWatch.Core", "src/ImmichFolderWatch.Immich", "src/ImmichFolderWatch.App.Shared",
    "src/ImmichFolderWatch.App.Linux/Platform", TEST_PROJECT + "/ImmichFolderWatch.Tests.Core.csproj",
    TEST_PROJECT + "/Services/FolderWatchWorkerPersistenceTests*.cs", ":!" + TEST_FILE,
    ":!" + UPLOAD_FILE, ":!" + REPAIR_FILE, ":!" + DELETION_FILE,
    "Directory.Build.props", "Directory.Build.targets", "global.json", "NuGet.Config",
)
UPLOAD_BYTES = bytes.fromhex("ff d8 00 01 7f 80 ff d9")
UPLOAD_TIMESTAMP = "2011-08-06T04:02:00.0000000+00:00"
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


def original_directory(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            f"expected an original directory: {path.name}")


def original_bytes(path, limit):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and 0 < before.st_size <= limit, f"expected a bounded regular file: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_size == before.st_size, f"changed input: {path.name}")
        data = stream.read(limit + 1)
    require(len(data) == before.st_size, f"input length changed while reading: {path.name}")
    return data


def artifact_hashes(root, upload=False):
    original_directory(root)
    limits = {"before.db": 16 << 20, "after.db": 16 << 20, "activity.json": 65536}
    limits.update({"capture.jpg": 8, "peer.jpg": 8} if upload else {"photo.jpg": 6})
    require({p.name for p in root.iterdir()} == limits.keys(), "incomplete or unexpected original activity files")
    return {name: sha256(original_bytes(root / name, limits[name])).hexdigest() for name in sorted(limits)}


def passed_activity(trx_bytes, method_name, manifest_hash):
    run = ElementTree.fromstring(trx_bytes)
    name = TEST_CLASS + "." + method_name
    definition, = (e for e in run.findall("./{*}TestDefinitions/{*}UnitTest") if e.get("name") == name)
    method = definition.find("{*}TestMethod")
    require((method.get("className"), method.get("name")) == (TEST_CLASS, method_name), "incorrect TRX method")
    execution_id = definition.find("{*}Execution").attrib["id"]
    result, = (e for e in run.findall("./{*}Results/{*}UnitTestResult") if e.get("testId") == definition.attrib["id"])
    require((result.get("testName"), result.get("outcome"), result.get("executionId")) == (name, "Passed", execution_id),
            "activity test did not pass in this TRX execution")
    stdout = result.findtext("./{*}Output/{*}StdOut", "")
    markers = [line.strip() for line in stdout.splitlines() if line.strip().startswith("IFW_ACTIVITY_SHA256=")]
    equal(markers, ["IFW_ACTIVITY_SHA256=" + manifest_hash], "test result does not identify the original activity file")
    return execution_id, stdout


def verify_trx(trx, manifest_hash, rust_backup_hash=None, *, upload=False):
    execution_id, stdout = passed_activity(original_bytes(trx, 32 << 20), UPLOAD_METHOD if upload else TEST_METHOD,
                                           manifest_hash)
    consumed = [line.strip() for line in stdout.splitlines() if line.strip().startswith("IFW_RUST_BACKUP_SHA256=")]
    equal(consumed, ["IFW_RUST_BACKUP_SHA256=" + rust_backup_hash] if rust_backup_hash else [],
          "test result does not identify the expected restore path and bytes")
    if upload:
        digest = sha256(UPLOAD_BYTES).hexdigest()
        markers = [line.strip() for line in stdout.splitlines() if line.strip().startswith("IFW_UPLOAD_PEER_")]
        equal(sorted(markers), ["IFW_UPLOAD_PEER_ASSET=asset-" + digest, "IFW_UPLOAD_PEER_SHA256=" + digest],
              "test result does not identify the original receiving peer bytes and asset")
    return execution_id


def schema(db):
    return [(kind, name, owner, " ".join(sql.split()) if sql else None) for kind, name, owner, sql in
            db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name")]


def reviewed_schema(revision, platform):
    with closing(sqlite3.connect(":memory:")) as golden:
        golden.executescript(git("show", f"{revision}:rust/tests/fixtures/legacy/{platform}/sqlite/sensitive.sql").decode())
        return schema(golden)


@contextmanager
def standalone_database(path, expected_schema, expected_digest):
    data = original_bytes(path, 16 << 20)
    require(sha256(data).hexdigest() == expected_digest and data.startswith(b"SQLite format 3\0") and data[18:20] == b"\1\1",
            f"expected the identified, standalone rollback-mode database: {path.name}")
    # SQLite must query the same bytes we hashed, including on builds without sqlite3_deserialize.
    with TemporaryDirectory(prefix="ifw-worker-backup-read-") as scratch:
        verified = Path(scratch) / "verified.db"
        verified.write_bytes(data)
        with closing(sqlite3.connect(verified.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], f"damaged {path.name}")
            require(db.execute("PRAGMA user_version").fetchone() == (1,), f"unexpected schema version in {path.name}")
            require(schema(db) == expected_schema, f"schema differs from the reviewed legacy corpus in {path.name}")
            yield db


def read_backup(path, expected_schema, expected_digest):
    with standalone_database(path, expected_schema, expected_digest) as db:
        for table in ("owned_albums", "sync_timestamp_repairs"):
            require(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,), f"unexpected {table} row")
        entries = [dict(zip(MAPPING_FIELDS, row, strict=True)) for row in db.execute("SELECT * FROM sync_entries")]
        return entries, db.execute("SELECT account_scope, last_successful_sync_utc FROM sync_account_status").fetchall()


def check_transfer(observed, downloads):
    equal([observed["downloads"], observed["uploads"]], [downloads, 0], "incorrect transfer counters")
    require(type(observed["albumLists"]) is int and observed["albumLists"] > 0, "missing successful album observation")


def utc_timestamp(stamp):
    require(isinstance(stamp, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}\+00:00", stamp),
            "invalid UTC timestamp encoding")
    datetime.fromisoformat(stamp)


def watch_root_key(source, windows, revision):
    native_path = PureWindowsPath(source) if windows else PurePosixPath(source)
    require(native_path.is_absolute() and native_path.name == "watch" and
            re.fullmatch("immich-folder-watch-worker-tests-[a-f0-9]{32}", native_path.parent.name), "wrong synthetic watch root")
    if not windows:
        return source
    # A native Windows temporary directory can include non-ASCII characters.
    table = git("show", revision + ":tools/rust-qa/legacy/casing/unicode-15.1.0.tsv").decode().splitlines()
    return source.translate({int(a, 16): int(b, 16) for a, b in (line.split() for line in table[1:])})


def verify(root, trx, platform, arch, revision, *, rust_backup_hash=None, upload=False):
    require(re.fullmatch(r"[0-9a-f]{40}", revision), "supply the full Git revision that executed the test")
    git("diff", "--exit-code", "--quiet", BASE, revision, "--", *LEGACY_INPUTS)
    test_blob = git("rev-parse", "--verify", revision + ":" + (UPLOAD_FILE if upload else TEST_FILE)).decode().strip()
    hashes = artifact_hashes(root, upload)
    execution_id = verify_trx(trx, hashes["activity.json"], rust_backup_hash, upload=upload)
    case = json.loads(original_bytes(root / "activity.json", 65536))
    equal([case["format"], case["caseId"], case["platform"], case["osArchitecture"], case["processArchitecture"]],
          ["ifw-csharp-worker-upload-activity-v1" if upload else "ifw-csharp-worker-download-activity-v1",
           "restored-latest-upload" if upload else "restored-latest-download", platform, arch, arch], "wrong case or native target")
    equal([case["testAssemblyVersion"], case["workerAssemblyVersion"]], ["3.0.4+" + revision] * 2,
          "running test and shipping worker assemblies must identify the recorded source revision")
    require(bool(case["osDescription"].strip()), "missing OS description")
    require(case["accountScope"] == ACCOUNT, "incorrect account identity")
    windows = platform == "windows"
    source_key = watch_root_key(case["sourcePath"], windows, revision)

    expected_schema = reviewed_schema(revision, platform)
    equal(read_backup(root / "before.db", expected_schema, hashes["before.db"]), [[], []], "before backup already contains activity")
    require(hashes["after.db"] != hashes["before.db"], "identical before and after backups")
    after = case["after"]
    require(after["databaseSha256"] == hashes["after.db"], "after backup hash differs")
    entries, accounts = read_backup(root / "after.db", expected_schema, hashes["after.db"])
    entry, = entries
    (account, history), = accounts
    synchronized = entry["lastSynchronizedAtUtc"]
    utc_timestamp(synchronized)
    utc_timestamp(history)
    require(account == ACCOUNT and synchronized <= history, "wrong account or transfer history order")
    if upload:
        check_upload(root, hashes, case, entry, history, windows, source_key)
    else:
        check_download(root, hashes, case, entry, history, windows, source_key)
    equal(artifact_hashes(root, upload), hashes, "originals changed during readback")
    return {"revision": revision, "reference": BASE, "activityTestBlob": test_blob, "platform": platform,
            "architecture": arch, "testExecutionId": execution_id, "trxSha256": sha256(original_bytes(trx, 32 << 20)).hexdigest(),
            "fileSha256": hashes, "lastSynchronizedAtUtc": synchronized, "lastSuccessfulSyncUtc": history}


def check_download(root, hashes, case, entry, history, windows, source_key):
    equal(case["before"], {"databaseSha256": hashes["before.db"], "mappingCount": 0, "accountStatusCount": 0,
                           "fileExisted": False}, "incorrect before state")
    written = MODIFIED if windows else CREATED
    expected = [ACCOUNT, case["sourcePath"], source_key, "photo.jpg", "PHOTO.JPG" if windows else "photo.jpg",
                "remote", "Camera", 6, written, 1, 0, entry["lastSynchronizedAtUtc"], None]
    equal(entry, dict(zip(MAPPING_FIELDS, expected, strict=True)), "unexpected stored mapping")
    require(original_bytes(root / "photo.jpg", 6) == b"remote", "downloaded media bytes differ")
    file_state = {"name": "photo.jpg", "size": 6, "sha256": hashes["photo.jpg"],
                  "lastWriteTimeUtc": written, "creationTimeUtc": CREATED if windows else None}
    restart = case["restart"]
    for state, downloads in ((case["after"], 1), (restart, 0)):
        equal([state["mapping"], state["lastSuccessfulSyncUtc"], state["file"]], [entry, history, file_state],
              "mapping, account history or original native file observations differ")
        check_transfer(state, downloads)
    equal(case["staleRead"], {"mappingCount": 0, "accountStatusCount": 0, "file": file_state}, "wrong stale backup control")
    equal([restart["totalDownloads"], restart["totalUploads"]], [1, 0], "incorrect cumulative transfer counts")


def check_upload(root, hashes, case, entry, history, windows, source_key):
    digest = sha256(UPLOAD_BYTES).hexdigest()
    asset = "asset-" + digest
    expected = [ACCOUNT, case["sourcePath"], source_key, "capture.jpg", "CAPTURE.JPG" if windows else "capture.jpg",
                asset, "Camera", len(UPLOAD_BYTES), UPLOAD_TIMESTAMP, 0, 0, entry["lastSynchronizedAtUtc"], None]
    equal(entry, dict(zip(MAPPING_FIELDS, expected, strict=True)), "unexpected stored upload mapping")
    before, after, restart = case["before"], case["after"], case["restart"]
    for name, observed in (("capture.jpg", before["local"]), ("peer.jpg", after["peer"])):
        require(original_bytes(root / name, len(UPLOAD_BYTES)) == UPLOAD_BYTES, "local or receiving peer bytes differ")
        equal([observed["name"], observed["size"], observed["sha256"], hashes[name]],
              ["capture.jpg", len(UPLOAD_BYTES), digest, digest], "incorrect retained file or receiving peer")
        utc_timestamp(observed["lastWriteTimeUtc"])
        if windows:
            utc_timestamp(observed["creationTimeUtc"])
        else:
            equal(observed["creationTimeUtc"], None, "unexpected creation timestamp on Linux")
    local, peer = before["local"], after["peer"]
    equal([before["databaseSha256"], before["peerExisted"], local["lastWriteTimeUtc"]],
          [hashes["before.db"], False, UPLOAD_TIMESTAMP], "incorrect pre-upload state")
    equal(case["staleRead"], {"mappingCount": 0, "accountStatusCount": 0, "local": local, "peer": peer},
          "reading the older database changed the retained files")
    listed_asset = {"id": asset, "originalFileName": "capture.jpg", "fileModifiedAt": None, "fileCreatedAt": None}
    for state, uploads in ((after, 1), (restart, 0)):
        equal([state["mapping"], state["lastSuccessfulSyncUtc"], state["local"], state["peer"]], [entry, history, local, peer],
              "restarted mapping, account history or external file observations differ")
        check_peer_requests(state, uploads, listed_asset)


def check_peer_requests(state, uploads, listed_asset):
    equal([state["uploads"], state["downloads"], state["rejectedRequests"]],
          [uploads, 0, []], "unexpected transfer or refused peer operation")
    listings = state["listings"]
    require(isinstance(listings, list) and listings and all(item is None or item == listed_asset for item in listings),
            "missing or unrelated Camera album listings")
    require((None in listings) == bool(uploads), "wrong peer visibility before upload or after restart")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("trx", type=Path)
    parser.add_argument("platform", choices=("linux", "windows"))
    parser.add_argument("arch", choices=("x64", "arm64"))
    parser.add_argument("revision")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.trx, args.platform, args.arch, args.revision, upload=args.upload), indent=2))
