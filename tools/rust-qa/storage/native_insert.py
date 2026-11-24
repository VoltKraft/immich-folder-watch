"""Compare native Rust and shipping C# writes with the original standalone SQLite files."""

from contextlib import closing
import json
import os
import sqlite3

from stored_keys import TABLES, casing_profiles, require, sha256


def snapshot(path):
    require(path.is_file() and not path.is_symlink() and
            all(not os.path.lexists(str(path) + tail) for tail in ("-wal", "-shm", "-journal")),
            f"Expected a standalone regular database: {path}")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        require(db.execute("PRAGMA integrity_check").fetchone() == ("ok",) and
                db.execute("PRAGMA user_version").fetchone() == (1,) and
                db.execute("PRAGMA journal_mode").fetchone() == ("delete",), "Expected a complete v1 backup")
        schema = db.execute("SELECT * FROM sqlite_schema ORDER BY type,name").fetchall()
        db.row_factory = sqlite3.Row
        return schema, {table: [dict(row) for row in db.execute(f'SELECT rowid,* FROM "{table}" ORDER BY rowid')]
                        for table in TABLES}


def run_native_insert(command, fixture, writer, dotnet, assembly):
    manifest = json.loads((fixture / "manifest.json").read_bytes())
    root = fixture.parent
    original = json.loads((root / "stored-keys/result.json").read_bytes())["inputs"]
    writer_profile = casing_profiles.match_reference((fixture / "invariant-uppercase.tsv").read_bytes())
    require(writer_profile is not None, "Unqualified native C# writer")
    tables = {}
    for profile in casing_profiles.PROFILES:
        data = profile.table.read_bytes()
        require(casing_profiles.match_reference(data) == profile, "Unknown historical uppercase table")
        tables[profile.version] = dict(tuple(int(value, 16) for value in row.split(b"\t"))
                                       for row in data.splitlines()[1:])
    for mode, case in manifest["cases"].items():
        command("native-insert-" + mode, [str(writer), "--native-insert", str(fixture), mode, case["sha256"]])
    command("csharp-native-upserts", [dotnet, str(assembly), "--casing-upsert", str(fixture)])
    upserts = root / "native-insert-upserts"
    reader = json.loads((upserts / "receipt.json").read_bytes())
    require(reader["readerProfile"] == manifest["casingProfile"] and reader["donorManifest"] == original["manifest.json"] and
            (reader["os"], reader["arch"]) == (manifest["os"], manifest["arch"]) and len(reader["observations"]) == 4,
            "The C# rollback reader does not match the original writer")
    report = {}
    for mode, case in manifest["cases"].items():
        rust = root / ("native-insert-" + mode)
        receipt = json.loads((rust / "receipt.json").read_bytes())
        require((receipt["os"], receipt["arch"]) == (manifest["os"], {"x64": "x86_64", "arm64": "aarch64"}[manifest["arch"]])
                and receipt["writerProfile"] == writer_profile.version
                and receipt["mode"] == mode and receipt["donor"] == case["sha256"], "The Rust writer used a different native fixture")
        request = receipt["stable"]
        raw_source = ("C:" if manifest["os"] == "windows" else "") + "/IfwSynthetic/Temp/../Insert/"
        require(request == dict(source=raw_source, account=manifest["account"], relative="New/Stable-é.jpg", asset="asset-native-stable"),
                "The Rust writer did not use the stable synthetic request")
        source, relative = os.path.normpath(raw_source), request["relative"].replace("/", os.sep)
        keys = {(source.translate(mapping), relative.translate(mapping)) for mapping in tables.values()}
        require(len(keys) == 1, "The stable pair differs between qualified profiles")
        source_key, relative_key = (source, relative) if mode == "sensitive" else keys.pop()
        dependent_keys = {}
        if mode == "insensitive":
            refused = receipt["refused"]
            dependent = request | dict(relative="New/Divergent-ƛ.jpg", asset="asset-native-dependent")
            dependent_keys = {v: [source.translate(m), dependent["relative"].replace("/", os.sep).translate(m)] for v, m in tables.items()}
            require(len(set(tuple(k) for k in dependent_keys.values())) == 2 and refused["request"] == dependent and
                    refused["decision"] == {"status": "absent-profile-dependent"} and refused["after"] == case["sha256"],
                    "The profile-dependent request was not refused on the original copy")
        else:
            require(receipt["refused"] is None, "Unexpected sensitive refusal")
        schema, before = snapshot(fixture / (mode + ".db"))
        rowid = max(r["rowid"] for r in before["sync_entries"]) + 1
        stamp = manifest["seed"]
        added = dict(rowid=rowid, account_scope=manifest["account"], source_path=source, relative_path=relative,
                     source_key=source_key, relative_path_key=relative_key, asset_id=request["asset"], album_name="Synthetic insert",
                     file_size=83, last_write_time_utc=stamp, last_synchronized_at_utc=stamp, direction=1, status=0, tombstone_expires_at_utc=None)
        after_rust = before | {"sync_entries": before["sync_entries"] + [added]}
        require(sha256(rust / "after.db") == receipt["after"] and snapshot(rust / "after.db") == (schema, after_rust),
                "Rust changed more than the one expected physical row")
        after_csharp = before | {"sync_entries": before["sync_entries"] + [added | {"file_size": 101}]}
        for pass_number in (1, 2):
            path = upserts / f"{mode}-{pass_number}.db"
            record = {"mode": mode, "pass": pass_number, "source": source, "relative": relative, "asset": request["asset"],
                      "readSize": 83 if pass_number == 1 else 101, "sha256": sha256(path)}
            require(record in reader["observations"] and snapshot(path) == (schema, after_csharp),
                    f"Shipping upsert {pass_number} in {mode} changed the historical rows or the inserted identity")
        report[mode] = dict(addedRow=added, entryCount=len(after_csharp["sync_entries"]), dependentKeys=dependent_keys)
    require({p.name: sha256(p) for p in fixture.iterdir()} == original, "Original native writer files changed")
    return dict(writerSha256=sha256(writer), readerReceiptSha256=sha256(upserts / "receipt.json"), modes=report)
