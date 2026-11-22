"""Compare actual .NET store lookups with independent SQL on the original snapshots."""

import json

from invariant_profile import VMR, decode, require, sha
from store import ACCOUNT, BASELINE, PAIRS, all_tables, artifact_directory, immutable_db, private_input, require_regular


def reader_files(directory, profiles):
    artifact_directory(directory)
    filenames = {"result.json", "invariant-uppercase.tsv"}
    require({path.name for path in directory.iterdir()} == filenames | set(profiles), "Unexpected reader capture members")
    paths = [directory / name for name in filenames]
    for profile in profiles:
        child = directory / profile
        artifact_directory(child)
        require({path.name for path in child.iterdir()} == {"sensitive.db", "insensitive.db"}, "Expected two reader copies")
        paths.extend(child.iterdir())
    for path in paths:
        require_regular(path)
    return {path.relative_to(directory).as_posix(): sha(path.read_bytes()) for path in paths}


def sql_observation(database, source, mapping):
    # The spellings used here are already absolute or relative in the native writer's syntax.
    # Bind the scalar-table-derived keys independently of the C# reader output.
    key = source.translate(mapping)
    columns = "source_path AS sourcePath, relative_path AS relativePath, asset_id AS assetId"
    query = f"SELECT {columns} FROM sync_entries WHERE account_scope=? AND source_key=?"
    entries = [dict(row) for row in database.execute(query + " ORDER BY relative_path_key", (ACCOUNT, key))]
    lookups = {}
    for name, pair in PAIRS.items():
        for spelling in pair:
            path = f"{name}-{spelling}.jpg"
            row = database.execute(query + " AND relative_path_key=?", (ACCOUNT, key, path.translate(mapping))).fetchone()
            lookups[path] = dict(row) if row else None
    return {"source": source, "entries": entries, "lookups": lookups}


def compare_case(original, copy, actual, source, writer_case, reader_map):
    require(actual["beforeSha256"] == writer_case["sha256"] and actual["afterSha256"] == sha(copy.read_bytes()),
            "Reader copy hash or input provenance differs")
    with immutable_db(original) as database, immutable_db(copy) as copied:
        require(all_tables(copied) == all_tables(database), "An actual reader changed the logical database")
        expected = (("display", source), ("stored", writer_case["sourceKey"]))
        signals = {}
        for label, spelling in expected:
            projection = sql_observation(database, spelling, reader_map)
            require(actual[label] == projection, f"C# {label} entries, original spellings or asset IDs disagree with SQL")
            signals[label] = {"source": spelling, "visibleEntries": len(projection["entries"]),
                              "successfulLookups": sum(row is not None for row in projection["lookups"].values())}
        history = database.execute("SELECT last_successful_sync_utc FROM sync_account_status WHERE account_scope=?",
                                   (ACCOUNT,)).fetchone()[0]
        require(actual["history"] == writer_case["history"] == history, "C# transfer history disagrees with the original SQL")
    return {"beforeSha256": actual["beforeSha256"], "afterSha256": actual["afterSha256"], "history": history,
            "pathLookupsCompared": 2 * sum(map(len, PAIRS.values())), **signals}


def verify_readers(reader_dirs, writer_dirs, tables, writers):
    originals = dict(zip(tables, writer_dirs, strict=True))
    writer_inputs = {profile: private_input(directory) for profile, directory in originals.items()}
    writer_docs = {profile: json.loads((directory / "result.json").read_bytes()) for profile, directory in originals.items()}
    builds, results = set(), {}
    for (reader, table), directory in zip(tables.items(), reader_dirs, strict=True):
        files = reader_files(directory, tables)
        doc = json.loads((directory / "result.json").read_bytes())
        require(doc["format"] == "ifw-managed-invariant-cross-readback-v1" and doc["reader"] == reader
                and doc["baseline"] == BASELINE and doc["runtime"] == "10.0.12" and doc["corelibBuild"].endswith("+" + VMR),
                "Unexpected reader report, profile or runtime")
        require(set(doc["observations"]) == set(tables), "The reader requires all three actual writers")
        mapping = decode(table)
        profile = doc["casingProfile"]
        require(profile["tableSha256"] == sha(table) and profile["changedScalars"] == len(mapping)
                and profile["scannedScalars"] == 1112064 and profile["contextBatchChecked"] is True
                and (directory / "invariant-uppercase.tsv").read_bytes() == table, "The active reader table differs")
        builds.add((doc["fixtureAssemblySha256"], doc["coreAssemblySha256"], doc["corelibSha256"]))
        observations = {}
        for writer, original in originals.items():
            manifest, observed = writer_docs[writer], doc["observations"][writer]
            require(all(doc[name] == manifest[name] for name in ("sources", "target", "os", "arch", "corelibSha256", "corelibBuild"))
                    and observed["writerFilesSha256"] == writer_inputs[writer] == writers[writer]["filesSha256"],
                    "Reader target, source pins or original digests disagree")
            require(set(observed["cases"]) == {"sensitive", "insensitive"}, "Both reader path modes are required")
            cases = {}
            for mode, actual in observed["cases"].items():
                name = mode + ".db"
                cases[mode] = compare_case(original / name, directory / writer / name, actual, manifest["sourcePath"],
                                           writers[writer]["cases"][mode], {} if mode == "sensitive" else mapping)
            observations[writer] = cases
        require(files == reader_files(directory, tables), "A reader copy changed during immutable verification")
        results[reader] = {"runtime": doc["runtime"], "corelibBuild": doc["corelibBuild"], "target": doc["target"],
                           "filesSha256": files, "writers": observations}
    require(len(builds) == 1, "The reader processes used different binaries")
    require(writer_inputs == {profile: private_input(directory) for profile, directory in originals.items()},
            "An original writer capture changed during the comparison")
    return results
