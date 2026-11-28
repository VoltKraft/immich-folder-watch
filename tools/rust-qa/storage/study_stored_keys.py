"""Compare the read-only Rust diagnostic with the frozen three-writer Fedora study."""

import argparse
from collections import Counter
import json
import posixpath
from pathlib import Path
import shutil
import subprocess
import sys

from evidence import sha256, write_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "legacy-invariant"))
from invariant_profile import decode, require, three_profiles
from readers import verify_readers
from store import ACCOUNT, PAIRS, artifact_directory, immutable_db, private_input, verify_writers


WRITER_COMMIT = "86ae0380c48744b15487874942ae2f72e4cc5ec1"
READER_COMMIT = "3c58fc14c5dba26191e70afcdbb903ae562e25e4"
READER_EVIDENCE = "daf312d1aef1ff5f451abff9f964c0eec1710f64f88d44e0d31740c6ed99bf78"
PROFILES = {"icu15": ("older", "15.1.0"), "managed16": ("managed", "managed-invariant-10.0.12"),
            "icu17": ("current", "17.0.0")}


def authenticate(writers, readers, tables):
    writer_evidence, reader_evidence = [p / "evidence.json" for p in (writers, readers)]
    require(sha256(reader_evidence) == READER_EVIDENCE, "Different independent reader evidence")
    reader = json.loads(reader_evidence.read_bytes())
    require(reader["readerCommit"] == READER_COMMIT and reader["writerCommit"] == WRITER_COMMIT
            and reader["writerEvidenceSha256"] == sha256(writer_evidence), "Different writer or reader provenance")
    writer = json.loads(writer_evidence.read_bytes())
    require(writer["sourceCommit"] == WRITER_COMMIT and reader["shippingBaseline"] == writer["shippingBaseline"],
            "Different shipping baseline or writer revision")
    for evidence, root in ((writer, writers), (reader, readers)):
        require(evidence["comparisonSha256"] == sha256(root / "comparison.json"), "Different original comparison")
    original_dirs = {}
    reader_dirs = []
    for profile, (name, _) in PROFILES.items():
        directory = writers / "source/artifacts/rust" / name
        expected = writer["nativeWriters"][name]
        require(private_input(directory) == expected["files"] == reader["originalWriterFiles"][name],
                f"Different frozen C# writer files for {name}")
        manifest = json.loads((directory / "result.json").read_bytes())
        for key in ("corelibBuild", "corelibSha256", "fixtureAssemblySha256", "coreAssemblySha256"):
            require(expected[key] == manifest[key], "Writer build differs in " + key)
        original_dirs[profile] = directory
        reader_dirs.append(readers / "source/artifacts/rust" / ("reader-" + name))
    observed = verify_writers(original_dirs.values(), tables)
    compared = verify_readers(reader_dirs, original_dirs.values(), tables, observed)
    reference = json.loads((readers / "comparison.json").read_bytes())
    require(observed == reference["storeObservations"] and compared == reference["actualReaderComparisons"],
            "Frozen C# observations differ from the original database rows")
    return original_dirs, observed, reader["writerEvidenceSha256"]


def queries(source, maps):
    # Every C# writer used these twelve raw spellings, even when its upserts collided.
    spellings = [f"{family}-{character}.jpg" for family, pair in PAIRS.items() for character in pair]
    for label, root in [("display", source), *((profile, source.translate(mapping)) for profile, mapping in maps.items())]:
        for relative in spellings:
            yield label, dict(account=ACCOUNT, source=root, relative=relative)
    for label, account, root, path in (
        ("normalized source", ACCOUNT, source + "/x/../.", spellings[0]),
        ("missing at a historical source", ACCOUNT, source, "unwritten.jpg"),
        ("concordant missing path", ACCOUNT, "/IfwSynthetic/Other", "absent.jpg"),
        ("distinct account", ACCOUNT.upper(), source, spellings[0]),
        ("account with surrounding spaces", " " + ACCOUNT + " ", source, spellings[0]),
    ):
        yield label, dict(account=account, source=root, relative=path)


def expected(database, query, profiles, writer_map):
    source = posixpath.normpath(query["source"])
    relative, account = query["relative"], query["account"]
    # The historical writer is known independently in this corpus. Its source spelling
    # distinguishes all three physical source keys in insensitive mode. For each equally
    # spelled display found by any projection, compare the actual physical SQLite row.
    keys = set()
    forms = set()
    for mapping in profiles:
        database.create_function("fold", 1, lambda text, mapping=mapping: text.translate(mapping))
        form = (source.translate(mapping), relative.translate(mapping))
        forms.add(form)
        keys.update(tuple(row) for row in database.execute(
            "SELECT source_key,relative_path_key FROM sync_entries "
            "WHERE account_scope=? AND fold(source_path)=? AND fold(relative_path)=?", (account, *form)))
    if not keys:
        return {"status": "absent-concordant" if len(forms) == 1 else "absent-profile-dependent"}, None
    if len(keys) > 1:
        return {"status": "ambiguous", "distinctStoredKeys": len(keys)}, None
    stored, = keys
    direct = database.execute(
        "SELECT source_key,relative_path_key,source_path,relative_path,asset_id FROM sync_entries "
        "WHERE account_scope=? AND source_key=? AND relative_path_key=?",
        (account, source.translate(writer_map), relative.translate(writer_map))).fetchone()
    if direct is None:
        return {"status": "possible-alias"}, None
    require(tuple(direct[:2]) == stored, "Writer lookup and candidate physical key disagree")
    return {"status": "existing", "storedKey": list(stored), "tables": ["sync_entries"]}, dict(direct)


def invoke(probe, directory, mode, snapshot, requests, *, study=True):
    args = [probe, *(["--three-profile-study"] if study else []), directory, mode, snapshot]
    return subprocess.run(args, input=json.dumps(requests), encoding="utf-8", capture_output=True, cwd=ROOT, timeout=30)


def match(receipt, cases):
    require(len(receipt["lookup"]) == len(cases), "Different number of answers")
    for observation, case in zip(receipt["lookup"], cases, strict=True):
        require(observation == case["expected"], f"Historical lookup disagrees with raw SQL in {case['view']} for {case['query']}")


def exercise(probe, directory, profile, maps, mode):
    manifest = json.loads((directory / "result.json").read_bytes())
    snapshot = directory / (mode + ".db")
    digest = sha256(snapshot)
    original = manifest["sourcePath"]
    require(set(maps) == set(PROFILES) and len({original.translate(m) for m in maps.values()}) == 3,
            "Expected three independently distinguishable source keys")
    sensitive = mode == "sensitive"
    mapping = {} if sensitive else maps[profile]
    cases = []
    with immutable_db(snapshot) as database:
        physical = database.execute("SELECT DISTINCT source_key FROM sync_entries WHERE account_scope=?", (ACCOUNT,)).fetchall()
        require([r[0] for r in physical] == [original.translate(mapping)], "Incorrect writer projection for this SQL database")
        for label, query in queries(original, maps):
            answer, identity = expected(database, query, [{}] if sensitive else maps.values(), mapping)
            cases.append({"view": label, "query": query, "expected": answer, "physicalRow": identity})
    actual = invoke(probe, directory, mode, digest, [c["query"] for c in cases])
    require(actual.returncode == 0, "Rust inspection failed: " + actual.stderr)
    receipt = json.loads(actual.stdout)
    require(receipt["format"] == "ifw-stored-path-key-observations-v1" and receipt["mode"] == mode
            and receipt["inputFormat"] == manifest["format"] and receipt["writerProfile"] == PROFILES[profile][1]
            and receipt["writerReceiptSha256"] == sha256(directory / "result.json")
            and receipt["snapshotSha256"] == digest and receipt["os"] == "linux" and receipt["arch"] == "x86_64"
            and receipt["opaqueOwnershipRows"] == 0 and receipt["transferHistoryRows"] == 1, "Incomplete read-only receipt")
    match(receipt, cases)
    return {"receipt": receipt, "queries": cases, "statuses": Counter(item["expected"]["status"] for item in cases)}


def controls(probe, directories, output, runs):
    results = {}
    managed = directories["managed16"]
    base = json.loads((managed / "result.json").read_bytes())
    request = [{"account": ACCOUNT, "source": base["sourcePath"], "relative": "long-s-ſ.jpg"}]
    for name, message in (
        ("ordinary selection", "synthetic fixture manifest or recorded snapshot digest differs"),
        ("wrong comparison mode", "synthetic fixture manifest or recorded snapshot digest differs"),
        ("unrecognized same-process table", "unqualified full casing table"),
        ("swapped known table", "incomplete same-process writer casing evidence"),
        ("relabeled oracle and table", "unrecognized frozen study writer receipt"),
        ("different build", "unrecognized frozen study writer receipt"),
        ("altered database", "synthetic snapshot digest or file type differs"),
        ("companion", "a standalone backup without SQLite companions is required"),
    ):
        directory = output / name.replace(" ", "-")
        shutil.copytree(managed, directory)
        marker = directory / "result.json"
        doc = json.loads(marker.read_bytes())
        table = directory / "invariant-uppercase.tsv"
        mode, sha = "insensitive", doc["cases"]["insensitive"]["sha256"]
        if name == "ordinary selection":
            shutil.copyfile(marker, directory / "manifest.json")
        elif name == "wrong comparison mode":
            mode = "sensitive"
        elif name == "unrecognized same-process table":
            raw = table.read_bytes()
            require(raw.count(b"000061\t000041\n") == 1, "Missing unrelated small-a mapping")
            table.write_bytes(raw.replace(b"000061\t000041\n", b"000061\t000042\n"))
        elif name in ("swapped known table", "relabeled oracle and table"):
            other = directories["icu17"]
            shutil.copyfile(other / table.name, table)
            if name == "relabeled oracle and table":
                doc["casingProfile"] = json.loads((other / "result.json").read_bytes())["casingProfile"]
                write_json(marker, doc)
        elif name == "different build":
            doc["fixtureAssemblySha256"] = "0" * 64
            write_json(marker, doc)
        elif name == "altered database":
            with (directory / "insensitive.db").open("r+b") as stream:
                stream.write(b"X")
        elif name == "companion":
            (directory / "insensitive.db-wal").write_bytes(b"private test companion")
        before = {p.name: sha256(p) for p in directory.iterdir()}
        refusal = invoke(probe, directory, mode, sha, request, study=name != "ordinary selection")
        require(refusal.returncode and not refusal.stdout and message in refusal.stderr, "Wrong negative result for " + name)
        require(before == {p.name: sha256(p) for p in directory.iterdir()}, "A refused input changed")
        results[name] = refusal.stderr.strip()
    for profile, report in runs.items():
        run = report["insensitive"]
        for label, replacement in (
            ("false absence", {"status": "absent-concordant"}),
            ("wrong physical key", {"status": "existing", "storedKey": ["/elsewhere", "other.jpg"], "tables": ["sync_entries"]}),
        ):
            wrong = list(run["queries"])
            physical = next(index for index, c in enumerate(wrong) if c["expected"]["status"] == "existing")
            wrong[physical] = dict(wrong[physical], expected=replacement)
            try:
                match(run["receipt"], wrong)
            except ValueError as error:
                results[f"{label} {profile}"] = str(error)
            else:
                raise ValueError(f"Missed the {label} oracle control")
    return results


def run(probe, writers, readers, output):
    for directory in (writers, readers, output, probe.parent):
        artifact_directory(directory)
    require(not any(output.is_relative_to(evidence) for evidence in (writers, readers)),
            "Place the output outside both frozen evidence directories")
    require(probe.is_file() and not probe.is_symlink(), "Expected the built local Rust diagnostic")
    tables = three_profiles()
    directories, observed, writer_evidence_sha = authenticate(writers, readers, tables)
    original = {name: private_input(d) for name, d in directories.items()}
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    maps = {name: decode(table) for name, table in tables.items()}
    runs = {p: {mode: exercise(probe, directory, p, maps, mode) for mode in ("sensitive", "insensitive")}
            for p, directory in directories.items()}
    negative = controls(probe, directories, output, runs)
    require(original == {name: private_input(d) for name, d in directories.items()}, "A frozen writer input changed")
    result = {"format": "ifw-read-only-three-profile-study-v1", "target": "x86_64-unknown-linux-gnu",
              "writerCommit": WRITER_COMMIT, "readerCommit": READER_COMMIT, "readerEvidenceSha256": READER_EVIDENCE,
              "writerEvidenceSha256": writer_evidence_sha, "probeSha256": sha256(probe), "observerSha256": sha256(Path(__file__)),
              "writerFilesBeforeAndAfter": original, "writers": observed, "runs": runs, "controls": negative}
    write_json(output / "result.json", result)
    print(f"Verified {sum(len(r['queries']) for v in runs.values() for r in v.values())} lookups and {len(negative)} controls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("probe", "writers", "readers", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    run(*(p.absolute() for p in (args.probe, args.writers, args.readers, args.output)))
