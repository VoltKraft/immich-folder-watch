"""Read shipping worker rollback fixtures from their original databases, media, assemblies and xUnit result."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from verify_activity import (
    ACCOUNT, BASE, CREATED, DELETION_FILE, LEGACY_INPUTS, MAPPING_FIELDS, MODIFIED, REPAIR_FILE,
    check_transfer, equal, git, original_bytes, original_directory, passed_activity, read_backup, require,
    reviewed_schema, standalone_database, utc_timestamp, watch_root_key,
)

REPAIR_METHOD = "TimestampRepair_RestartsFromPendingBackupAfterFilesystemChange"
DELETION_METHOD = "Sync_PreservesPeerTrashAndTombstoneWhenRestoringDeletionBackup"
TRASH_BYTES = bytes.fromhex("ff d8 00 23 7f 80 fe ff d9")
TRANSFER_TIME = "2014-02-04T06:08:10.0000000+00:00"
ACCOUNT_TIME = "2014-02-05T06:08:10.0000000+00:00"
ASSEMBLIES = {"test": "ImmichFolderWatch.Tests.Core.dll", "worker": "ImmichFolderWatch.Core.dll"}


def journal_stamp(timestamp):
    """System.Text.Json trims trailing fractional zeros, while the SQLite columns use seven places."""
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,7}))?\+00:00", timestamp)
    require(match is not None, "unexpected journal timestamp encoding")
    result = f"{match[1]}.{(match[2] or '').ljust(7, '0')}+00:00"
    utc_timestamp(result)
    return result


def check_journal(db, receipt, entry, desired_write, digest):
    require(db.execute("SELECT COUNT(*) FROM owned_albums").fetchone() == (0,), "unexpected owned album")
    entries = [dict(zip(MAPPING_FIELDS, row, strict=True)) for row in db.execute("SELECT * FROM sync_entries")]
    equal(entries, [entry], "pending backup changed the original mapping")
    equal(db.execute("SELECT * FROM sync_account_status").fetchall(), [[ACCOUNT, ACCOUNT_TIME]],
          "pending repair changed the account history")
    (key, source_key, relative_key, payload), = db.execute(
        "SELECT account_scope, source_key, relative_path_key, repair_json FROM sync_timestamp_repairs")
    equal([key, source_key, relative_key], [ACCOUNT, entry["sourceKey"], entry["relativePathKey"]], "wrong repair owner")
    journal = json.loads(payload)
    require(set(journal) == {"OriginalEntry", "CreationTimeUtc", "LastWriteTimeUtc", "ContentSha256"},
            "unexpected repair journal fields")
    original = {name[0].lower() + name[1:]: value for name, value in journal["OriginalEntry"].items()}
    expected = {k: v for k, v in entry.items() if k not in ("sourceKey", "relativePathKey")}
    equal({**original, "lastWriteTimeUtc": journal_stamp(original["lastWriteTimeUtc"]),
           "lastSynchronizedAtUtc": journal_stamp(original["lastSynchronizedAtUtc"])}, expected,
          "journal does not describe the original mapping")
    equal([journal_stamp(journal["CreationTimeUtc"]), journal_stamp(journal["LastWriteTimeUtc"]), journal["ContentSha256"]],
          [CREATED, desired_write, digest.upper()], "wrong requested repair dates or content digest")
    equal(receipt, {"originalEntry": original, "creationTimeUtc": journal["CreationTimeUtc"],
                    "lastWriteTimeUtc": journal["LastWriteTimeUtc"], "contentSha256": journal["ContentSha256"]},
          "persisted intent differs from the worker's journal observation")


def check_repair(directory, case, files, schema, windows, revision):
    before, paused, restart = case["before"], case["interrupted"], case["restart"]
    for name, state in (("before.db", before), ("pending.db", paused), ("completed.db", restart)):
        equal(files[name], state["databaseSha256"], f"wrong original {name}")
    require(len({files["before.db"], files["pending.db"], files["completed.db"]}) == 3, "duplicated repair database")
    entries, history = read_backup(directory / "before.db", schema, files["before.db"])
    entry, = entries
    desired_write = MODIFIED if windows else CREATED
    source = entry["sourcePath"]
    expected = [ACCOUNT, source, watch_root_key(source, windows, revision), "photo.jpg", "PHOTO.JPG" if windows else "photo.jpg",
                "remote", "Camera", 6, entry["lastWriteTimeUtc"], 1, 0, TRANSFER_TIME, None]
    equal(entry, dict(zip(MAPPING_FIELDS, expected, strict=True)), "unexpected pre-repair mapping")
    equal(history, [[ACCOUNT, ACCOUNT_TIME]], "unexpected pre-repair Last Sync")
    utc_timestamp(entry["lastWriteTimeUtc"])
    require(entry["lastWriteTimeUtc"] != desired_write, "no original timestamp to repair")
    equal([before["mapping"], before["lastSuccessfulSyncUtc"]], [entry, ACCOUNT_TIME], "wrong pre-repair receipt")
    media = original_bytes(directory / "photo.jpg", 6)
    require(media == b"remote", "wrong original photo")
    digest = sha256(media).hexdigest()
    equal(digest, files["photo.jpg"], "wrong archived repair photo digest")
    with standalone_database(directory / "pending.db", schema, files["pending.db"]) as db:
        check_journal(db, paused["pending"], entry, desired_write, digest)
    final_entry = {**entry, "lastWriteTimeUtc": desired_write}
    equal(read_backup(directory / "completed.db", schema, files["completed.db"]), [[final_entry], history],
          "completed backup did not finalize only the intended timestamp")
    equal([restart["mapping"], restart["lastSuccessfulSyncUtc"]], [final_entry, ACCOUNT_TIME], "wrong restart receipt")
    original_file = {"name": "photo.jpg", "size": len(media), "sha256": digest, "lastWriteTimeUtc": entry["lastWriteTimeUtc"],
                     "creationTimeUtc": before["file"]["creationTimeUtc"] if windows else None}
    if windows:
        utc_timestamp(original_file["creationTimeUtc"])
    equal(before["file"], original_file, "incorrect original file")
    repaired_file = {**original_file, "lastWriteTimeUtc": desired_write, "creationTimeUtc": CREATED if windows else None}
    for state in (paused, case["staleRestore"], restart):
        equal(state["file"], repaired_file, "the external photo or its native timestamp changed across restore")
    require("Timestamp correction" in paused["lastSyncErrorMessage"], "missing interruption before repair completion")
    for state in (paused, restart):
        check_transfer(state, 0)
    return {"repairRows": [0, 1, 0], "retainedPhotoSha256": digest,
            "repairedLastWriteTimeUtc": desired_write, "lastSuccessfulSyncUtc": ACCOUNT_TIME}


def check_requests(requests, asset, *, restart):
    """Read the shipping HTTP client's complete ledger from the synthetic peer."""
    album = {"method": "GET", "path": "/api/albums", "body": None, "listedAsset": None}
    search = {"method": "POST", "path": "/api/search/metadata",
              "body": {"albumIds": ["album-camera"], "page": 1, "size": 250}, "listedAsset": None}
    positive = {**search, "listedAsset": asset}
    download = {"method": "GET", "path": f"/api/assets/{asset}/original", "body": None, "listedAsset": None}
    trash = {"method": "DELETE", "path": "/api/assets", "body": {"ids": [asset], "force": False}, "listedAsset": None}
    require(album in requests, "no album lookup")
    if restart:
        require(search in requests and requests.index(album) < requests.index(search), "no empty album reconciliation on restart")
        allowed = (album, search)
    else:
        require(positive in requests and requests.count(download) == 1 and requests.count(trash) == 1,
                "expected exactly one original download and one non-forced trash request")
        require(requests.index(album) < requests.index(positive) < requests.index(download) < requests.index(trash),
                "incorrect download and deletion order")
        allowed = (album, search, positive, download, trash)
    # JSON distinguishes false from zero and verifies every request body and asset ID.
    for request in requests:
        require(any(json.dumps(request, sort_keys=True) == json.dumps(item, sort_keys=True) for item in allowed),
                "unexpected HTTP request")


def check_deletion(directory, case, files, schema, windows, revision):
    before, after = case["before"], case["after"]
    equal([case["caseId"], case["accountScope"]], ["restored-latest-local-deletion", ACCOUNT], "wrong deletion case")
    require(original_bytes(directory / "peer-trash.jpg", len(TRASH_BYTES)) == TRASH_BYTES, "wrong original peer trash bytes")
    digest = sha256(TRASH_BYTES).hexdigest()
    equal(digest, files["peer-trash.jpg"], "wrong archived trash digest")
    asset = "asset-" + digest
    equal(case["assetId"], asset, "wrong synthetic asset identity")
    require(files["before.db"] != files["after.db"], "same database before and after trash")
    equal([files["before.db"], files["after.db"]], [before["databaseSha256"], after["databaseSha256"]], "wrong donor")
    (entries, accounts) = read_backup(directory / "before.db", schema, files["before.db"])
    entry, = entries
    (account, history), = accounts
    equal(account, ACCOUNT, "wrong account history")
    source = case["sourcePath"]
    expected = [ACCOUNT, source, watch_root_key(source, windows, revision), "photo.jpg", "PHOTO.JPG" if windows else "photo.jpg",
                asset, "Camera", len(TRASH_BYTES), CREATED, 1, 0, entry["lastSynchronizedAtUtc"], None]
    equal(entry, dict(zip(MAPPING_FIELDS, expected, strict=True)), "wrong original download mapping")
    rows, after_accounts = read_backup(directory / "after.db", schema, files["after.db"])
    tombstone, = rows
    deleted_at = tombstone["lastSynchronizedAtUtc"]
    expires = tombstone["tombstoneExpiresAtUtc"]
    for stamp in (entry["lastSynchronizedAtUtc"], history, deleted_at, expires):
        utc_timestamp(stamp)
    require(entry["lastSynchronizedAtUtc"] <= history <= deleted_at < expires, "wrong deletion history order")
    equal(tombstone, {**entry, "status": 1, "lastSynchronizedAtUtc": deleted_at, "tombstoneExpiresAtUtc": expires},
          "incorrect tombstone delta")
    equal(after_accounts, accounts, "deletion changed account Last Sync")
    for phase, row in (("before", entry), ("staleRead", entry), ("after", tombstone), ("restart", tombstone)):
        equal([case[phase]["mapping"], case[phase]["lastSuccessfulSyncUtc"]], [row, history],
              "observed state differs from original SQLite donors")
    file = {"name": "photo.jpg", "size": len(TRASH_BYTES), "sha256": digest, "lastWriteTimeUtc": CREATED,
            "creationTimeUtc": CREATED if windows else None}
    equal([before["local"], before["peer"]], [file, file], "incorrect original local or peer file")
    for phase in ("after", "staleRead", "restart"):
        equal(case[phase]["external"], {"localFiles": [], "albumFiles": [], "trashFile": file},
              "stale or latest restore changed the external deletion")
    check_requests(after["requests"], asset, restart=False)
    check_requests(case["restart"]["requests"], asset, restart=True)
    return {"assetId": asset, "trashSha256": digest, "tombstoneExpiresAtUtc": expires,
            "lastSuccessfulSyncUtc": history, "trashRequests": [1, 0]}


def verify(kind, directory, trx, assemblies, platform, arch, revision, *, rust_backup_hash=None):
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "supply the executing commit")
    git("diff", "--exit-code", "--quiet", BASE, revision, "--", *LEGACY_INPUTS)
    original_directory(directory)
    original_directory(assemblies)
    limits = {"before.db": 16 << 20, "activity.json": 65536}
    inputs = ASSEMBLIES.copy()
    if kind == "repair":
        limits.update({"pending.db": 16 << 20, "completed.db": 16 << 20, "photo.jpg": 6})
        method, source, read_state = REPAIR_METHOD, REPAIR_FILE, check_repair
    elif kind == "deletion":
        limits.update({"after.db": 16 << 20, "peer-trash.jpg": len(TRASH_BYTES)})
        inputs["client"] = "ImmichFolderWatch.Immich.dll"
        method, source, read_state = DELETION_METHOD, DELETION_FILE, check_deletion
    else:
        raise ValueError("unknown worker activity")
    require({p.name for p in directory.iterdir()} == limits.keys(), f"unexpected {kind} artifact set")
    manifest = original_bytes(directory / "activity.json", limits.pop("activity.json"))
    hashes = {"activity.json": sha256(manifest).hexdigest()}
    hashes.update({name: sha256(original_bytes(directory / name, size)).hexdigest() for name, size in limits.items()})
    case = json.loads(manifest)
    trx_bytes = original_bytes(trx, 32 << 20)
    execution, output = passed_activity(trx_bytes, method, hashes["activity.json"])
    markers = ["IFW_ACTIVITY_SHA256=" + hashes["activity.json"]]
    if rust_backup_hash is not None:
        require(re.fullmatch(r"[0-9a-f]{64}", rust_backup_hash) is not None, "invalid returned database digest")
        markers.append("IFW_RUST_BACKUP_SHA256=" + rust_backup_hash)
    if kind == "deletion":
        markers.append("IFW_DELETE_TRASH_SHA256=" + hashes["peer-trash.jpg"])
    equal(sorted(line.strip() for line in output.strip().splitlines()), sorted(markers), "unexpected xUnit markers")
    equal([case["format"], case["platform"], case["osArchitecture"], case["processArchitecture"]],
          [f"ifw-csharp-worker-{kind}-activity-v1", platform, arch, arch], "wrong native target")
    require(bool(case["osDescription"].strip()), "missing operating system description")
    assemblies_read = {}
    for role, name in inputs.items():
        digest = sha256(original_bytes(assemblies / name, 32 << 20)).hexdigest()
        equal([case[role + "AssemblyVersion"], case[role + "AssemblySha256"]],
              ["3.0.4+" + revision, digest], "wrong loaded " + role + " assembly")
        assemblies_read[name] = digest
    summary = read_state(directory, case, hashes, reviewed_schema(revision, platform), platform == "windows", revision)
    return {"revision": revision, "reference": BASE, "testBlob": git("rev-parse", revision + ":" + source).decode().strip(),
            "platform": platform, "architecture": arch, "xunitExecution": execution, "fileSha256": hashes,
            "trxSha256": sha256(trx_bytes).hexdigest(), "assemblies": assemblies_read, **summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("repair", "deletion"))
    parser.add_argument("originals", type=Path)
    parser.add_argument("trx", type=Path)
    parser.add_argument("assemblies", type=Path)
    parser.add_argument("platform", choices=("linux", "windows"))
    parser.add_argument("architecture", choices=("x64", "arm64"))
    parser.add_argument("revision")
    args = parser.parse_args()
    print(json.dumps(verify(args.kind, args.originals, args.trx, args.assemblies, args.platform, args.architecture, args.revision),
                     indent=2, sort_keys=True))
