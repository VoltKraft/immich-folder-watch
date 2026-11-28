"""Update a single synthetic file size on historical copies and read it through the shipping C# store."""

import argparse
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess

from evidence import sha256, write_json
from study_stored_keys import PROFILES, READER_COMMIT, ROOT, WRITER_COMMIT, authenticate, decode, require, three_profiles
from store import ACCOUNT, SEED, all_tables, artifact_directory, immutable_db, private_input


AREA = ROOT / "artifacts/rust/stored-key-mutations"
NAMES = {"icu15": "long-s-S.jpg", "managed16": "stroke-Ƛ.jpg", "icu17": "beria-𖺠.jpg"}
PK = ("account_scope", "source_key", "relative_path_key")


def finalized_hash(path):
    artifact_directory(path.parent)
    def companions_absent():
        for suffix in ("-journal", "-wal", "-shm"):
            require(not os.path.lexists(str(path) + suffix), "Expected a finalized SQLite database without companions")
    companions_absent()
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Expected a single-link regular study file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(fd)
        require(os.path.samestat(info, opened) and opened.st_nlink == 1, "Study input changed before the read")
        header = stream.read(20)
        require(header[:16] == b"SQLite format 3\0" and header[18:20] == b"\x01\x01",
                "Expected a finalized rollback-journal database header")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        require(os.path.samestat(opened, path.lstat()) and os.fstat(fd).st_nlink == 1, "A study input was replaced")
    companions_absent()
    return digest


def finalized_pair(directory):
    artifact_directory(directory)
    names = {"before.db", "after.db"}
    def members():
        require({p.name for p in directory.iterdir()} == names, "Expected exactly the finalized before.db and after.db pair")
    members()
    hashes = {name: finalized_hash(directory / name) for name in sorted(names)}
    members()
    return hashes


def database_state(path):
    initial = finalized_hash(path)
    with immutable_db(path) as db:
        schema = [tuple(r) for r in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name")]
        state = all_tables(db)
    require(finalized_hash(path) == initial, "Input changed during immutable SQL readback")
    return schema, state


def rust_run(probe, directory, destination, mode, query, flag=()):
    args = [probe, *flag, directory, mode, sha256(directory / (mode + ".db")), destination]
    return subprocess.run(args, cwd=ROOT, input=json.dumps(query), capture_output=True, encoding="utf-8", timeout=30, umask=0)


def inspect_copy(directory, mode, output, query, probe, decision, key=None, unexplained=False):
    donor = directory / (mode + ".db")
    original_schema, original_tables = database_state(donor)
    result = rust_run(probe, directory, output, mode, query, ["--unexplained-control"] if unexplained else [])
    require(result.returncode == 0, "Rust copy update failed: " + result.stderr)
    receipt = json.loads(result.stdout)
    inputs = finalized_pair(output)
    before, after = (output / (phase + ".db") for phase in ("before", "after"))
    permissions = {name: oct(stat.S_IMODE(path.stat().st_mode)) for name, path in (("directory", output), ("before.db", before), ("after.db", after))}
    require(permissions == {"directory": "0o700", "before.db": "0o600", "after.db": "0o600"},
            "The direct Rust entry point requires private outputs even with umask zero")
    require(receipt["format"] == "ifw-study-file-size-update-v1" and receipt["mode"] == mode and receipt["request"] == query
            and receipt["donorSha256"] == sha256(donor) and receipt["writerReceiptSha256"] == sha256(directory / "result.json")
            and receipt["afterSha256"] == sha256(after) and receipt["beforeSha256"] == sha256(before)
            and receipt["preparedUnexplainedControl"] == unexplained and receipt["replacementFileSize"] == 37
            and receipt["decision"]["status"] == decision, "Wrong Rust decision or input/output identity")
    before_schema, before_tables = database_state(before)
    after_schema, after_tables = database_state(after)
    require(original_schema == before_schema == after_schema, "Schema or indices changed")
    if unexplained:
        expected = copy.deepcopy(original_tables)
        damaged, = [r for r in expected["sync_entries"] if r["account_scope"] == ACCOUNT and r["relative_path"] == "sharp-s-ß.jpg"]
        damaged["relative_path_key"] = "!ifw-derived-control!"
        expected["sync_entries"].sort(key=lambda r: tuple(r[k] for k in PK))
        require(before_tables == expected, "Negative fixture setup changed other data")
    else:
        require(sha256(before) == sha256(donor) and before_tables == original_tables, "Working input differs from donor")
    expected = copy.deepcopy(before_tables)
    if key is None:
        require(receipt["rowsChanged"] == 0 and receipt["repeatAtTarget"] is None and sha256(before) == sha256(after), "Refusal wrote to the copy")
    else:
        require(receipt["rowsChanged"] == 1 and receipt["decision"]["storedKey"] == list(key[1:])
                and receipt["decision"]["tables"] == ["sync_entries"], "Rust used a different physical identity")
        row, = [r for r in expected["sync_entries"] if tuple(r[k] for k in PK) == key]
        require(row["file_size"] == 19, "Unexpected initial file size")
        row["file_size"] = 37
        require(receipt["repeatAtTarget"] == {"expectedFileSize": 37, "decision": {"status": "unchanged-size"}, "rowsChanged": 0},
                "The genuine retry at the stored target must preserve the updated database")
    require(expected == after_tables, "Unexpected change to a row, field, identity, journal, binding or history")
    require(inputs == finalized_pair(output), "A finalized pair changed during the observation")
    receipt["observedPermissionsAtUmaskZero"] = permissions
    return receipt


def view(db, source, relative, mapping):
    columns = "account_scope AS account,source_path AS source,relative_path AS relative,asset_id AS asset,file_size AS size"
    query = f"SELECT {columns} FROM sync_entries WHERE account_scope=? AND source_key=?"
    physical = (ACCOUNT, source.translate(mapping))
    rows = [dict(r) for r in db.execute(query + " ORDER BY relative_path_key", physical)]
    single = db.execute(query + " AND relative_path_key=?", (*physical, relative.translate(mapping))).fetchone()
    return {"source": source, "relative": relative, "get": dict(single) if single else None, "list": rows}


def check_reader(report, directories, cases, mappings, reader):
    comparisons = {}
    for writer, directory in directories.items():
        stored = json.loads((directory / "result.json").read_bytes())
        for mode in ("sensitive", "insensitive"):
            fold = {} if mode == "sensitive" else mappings[reader]
            relative = NAMES[writer]
            observed = {}
            case_directory = cases / writer / mode
            inputs = finalized_pair(case_directory)
            for phase in ("before", "after"):
                key = f"{writer}/{mode}/{phase}"
                item = report["observations"][key]
                dbpath = case_directory / (phase + ".db")
                require(item["inputSha256"] == inputs[dbpath.name] and item["history"] == SEED, "Wrong C# input or history")
                display = stored["sourcePath"]
                with immutable_db(dbpath) as db:
                    source, = db.execute("SELECT DISTINCT source_key FROM sync_entries WHERE account_scope=?", (ACCOUNT,)).fetchall()
                    for name, spelling in (("display", display), ("storedKey", source[0])):
                        require(item[name] == view(db, spelling, relative, fold), "C# path listing or exact lookup differs from raw SQL: " + key)
                value = item["display"]["get"]
                expected_size = 19 if phase == "before" else 37
                if mode == "sensitive" or reader == writer:
                    require(value is not None and value["size"] == expected_size and value in item["display"]["list"],
                            "Both shipping store APIs must expose the size")
                else:
                    require(value is None and not item["display"]["list"], "Unexpected cross-profile source match")
                observed[phase] = {v: item[v]["get"] for v in ("display", "storedKey")}
            require(inputs == finalized_pair(case_directory), "A finalized case changed during the independent SQL read")
            comparisons[f"{writer}/{mode}"] = observed
    require(len(report["observations"]) == 12, "Expected every before/after input exactly once")
    return comparisons


def reader_input_controls(dotnet, assembly, env, output, directories, maps, reader, valid_report):
    controls = output / "reader-input-controls"
    cases = controls / "cases"
    shutil.copytree(output / "cases", cases)
    pair = cases / "icu15/sensitive"
    main = pair / "after.db"
    results = {}

    def reject(label, python_message, csharp_message):
        try:
            check_reader(valid_report, directories, cases, maps, reader)
        except ValueError as error:
            require(python_message in str(error), "Unexpected independent SQL refusal: " + str(error))
        else:
            raise ValueError("The independent SQL reader accepted " + label)
        destination = controls / ("read-" + label)
        process = subprocess.run([dotnet, assembly, "read-sizes", cases, destination],
                                 cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
        require(process.returncode == 2 and not process.stdout and csharp_message in process.stderr
                and not destination.exists(), "The C# reader did not refuse " + label + ": " + process.stderr)
        results[label] = {"python": python_message, "csharp": process.stderr.strip(), "exitCode": process.returncode}

    # A committed WAL update is visible from a new connection while the main file still contains 37.
    args = (ACCOUNT, NAMES["icu15"])
    where = " WHERE account_scope=? AND relative_path=?"
    select = "SELECT file_size FROM sync_entries" + where
    with closing(sqlite3.connect(main)) as writer:
        require(writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",), "Expected a live WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        require(writer.execute("UPDATE sync_entries SET file_size=38" + where + " AND file_size=37", args).rowcount == 1,
                "Expected one committed WAL change on the disposable copy")
        writer.commit()
        with closing(sqlite3.connect(main.as_uri() + "?mode=ro", uri=True)) as active:
            live_size = active.execute(select, args).fetchone()[0]
        with closing(sqlite3.connect(main.as_uri() + "?mode=ro&immutable=1", uri=True)) as isolated:
            main_size = isolated.execute(select, args).fetchone()[0]
        require((main_size, live_size) == (37, 38), "The WAL control needs distinct committed and main-file states")
        companions = [main.with_name(main.name + suffix) for suffix in ("-wal", "-shm")]
        require(all(p.stat().st_size > 0 for p in companions), "Missing live SQLite companions")
        snapshot = controls / "active-wal"
        snapshot.mkdir(mode=0o700)
        for file in [main, *companions]:
            shutil.copyfile(file, snapshot / file.name)
        reject("live-wal", "exactly the finalized", "finalized pair")
        require(all(sha256(p) == sha256(snapshot / p.name) for p in [main, *companions]), "A reader altered the active WAL fixture")
        results["live-wal"].update(mainFileSize=main_size, committedSize=live_size,
                                   files={p.name: sha256(snapshot / p.name) for p in [main, *companions]})

    require({p.name for p in pair.iterdir()} == {"before.db", "after.db"}, "SQLite did not close its disposable WAL")
    shutil.copyfile(snapshot / "after.db", main)
    reject("wal-header-alone", "rollback-journal database header", "rollback-journal database header")
    # Keep the tested members separate from the six Rust outputs and the original donors.
    shutil.copyfile(output / "cases/icu15/sensitive/after.db", main)
    extra = pair / "unexpected"
    extra.touch()
    reject("unexpected-member", "exactly the finalized", "finalized pair")
    extra.unlink()
    main.unlink()
    main.symlink_to("before.db")
    reject("symbolic-link", "single-link regular", "finalized pair")
    main.unlink()
    main.hardlink_to(pair / "before.db")
    reject("hard-link", "single-link regular", "single-link regular")
    main.unlink()
    os.mkfifo(main, 0o600)
    reject("named-pipe", "single-link regular", "regular")
    main.unlink()
    return results


def read_csharp(readers, dotnet, reader_dll, older_icu, output, directories, maps, tables):
    evidence = json.loads((readers / "evidence.json").read_bytes())
    require(sha256(dotnet) == evidence["sdkSha256"], "Use the SDK host from the verified C# reader")
    frozen = readers / "build/bin/StoreIdentities/release"
    require(sha256(frozen / "StoreIdentities.dll") == evidence["readerAssemblySha256"], "Different previous reader")
    # Keep the already verified shipping Core and its original runtime dependencies.
    runtime = output / "reader-runtime"
    shutil.copytree(frozen, runtime)
    assembly = runtime / "StoreIdentities.dll"
    shutil.copyfile(reader_dll, assembly)
    digest = sha256(assembly)
    receipts = {}
    for profile, (label, _) in PROFILES.items():
        original = evidence["readers"][label]
        env = {k:v for k,v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")
               and not k.startswith(("DOTNET_", "COMPlus_", "CORECLR_"))}
        for name in ("HOME", "DOTNET_CLI_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
            private = output / "environment" / label / name
            private.mkdir(parents=True, mode=0o700)
            env[name] = str(private)
        env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_GENERATE_ASPNET_CERTIFICATE="false", IFW_ORACLE_EXPECT_ARCH="x64")
        if profile == "managed16":
            env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = "1"
        elif profile == "icu15":
            for lib, expected in original["loadedIcuSha256"].items():
                require(sha256(older_icu / lib) == expected, "Different ICU 74 input: " + lib)
            env.update(LD_LIBRARY_PATH=str(older_icu), DOTNET_SYSTEM_GLOBALIZATION_APPLOCALICU="74.2")
        destination = output / ("reader-" + profile)
        process = subprocess.run([dotnet, assembly, "read-sizes", output / "cases", destination],
                                 cwd=ROOT, env=env, capture_output=True, timeout=180)
        (output / ("reader-" + profile + ".log")).write_bytes(process.stdout + process.stderr)
        require(process.returncode == 0, "The native C# reader failed: " + process.stderr.decode()[-1000:])
        path = destination / "result.json"
        data = json.loads(path.read_bytes())
        require(data["format"] == "ifw-study-file-size-csharp-v1" and data["reader"] == profile and data["target"] == "linux-x64"
                and data["runtime"] == "10.0.12" and data["baseline"] == evidence["shippingBaseline"]
                and data["sources"] == json.loads((directories[profile] / "result.json").read_bytes())["sources"]
                and data["casingProfile"] == original["profile"] and (destination / "invariant-uppercase.tsv").read_bytes() == tables[profile]
                and data["fixtureAssemblySha256"] == digest and data["corelibBuild"] == original["corelibBuild"]
                and data["corelibSha256"] == original["corelibSha256"] and data["coreAssemblySha256"] == original["coreAssemblySha256"]
                == sha256(runtime / "ImmichFolderWatch.Core.dll"), "Different native C# process, shipping Core, or casing")
        receipts[profile] = {"resultSha256": sha256(path), "coreAssemblySha256": data["coreAssemblySha256"],
                             "corelibSha256": data["corelibSha256"], "observerSha256": digest,
                             "cases": check_reader(data, directories, output / "cases", maps, profile)}
        if profile == "icu15":
            controls = reader_input_controls(dotnet, assembly, env, output, directories, maps, profile, data)
    return receipts, controls


def run(probe, writers, readers, dotnet, reader_dll, older_icu, output):
    for directory in (writers, readers, output, probe.parent, reader_dll.parent, older_icu):
        artifact_directory(directory)
    require(output.is_relative_to(AREA) and output != AREA and not any(output.is_relative_to(d) for d in (writers, readers)),
            "Use a fresh run directory inside artifacts/rust/stored-key-mutations")
    tables = three_profiles()
    directories, _, evidence = authenticate(writers, readers, tables)
    donors = {p: private_input(d) for p,d in directories.items()}
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    maps = {p: decode(t) for p,t in tables.items()}
    good = {}
    for profile, directory in directories.items():
        source = json.loads((directory / "result.json").read_bytes())["sourcePath"]
        parent = output / "cases" / profile
        parent.mkdir(parents=True)
        for mode in ("sensitive", "insensitive"):
            mapping = {} if mode == "sensitive" else maps[profile]
            relative = NAMES[profile]
            key = (ACCOUNT, source.translate(mapping), relative.translate(mapping))
            query = {"account": ACCOUNT, "source": source, "relative": relative, "expectedFileSize": 19}
            good[f"{profile}/{mode}"] = inspect_copy(directory, mode, parent / mode, query, probe, "existing", key)
    negative = {}
    parent = output / "controls"
    parent.mkdir()
    source = json.loads((directories["icu15"] / "result.json").read_bytes())["sourcePath"]
    for name, spelling, path, old, expected in (
        ("ambiguous", source, "stroke-ƛ.jpg", 19, "ambiguous"),
        ("alias", source.translate(maps["managed16"]), "long-s-S.jpg", 19, "possible-alias"),
        ("unexplained", source, "dotless-I.jpg", 19, "unqualified-history"),
        ("absent", source, "unwritten.jpg", 19, "absent-profile-dependent"),
        ("absent-concordant", "/IfwSynthetic/other", "new.jpg", 19, "absent-concordant"),
        ("stale", source, "long-s-S.jpg", 20, "stale-size"),
        ("requested-target-is-stale", source, "long-s-S.jpg", 37, "stale-size"),
        ("wrong-account", source, "long-s-S.jpg", 19, "absent-profile-dependent"),
    ):
        query = {"account": ACCOUNT.upper() if name == "wrong-account" else ACCOUNT, "source": spelling,
                 "relative": path, "expectedFileSize": old}
        negative[name] = inspect_copy(directories["icu15"], "insensitive", parent / name, query, probe, expected,
                                      unexplained=name == "unexplained")
    other = parent / "unknown-writer"
    shutil.copytree(directories["icu15"], other)
    table = other / "invariant-uppercase.tsv"
    raw = table.read_bytes()
    require(raw.count(b"000061\t000041\n") == 1, "Missing the unrelated small-a mapping")
    table.write_bytes(raw.replace(b"000061\t000041\n", b"000061\t000042\n"))
    manifest = json.loads((other / "result.json").read_bytes())
    manifest["casingProfile"]["tableSha256"] = sha256(table)
    write_json(other / "result.json", manifest)
    before = private_input(other)
    refused = rust_run(probe, other, parent / "unknown-attempt", "insensitive", query)
    require(refused.returncode and not refused.stdout and "unqualified full casing table" in refused.stderr
            and before == private_input(other) and not (parent / "unknown-attempt").exists(), "Unknown writer reached an update")
    negative["unknown-writer"] = {"error": refused.stderr.strip(), "filesBeforeAndAfter": before}
    csharp, pair_controls = read_csharp(readers, dotnet, reader_dll, older_icu, output, directories, maps, tables)
    for label, receipt in good.items():
        observed = finalized_pair(output / "cases" / label)
        for phase in ("before", "after"):
            require(observed[phase + ".db"] == receipt[phase + "Sha256"], "A Rust output changed")
    require(donors == {p: private_input(d) for p,d in directories.items()}, "An original writer changed")
    write_json(output / "result.json", {"format":"ifw-existing-file-size-study-v1", "writerCommit":WRITER_COMMIT,
               "readerCommit":READER_COMMIT, "writerEvidenceSha256":evidence, "writerFilesBeforeAndAfter":donors,
               "probeSha256":sha256(probe), "observerSha256":sha256(Path(__file__)), "updates":good, "controls":negative,
               "readerInputControls":pair_controls, "csharp":csharp})
    print(f"Verified {len(good)} one-field updates and retries, {len(negative)} mutation refusals, "
          f"{len(pair_controls)} paired-reader refusals and 36 shipping C# before/after reads")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("probe", "writers", "readers", "dotnet", "reader-dll", "older-icu", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    run(*(p.absolute() for p in (args.probe, args.writers, args.readers, args.dotnet, args.reader_dll, args.older_icu, args.output)))
