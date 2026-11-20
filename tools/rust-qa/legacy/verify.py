#!/usr/bin/env python3
"""Drive actual Rust scalar/path codecs with verified synthetic C# reference data.

Python's sqlite3/json decode the fixture container only. Expected scalar answers
come from the C# BCL oracle or the checked-in C# corpus, never from Rust output.
This does not establish a Rust SQLite or YAML implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile


def utf16_hex(value: str) -> str:
    return value.encode("utf-16-be", errors="surrogatepass").hex().upper()


def text_hex(value: str) -> str:
    return value.encode("utf-8").hex()


def verified_manifest(root: Path, field: str, expected_format: str) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["Format"] != expected_format:
        raise ValueError("unsupported fixture manifest format")
    for name, expected in manifest[field].items():
        path = Path(name)
        if path.is_absolute() or path.drive or ".." in path.parts or "\\" in name:
            raise ValueError("invalid fixture payload path")
        raw = (root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"reference payload digest mismatch: {name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--scalar-reference", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("rust/tests/fixtures/legacy"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unicode-data", type=Path,
                        help="Optional separately downloaded/pinned official UnicodeData.txt; no network is used here")
    args = parser.parse_args()
    manifest = verified_manifest(args.scalar_reference, "Payloads", "ifw-rw02-scalar-reference-v1")
    if manifest["ScannedScalars"] != 0x110000 - 0x800 or not manifest["ContextBatchEquivalenceChecked"]:
        raise AssertionError("incomplete C# scalar reference")
    native = manifest["OS"]
    if native not in {"linux", "windows"}:
        raise AssertionError("unsupported native platform")
    root = args.fixtures / native
    legacy_manifest = verified_manifest(root, "Fixtures", "ifw-rw01-legacy-v1")
    if legacy_manifest["Platform"] != native or not legacy_manifest["SyntheticOnly"]:
        raise AssertionError("legacy reference platform or isolation mismatch")
    map_path = args.scalar_reference / "invariant-uppercase.tsv"
    map_lines = map_path.read_text(encoding="utf-8").splitlines()
    if map_lines[0] != "IFW-INVARIANT-UPPERCASE-V1":
        raise AssertionError("unknown casing map")
    pairs = [tuple(int(field, 16) for field in line.split("\t")) for line in map_lines[1:]]
    mapping = dict(pairs)
    if len(mapping) != len(pairs) or len(mapping) != manifest["ChangedScalars"]:
        raise AssertionError("casing map count mismatch")

    requests: list[str] = []
    expected: list[str] = []
    labels: list[str] = []
    categories: dict[str, int] = {}

    def case(category: str, request: str, response: str) -> None:
        requests.append(request)
        expected.append(response)
        labels.append(f"{category} #{categories.get(category, 0) + 1}")
        categories[category] = categories.get(category, 0) + 1

    expected_arch = {"X64": "x86_64", "Arm64": "aarch64"}[manifest["ProcessArchitecture"]]
    if manifest["ProcessArchitecture"] != manifest["OSArchitecture"]:
        raise AssertionError("C# scalar reference was not native")
    case("native identity", "platform", f"ok\t{native}\t{expected_arch}")

    timestamps = json.loads((args.scalar_reference / "timestamps.json").read_text(encoding="utf-8"))
    if len(timestamps) != manifest["TimestampVectors"]:
        raise AssertionError("timestamp reference count mismatch")
    by_sql = {row["Sql"]: row for row in timestamps}
    by_json = {row["JsonScalar"]: row for row in timestamps}

    def time_response(row: dict) -> str:
        return (f"ok\t{row['UtcTicks']}\t{row['Sql']}\t{row['UnixSeconds']}\t"
                f"{row['SubsecondNanoseconds']}\t{row['JsonScalar']}")

    for row in timestamps:
        for command in [f"sql\t{row['Sql']}", f"json-time\t{row['JsonScalar']}",
                        f"ticks\t{row['UtcTicks']}",
                        f"unix\t{row['UnixSeconds']}\t{row['SubsecondNanoseconds']}"]:
            case("BCL timestamp", command, time_response(row))

    # Python reads the container. Numeric ticks/Unix answers for every scalar
    # were independently calculated by the C# oracle from these same records.
    sql_times: set[str] = set()
    repair_times: set[str] = set()
    table_counts = {}
    for sensitivity in ["sensitive", "insensitive"]:
        with sqlite3.connect(":memory:") as database:
            database.execute("PRAGMA trusted_schema=OFF")
            database.executescript((root / "sqlite" / f"{sensitivity}.sql").read_text(encoding="utf-8"))
            tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {"sync_entries", "owned_albums", "sync_timestamp_repairs", "sync_account_status"}:
                raise AssertionError("unexpected fixture schema")
            table_counts[sensitivity] = {table: database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                                         for table in sorted(tables)}
            for modified, synced, expiry, direction, status, source, source_key, relative, relative_key in database.execute(
                "SELECT last_write_time_utc,last_synchronized_at_utc,tombstone_expires_at_utc,direction,status,"
                "source_path,source_key,relative_path,relative_path_key FROM sync_entries"
            ):
                sql_times.update(value for value in [modified, synced, expiry] if value is not None)
                for command, value in [("direction", direction), ("status", status)]:
                    case("SQLite enum", f"{command}\t{value}", f"ok\t{value}")
                for raw, key in [(source, source_key), (relative, relative_key)]:
                    case("SQLite key", f"key\t{str(sensitivity == 'sensitive').lower()}\t{text_hex(raw)}",
                         "ok\t" + text_hex(key))
            sql_times.update(row[0] for row in database.execute("SELECT last_successful_sync_utc FROM sync_account_status"))
            for (payload,) in database.execute("SELECT repair_json FROM sync_timestamp_repairs"):
                repair = json.loads(payload)
                repair_times.update([repair["CreationTimeUtc"], repair["LastWriteTimeUtc"],
                                     repair["OriginalEntry"]["LastWriteTimeUtc"],
                                     repair["OriginalEntry"]["LastSynchronizedAtUtc"]])
            source = json.loads((root / "sqlite" / f"{sensitivity}.expected.json").read_text(encoding="utf-8"))["Source"]
            for (source_key,) in database.execute("SELECT source_key FROM owned_albums"):
                case("owned album source key", f"key\t{str(sensitivity == 'sensitive').lower()}\t{text_hex(source)}",
                     "ok\t" + text_hex(source_key))

    for command, values in [("sql", sql_times), ("json-time", repair_times)]:
        for value in sorted(values):
            row = (by_sql if command == "sql" else by_json)[value]
            case("SQLite/repair time", command + "\t" + value, time_response(row))

    paths = json.loads((root / "sqlite/path-vectors.json").read_text(encoding="utf-8"))["Vectors"]
    for row in paths:
        case("native source path", "source\t" + text_hex(row["SourceInput"]), "ok\t" + text_hex(row["SourcePath"]))
        case("native relative path", "relative\t" + text_hex(row["RelativeInput"]), "ok\t" + text_hex(row["RelativePath"]))
        for path, key in [(row["SourcePath"], row["SourceKey"]), (row["RelativePath"], row["RelativePathKey"])]:
            case("native path key", f"key\t{str(row['PathsCaseSensitive']).lower()}\t{text_hex(path)}", "ok\t" + text_hex(key))

    for row in json.loads((root / "identities.json").read_text(encoding="utf-8"))["InvariantUppercase"]:
        case("reviewed uppercase", "uppercase\t" + utf16_hex(row["Input"]), "ok\t" + utf16_hex(row["Output"]))
    for row in json.loads((args.scalar_reference / "utf16-vectors.json").read_text(encoding="utf-8")):
        case("UTF-16 BCL", "uppercase\t" + row["Input"], "ok\t" + row["Output"])

    # Exhaustively check the Rust mapping operation over every valid scalar,
    # including all unchanged characters. Batches keep every request bounded.
    batch: list[str] = []
    batch_upper: list[str] = []
    for scalar in range(0x110000):
        if 0xD800 <= scalar <= 0xDFFF:
            continue
        batch.append(chr(scalar))
        batch_upper.append(chr(mapping.get(scalar, scalar)))
        if len(batch) == 4096:
            case("exhaustive scalar batch", "uppercase\t" + utf16_hex("".join(batch)),
                 "ok\t" + utf16_hex("".join(batch_upper)))
            batch.clear()
            batch_upper.clear()
    if batch:
        case("exhaustive scalar batch", "uppercase\t" + utf16_hex("".join(batch)),
             "ok\t" + utf16_hex("".join(batch_upper)))

    for invalid in ["1900-02-29T00:00:00.0000000+00:00", "2024-02-30T00:00:00.0000000+00:00",
                    "0000-01-01T00:00:00.0000000+00:00", "2024-01-01T24:00:00.0000000+00:00",
                    "2024-01-01T00:00:60.0000000+00:00", "2024-01-01T00:00:00.0000000Z",
                    "2024-01-01T00:00:00.0000000+01:00", "2024-01-01T00:00:00.1+00:00"]:
        case("negative control", "sql\t" + invalid, "err")
    for command in ["ticks\t-1", "ticks\t3155378976000000000", "unix\t0\t1", "unix\t0\t1000000000",
                    "unix\t-9223372036854775808\t0", "unix\t9223372036854775807\t0",
                    "direction\t-1", "direction\t2", "status\t-1", "status\t2",
                    "source\t" + text_hex("relative/path"), "relative\t" + text_hex("/rooted.jpg")]:
        case("negative control", command, "err")

    result = subprocess.run([str(args.probe.resolve()), str(map_path.resolve())],
                            input="\n".join(requests) + "\n", encoding="utf-8", capture_output=True, timeout=120)
    if result.returncode:
        raise AssertionError(f"Rust probe failed ({result.returncode}): {result.stderr[:400]}")
    actual = result.stdout.splitlines()
    if len(actual) != len(expected):
        raise AssertionError("Rust returned an unexpected response count")
    for label, observed, wanted in zip(labels, actual, expected, strict=True):
        if observed != wanted:
            raise AssertionError(f"Rust/C# mismatch: {label}; lengths {len(observed)} != {len(wanted)}")

    # Keep expected data intact while deliberately changing only the map loaded
    # by Rust. This must produce a detected disagreement, not a self-confirming test.
    with tempfile.TemporaryDirectory(prefix="ifw-legacy-negative-") as temporary:
        wrong = Path(temporary) / "wrong-map.tsv"
        wrong.write_text(map_path.read_text(encoding="utf-8").replace("000061\t000041\n", "000061\t000042\n"), encoding="utf-8")
        result = subprocess.run([str(args.probe.resolve()), str(wrong)], input="uppercase\t0061\n",
                                encoding="utf-8", capture_output=True, timeout=10)
        if result.returncode or result.stdout.strip() != "ok\t0042":
            raise AssertionError("negative mapping control was not distinguishable")
        wrong.write_text("IFW-INVARIANT-UPPERCASE-V1\n000061\t000041\n000061\t000042\n", encoding="utf-8")
        invalid = subprocess.run([str(args.probe.resolve()), str(wrong)], input="", encoding="utf-8", capture_output=True, timeout=10)
        if invalid.returncode == 0:
            raise AssertionError("duplicate mapping was accepted")

    unicode_comparison = None
    if args.unicode_data:
        unicode_raw = args.unicode_data.read_bytes()
        unicode_map = {}
        for line in unicode_raw.decode("utf-8").splitlines():
            columns = line.split(";")
            if columns[12]:
                unicode_map[int(columns[0], 16)] = int(columns[12], 16)
        differences = [{"Scalar": f"{scalar:06X}", "DotNet": f"{mapping.get(scalar, scalar):06X}",
                        "UnicodeData": f"{unicode_map.get(scalar, scalar):06X}"}
                       for scalar in sorted(mapping.keys() | unicode_map.keys())
                       if mapping.get(scalar, scalar) != unicode_map.get(scalar, scalar)]
        unicode_comparison = {"sha256": hashlib.sha256(unicode_raw).hexdigest(), "differences": differences}

    report = {
        "format": "ifw-rw02-legacy-probe-v1", "native_os": native, "native_arch": expected_arch,
        "runtime_reference": manifest["Runtime"], "passed_requests": len(requests), "categories": categories,
        "exhaustive_scalars": manifest["ScannedScalars"], "changed_scalar_mappings": len(mapping),
        "casing_map_sha256": manifest["Payloads"]["invariant-uppercase.tsv"],
        "probe_sha256": hashlib.sha256(args.probe.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scalar_manifest_sha256": hashlib.sha256((args.scalar_reference / "manifest.json").read_bytes()).hexdigest(),
        "legacy_manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "legacy_assertions_recorded": legacy_manifest["Assertions"], "table_rows_decoded_by_python": table_counts,
        "unequal_map_control_detected": True, "invalid_map_control_rejected": True,
        "unicode_data_comparison": unicode_comparison,
        "unproven": ["Rust SQLite IO", "Rust YAML and whole repair-JSON parsing", "SHA-256 identities",
                     "cross-target equality of complete casing tables", "Windows device/verbatim paths",
                     "migration and data-write recovery", "filesystem authorization"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Rust/C# scalar probe passed: {len(requests)} requests, {manifest['ScannedScalars']} Unicode scalars; {native}-{expected_arch}.")


if __name__ == "__main__":
    main()
