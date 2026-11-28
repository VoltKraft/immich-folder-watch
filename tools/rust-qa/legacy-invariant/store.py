"""Read finalized synthetic store studies using SQLite's immutable URI mode."""

import json
import sqlite3
import stat
from contextlib import contextmanager

from invariant_profile import ROOT, VMR, decode, require, sha

BASELINE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
ACCOUNT = "ifw-managed-invariant-study"
SEED = "2024-02-29T03:04:05.1234567+00:00"
PAIRS = {
    "long-s": ("S", "ſ"), "stroke": ("Ƛ", "ƛ"), "dotless": ("I", "ı"),
    "sharp-s": ("SS", "ß"), "garay": ("\U00010d50", "\U00010d70"), "beria": ("\U00016ea0", "\U00016ebb"),
}
FILES = {"result.json", "invariant-uppercase.tsv", "sensitive.db", "insensitive.db"}
ORDER = {
    "sync_entries": "account_scope,source_key,relative_path_key",
    "sync_timestamp_repairs": "account_scope,source_key,relative_path_key",
    "owned_albums": "account_scope,source_key,directory_key",
    "sync_account_status": "account_scope",
}


def artifact_directory(directory):
    base = ROOT / "artifacts/rust"
    require(directory.is_absolute() and directory.resolve() == directory and directory.is_relative_to(base),
            "Supply an absolute synthetic capture below artifacts/rust without links")


def require_regular(file):
    info = file.lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "Synthetic capture members must be regular files")


def private_input(directory):
    artifact_directory(directory)
    files = list(directory.iterdir())
    require({file.name for file in files} == FILES, "Unexpected synthetic capture members")
    for file in files:
        require_regular(file)
    return {file.name: sha(file.read_bytes()) for file in files}


def expected_entries(mapping, sensitive):
    fold = (lambda text: text) if sensitive else (lambda text: text.translate(mapping))
    rows, paths, aliases = {}, [], {}
    for pair, (upper, lower) in PAIRS.items():
        aliases[pair] = fold(upper) == fold(lower)
        for spelling, kind in ((upper, "upper"), (lower, "lower")):
            path = f"{pair}-{spelling}.jpg"
            rows[fold(path)] = (path, f"{pair}-{kind}")
            paths.append(path)
    return rows, {path: rows[fold(path)][1] for path in paths}, aliases


@contextmanager
def immutable_db(path):
    database = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA query_only=ON")
        for pragma, expected in (("journal_mode", "delete"), ("integrity_check", "ok"), ("user_version", 1)):
            require(database.execute("PRAGMA " + pragma).fetchone()[0] == expected, "Invalid standalone schema-v1 database")
        yield database
    finally:
        database.close()


def all_tables(database):
    return {table: [dict(row) for row in database.execute(f"SELECT * FROM {table} ORDER BY {order}")]
            for table, order in ORDER.items()}


def inspect_db(path, case, mode, source, profile, maps):
    sensitive = mode == "sensitive"
    keys = {name: source if sensitive else source.translate(mapping) for name, mapping in maps.items()}
    with immutable_db(path) as database:
        tables = all_tables(database)
        by_reader = {name: database.execute("SELECT count(*) FROM sync_entries WHERE account_scope=? AND source_key=?",
                                            (ACCOUNT, key)).fetchone()[0] for name, key in keys.items()}
    require(tables == case["tables"], "Immutable SQLite rows differ from the C# store's captured rows")
    entries = tables["sync_entries"]
    expected, lookups, aliases = expected_entries(maps[profile], sensitive)
    require(len(entries) == len(expected) and all(
        (r["account_scope"], r["source_path"], r["source_key"]) == (ACCOUNT, source, keys[profile]) for r in entries),
        "Unexpected entry count, source display or source key")
    require({r["relative_path_key"]: (r["relative_path"], r["asset_id"]) for r in entries} == expected,
            "Stored raw displays, relative keys or winning asset IDs differ from the external scalar table")
    require(case["lookups"] == lookups, "The legacy store returned different assets for the supplied names")
    require(tables["sync_account_status"] == [{"account_scope": ACCOUNT, "last_successful_sync_utc": SEED}]
            and case["history"] == SEED and not tables["owned_albums"] and not tables["sync_timestamp_repairs"],
            "Unexpected account history, albums or repairs")
    require(all(count == (len(entries) if sensitive or reader == profile else 0)
                for reader, count in by_reader.items()), "Unexpected cross-profile source-key predicate result")
    return {"sha256": case["sha256"], "sourceKey": keys[profile], "rows": len(entries),
            "sameIdentity": aliases, "directSqlSourceCounts": by_reader, "storeLookups": lookups, "history": case["history"]}


def verify_writers(directories, tables):
    maps = {name: decode(table) for name, table in tables.items()}
    manifest = json.loads((ROOT / "rust/tests/fixtures/legacy/linux/manifest.json").read_bytes())
    require(manifest["BehavioralBaseline"] == BASELINE, "Wrong shipping behavioral baseline")
    result, builds = {}, set()
    for (profile, table), directory in zip(tables.items(), directories, strict=True):
        before = private_input(directory)
        doc = json.loads((directory / "result.json").read_bytes())
        require(doc["format"] == "ifw-managed-invariant-store-differential-v1" and doc["baseline"] == BASELINE
                and doc["account"] == ACCOUNT and doc["seed"] == SEED, "Wrong synthetic capture identity")
        require(doc["runtime"] == "10.0.12" and doc["corelibBuild"].endswith("+" + VMR), "Wrong managed runtime build")
        os_name, arch = doc["os"], doc["arch"]
        require(os_name in ("linux", "windows") and arch in ("x64", "arm64"), "Unexpected native target")
        expected_target = f"{'win' if os_name == 'windows' else 'linux'}-{arch}"
        require(doc["target"] == expected_target, "The process runtime identifier disagrees with its native target")
        source = ("/IfwSynthetic/Archive-ſ-ƛ" if os_name == "linux" else "C:\\IfwSynthetic\\Archive-ſ-ƛ")
        require(source == doc["sourcePath"], "Unexpected synthetic source")
        source_names = ("Models/SyncStateEntry.cs", "Models/SyncTimestampRepair.cs",
                        "Services/SqliteSyncStateStore.cs", "Services/SqliteSyncStateStore.AlbumOwnership.cs")
        source_paths = ["src/ImmichFolderWatch.Core/" + name for name in source_names]
        require(doc["sources"] == {name: manifest["SourceHashes"][name] for name in source_paths},
                "The observed shipping source pins differ")
        builds.add((os_name, arch, doc["target"], doc["corelibSha256"], doc["coreAssemblySha256"], doc["fixtureAssemblySha256"]))
        observed = doc["casingProfile"]
        require(observed["scannedScalars"] == 1112064 and observed["contextBatchChecked"] is True
                and observed["changedScalars"] == len(maps[profile]) and observed["tableSha256"] == sha(table)
                and (directory / "invariant-uppercase.tsv").read_bytes() == table, "Wrong complete same-process writer table")
        require(set(doc["cases"]) == {"sensitive", "insensitive"}, "Expected the two explicit path modes")
        cases = {}
        for mode, case in doc["cases"].items():
            filename = mode + ".db"
            require(case["sha256"] == before[filename], "Original database digest differs")
            cases[mode] = inspect_db(directory / filename, case, mode, source, profile, maps)
        require(before == private_input(directory), "A synthetic source changed during immutable readback")
        result[profile] = {"runtime": doc["runtime"], "corelibBuild": doc["corelibBuild"], "target": doc["target"],
                           "sources": doc["sources"], "filesSha256": before, "cases": cases}
    require(len(builds) == 1, "Capture all writers on the same native target using the same binaries")
    return result
