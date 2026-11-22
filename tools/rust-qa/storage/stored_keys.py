"""Compare the Rust read-only key lookup with completed synthetic C# backups."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from evidence import sha256, write_json

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/rust-qa/legacy"))
import casing_profiles

ARTIFACTS = (ROOT / "artifacts/rust").resolve()
BASELINE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
TABLES = ("sync_entries", "sync_timestamp_repairs", "owned_albums", "sync_account_status")
LOWER, UPPER = "\u019b", "\ua7dc"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def private(path):
    path = path.resolve()
    require(path.is_relative_to(ARTIFACTS) and path != ARTIFACTS, "Expected a path below artifacts/rust")
    return path


def readback(db, reference):
    require(sha256(db) == reference["sha256"], "C# snapshot digest mismatch")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Invalid reference backup")
        require(connection.execute("PRAGMA user_version").fetchone()[0] == 1, "Unexpected reference schema")
        for table in TABLES:
            rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
            canonical = lambda row: json.dumps(row, sort_keys=True, ensure_ascii=True)
            require(sorted(map(canonical, rows)) == sorted(map(canonical, reference["tables"][table])),
                    "C# and SQLite readback differ in " + table)


def queries(m, mode, tables):
    primary, other = m["account"], m["otherAccount"]
    source, lower, upper = m["sourcePath"], m["relativePath"], m["upperRelativePath"]
    journal, tombstone = m["repairRelativePath"], m["tombstoneRelativePath"]
    sensitive = mode == "sensitive"
    older = m["nativeUpperOfDiscriminator"] == LOWER
    cases = []

    def case(label, account, root, path, status, **values):
        cases.append((label, dict(account=account, source=root, relative=path), dict(status=status, **values)))

    def existing(label, account, lookup, original, *, repair_only=False, root=source):
        matching = []
        for row in tables["sync_entries"]:
            if row["account_scope"] == account and row["source_path"] == source and row["relative_path"] == original:
                matching.append(("sync_entries", [row["source_key"], row["relative_path_key"]]))
        for row in tables["sync_timestamp_repairs"]:
            value = json.loads(row["repair_json"])["OriginalEntry"]
            if row["account_scope"] == account and value["SourcePath"] == source and value["RelativePath"] == original:
                matching.append(("sync_timestamp_repairs", [row["source_key"], row["relative_path_key"]]))
        require(matching and len({tuple(pair) for _, pair in matching}) == 1, "Expected one C# original identity")
        if repair_only:
            require([table for table, _ in matching] == ["sync_timestamp_repairs"], "Expected a standalone repair")
        case(label, account, root, lookup, "existing", storedKey=matching[0][1], tables=sorted(t for t, _ in matching))

    if older and not sensitive:
        for label, query in (("original lower name", lower), ("original upper name", upper)):
            case(label, primary, source, query, "ambiguous", distinctStoredKeys=2)
    else:
        existing("original lower name", primary, lower, lower)
        existing("original upper name", primary, upper, upper if sensitive else lower)
    existing("same spelling in the other account", other, lower, lower)
    existing("standalone repair", primary, journal, journal, repair_only=True)
    existing("preserved tombstone", primary, tombstone, tombstone)
    if sensitive:
        case("changed journal source spelling", primary, source.replace(LOWER, UPPER), journal, "absent-concordant")
        case("changed spelling in the other account", other, source, upper, "absent-concordant")
    elif older:
        case("changed journal source spelling", primary, source.replace(LOWER, UPPER), journal, "possible-alias")
        case("changed spelling in the other account", other, source, upper, "possible-alias")
    else:
        existing("changed journal source spelling", primary, journal, journal, root=source.replace(LOWER, UPPER))
        existing("changed spelling in the other account", other, upper, lower)
    case("new concordant spelling", primary, source.replace(LOWER, "X"), "new.jpg", "absent-concordant")
    missing = "absent-concordant" if sensitive else "absent-profile-dependent"
    case("new file at a source affected by casing", primary, source, "new.jpg", missing)
    case("case-distinct account", primary.upper(), source, lower, missing)
    case("ownership directory is opaque", primary, source, m["albumDirectory"], missing)
    case("opaque album ID is not a path identity", primary, source, m["albumId"], missing)
    return cases


def run_probe(probe, directory, mode, snapshot, requests):
    return subprocess.run([str(probe), str(directory), mode, snapshot], cwd=ROOT,
                          input=json.dumps(requests), text=True, capture_output=True,
                          check=False, timeout=30)


def check_answers(probe, directory, mode, digest, cases, reference):
    result = run_probe(probe, directory, mode, digest, [q for _, q, _ in cases])
    require(result.returncode == 0, "Read-only Rust inspect failed: " + result.stderr.strip()[:800])
    answer = json.loads(result.stdout)
    require(answer["format"] == "ifw-stored-path-key-observations-v1" and answer["mode"] == mode and
            answer["snapshotSha256"] == digest and len(answer["lookup"]) == len(cases), "Wrong Rust receipt")
    require(answer["opaqueOwnershipRows"] == len(reference["owned_albums"]) and
            answer["transferHistoryRows"] == len(reference["sync_account_status"]), "Missing opaque state")
    for (label, _, expected), observed in zip(cases, answer["lookup"], strict=True):
        require(expected == observed, f"Unexpected Rust lookup for {label}: {observed}")
    return {"receipt": answer, "cases": [name for name, _, _ in cases]}


def control_copy(output, fixture, name):
    directory = output / name
    directory.mkdir()
    shutil.copyfile(fixture / "insensitive.db", directory / "insensitive.db")
    return directory


def mark_control(directory, original):
    digest = sha256(directory / "insensitive.db")
    write_json(directory / "manifest.json", {"format": "ifw-derived-path-key-control-v1",
               "baseSha256": original, "cases": {"insensitive": {"sha256": digest}}})
    return digest


def negative_controls(probe, fixture, output, m):
    source = m["sourcePath"]
    primary = m["account"]
    base = m["cases"]["insensitive"]
    tables = base["tables"]
    one = [dict(account=primary, source=source, relative=m["repairRelativePath"])]
    results = {}

    # Source under one qualified profile and relative path under the other cannot explain one row.
    directory = control_copy(output, fixture, "mixed-key-components")
    with closing(sqlite3.connect(directory / "insensitive.db")) as db, db:
        row = next(r for r in tables["sync_entries"] if r["account_scope"] == primary and r["status"] == 1)
        changed = db.execute("UPDATE sync_entries SET source_key=?,relative_path_key=? "
                             "WHERE account_scope=? AND source_key=? AND relative_path_key=?",
                             (row["source_key"].replace(UPPER, LOWER), row["relative_path_key"].replace(LOWER, UPPER),
                              primary, row["source_key"], row["relative_path_key"])).rowcount
        require(changed == 1, "Synthetic tombstone control was not created")
    digest = mark_control(directory, base["sha256"])
    cases = [("different profiles on one row", one[0], {"status": "unqualified-history"})]
    cases += [v for v in queries(m, "insensitive", tables) if v[0] == "same spelling in the other account"]
    results["mixedComponents"] = check_answers(probe, directory, "insensitive", digest, cases, tables)

    # A legitimate key in the entry table can conflict with a standalone journal under the other profile.
    directory = control_copy(output, fixture, "colliding-repair")
    row = next(r for r in tables["sync_timestamp_repairs"] if
               json.loads(r["repair_json"])["OriginalEntry"]["RelativePath"] == m["repairRelativePath"])
    old, new = (LOWER, UPPER) if m["nativeUpperOfDiscriminator"] == LOWER else (UPPER, LOWER)
    with closing(sqlite3.connect(directory / "insensitive.db")) as db, db:
        changed = db.execute("""
            INSERT INTO sync_entries
              (account_scope,source_path,source_key,relative_path,relative_path_key,asset_id,album_name,file_size,
               last_write_time_utc,direction,status,last_synchronized_at_utc,tombstone_expires_at_utc)
            SELECT account_scope,source_path,?,?,?,asset_id,album_name,file_size,
                   last_write_time_utc,direction,status,last_synchronized_at_utc,tombstone_expires_at_utc
              FROM sync_entries WHERE account_scope=? AND status=1
            """, (row["source_key"].replace(old, new), m["repairRelativePath"],
                  row["relative_path_key"].replace(old, new), primary)).rowcount
        require(changed == 1, "Synthetic entry/journal collision was not created")
    digest = mark_control(directory, base["sha256"])
    cases = [("distinct entry and journal keys", one[0], {"status": "ambiguous", "distinctStoredKeys": 2})]
    results["collidingJournal"] = check_answers(probe, directory, "insensitive", digest, cases, tables)

    for name in ("foreign-repair-account", "future-schema", "companion", "wrong-digest"):
        directory = control_copy(output, fixture, name)
        dbpath = directory / "insensitive.db"
        if name == "foreign-repair-account":
            with closing(sqlite3.connect(dbpath)) as db, db:
                document = json.loads(row["repair_json"])
                document["OriginalEntry"]["AccountScope"] = m["otherAccount"]
                db.execute("UPDATE sync_timestamp_repairs SET repair_json=? WHERE account_scope=? AND source_key=? AND relative_path_key=?",
                           (json.dumps(document), primary, row["source_key"], row["relative_path_key"]))
        elif name == "future-schema":
            with closing(sqlite3.connect(dbpath)) as db, db:
                db.execute("PRAGMA user_version=999")
        elif name == "companion":
            (directory / "insensitive.db-wal").write_bytes(b"synthetic companion sentinel")
        digest = mark_control(directory, base["sha256"])
        expected = "0" * 64 if name == "wrong-digest" else digest
        before = {p.name: sha256(p) for p in directory.iterdir()}
        run = run_probe(probe, directory, "insensitive", expected, one)
        require(run.returncode != 0 and not run.stdout, "Invalid control returned lookup data")
        require(before == {p.name: sha256(p) for p in directory.iterdir()}, "Rejected snapshot changed")
        results[name] = {"exitCode": run.returncode, "filesUnchanged": len(before), "error": run.stderr.strip()}
    return results


def exercise(probe, fixture, output):
    probe, fixture, output = (private(p) for p in (probe, fixture, output))
    require(probe.is_file() and fixture.is_dir(), "Missing executable or C# synthetic corpus")
    casing_profiles.require_notice()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    m = json.loads((fixture / "manifest.json").read_bytes())
    require(m["format"] == "ifw-qualified-path-key-fixture-v1" and m["baseline"] == BASELINE and
            m["nativeUpperOfDiscriminator"] in (LOWER, UPPER), "Unqualified C# discriminator or fixture")
    original = {p.name: sha256(p) for p in fixture.iterdir()}
    require(set(original) == {"manifest.json", "sensitive.db", "insensitive.db"}, "Expected standalone C# backups")
    modes = {}
    for mode in ("sensitive", "insensitive"):
        ref = m["cases"][mode]
        readback(fixture / (mode + ".db"), ref)
        modes[mode] = check_answers(probe, fixture, mode, ref["sha256"], queries(m, mode, ref["tables"]), ref["tables"])
        receipt = modes[mode]["receipt"]
        require(receipt["inputFormat"] == m["format"] and receipt["os"] == m["os"] and
                receipt["arch"] == {"x64": "x86_64", "arm64": "aarch64"}[m["arch"]],
                "C# and Rust executed on different native targets")
    controls = negative_controls(probe, fixture, output, m)
    require({p.name: sha256(p) for p in fixture.iterdir()} == original, "Original C# backup set changed")
    report = dict(format="ifw-qualified-stored-key-run-v1", source=m["baseline"], rustExecutableSha256=sha256(probe),
                  inputs=original, nativeUpperOfDiscriminator=m["nativeUpperOfDiscriminator"],
                  modes=modes, controls=controls)
    write_json(output / "result.json", report)
    print(f"Verified {sum(len(v['cases']) for v in modes.values())} native backup lookups and {len(controls)} controls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("probe", "fixture", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    exercise(args.probe, args.fixture, args.output)
