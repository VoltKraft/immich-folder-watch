"""Reproduce .NET 10.0.12 managed globalization-invariant uppercase from source."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import struct
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "legacy"))
from casing_profiles import PROFILES, match_reference, require_notice, simple_uppercase

VMR = "95017c711e6afc1085133d440e42b4bd78155701"
RUNTIME = "4271d88e0aebf3d04f188f1334c2220d80555ef6"
CORE = f"https://raw.githubusercontent.com/dotnet/runtime/{RUNTIME}/src/libraries/System.Private.CoreLib"
GLOBALIZATION = f"{CORE}/src/System/Globalization"
GENERATOR = f"{CORE}/Tools/GenUnicodeProp"
SOURCES = {
    "UnicodeData.txt": ("https://www.unicode.org/Public/16.0.0/ucd/UnicodeData.txt",
                        "ff58e5823bd095166564a006e47d111130813dcf8bf234ef79fa51a870edb48f"),
    "source-manifest.json": (f"https://raw.githubusercontent.com/dotnet/dotnet/{VMR}/src/source-manifest.json",
                             "f3117c464da657625805aab94ff4d285c213dafe04049559b419c68a30ef55bd"),
    "gen-GenUnicodeProp.csproj": (f"{GENERATOR}/GenUnicodeProp.csproj",
                                  "1d3057bba07cc5defe6173d4f0cb8a9c7b309c8380f29f41f07f169017ef9afd"),
    "gen-CategoryCasingInfo.cs": (f"{GENERATOR}/CategoryCasingInfo.cs",
                                  "f6196a95614742c2b3f64b3ccb0bb4c87c009584aedee98b11bce31b99935518"),
    "TextInfo.cs": (f"{GLOBALIZATION}/TextInfo.cs", "b7291cef3ef1990f0d42d601e1245f13eed3f10378a2360bf7d8395f938ace30"),
    "InvariantModeCasing.cs": (f"{GLOBALIZATION}/InvariantModeCasing.cs",
                               "c15c9b5c544ead29477e597aa7132938dd0ec0fd10de22323fc08f689dcff2c8"),
    "SurrogateCasing.cs": (f"{GLOBALIZATION}/SurrogateCasing.cs",
                           "0554d216fafa1e0faa414ed553e03966ddb0e6bada725359ebc1df33875d6ab8"),
    "CharUnicodeInfo.cs": (f"{GLOBALIZATION}/CharUnicodeInfo.cs",
                           "421b42928c7feb79870bc238487893a3d75e32620c63e0aa33190b27cf96d629"),
    "CharUnicodeInfoData.cs": (f"{GLOBALIZATION}/CharUnicodeInfoData.cs",
                               "f4d6e35f4102b5855dd6d0f22b5a966fd9fc811b1497895f003bb07f454c7062"),
}
MANAGED = "51e3c6f44c782e8e99c355b504f32900da56c9e4a500da83a15a2f807b95b6e4"
UNFILTERED = "31d8b2a3b6bf02485b5ecb6f1d5d820ca4083594dd7c0d6d08905b2ef259cb54"
DIFFERENTIAL = "e2251669d767e6269fe594a6d101af2505df1751075b782bdb91ec70268eb9a5"
TABLE = HERE / "managed-invariant-10.0.12.tsv"
HEADER = b"IFW-INVARIANT-UPPERCASE-V1\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_source(name, data):
    require(sha(data) == SOURCES[name][1], f"Input differs from the published source for {name}")
    return data


def fetch(directory):
    require(not directory.exists(), "The source directory must be fresh")
    inputs = {}
    for name, (url, _) in SOURCES.items():
        with urllib.request.urlopen(url, timeout=45) as response:
            inputs[name] = check_source(name, response.read(3_000_000))
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, data in inputs.items():
        (directory / name).write_bytes(data)


def encode(mapping):
    return HEADER + "".join(f"{scalar:06X}\t{upper:06X}\n" for scalar, upper in sorted(mapping.items())).encode("ascii")


def decode(table):
    require(table.startswith(HEADER), "Invalid sparse table header")
    return {int(a, 16): int(b, 16) for a, b in (line.split(b"\t") for line in table[len(HEADER):].splitlines())}


def managed_from_ucd(data):
    ucd = simple_uppercase(check_source("UnicodeData.txt", data))
    require(len(ucd) == 1477 and sha(encode(ucd)) == UNFILTERED, "Unexpected unfiltered UCD table")
    managed = ucd.copy()
    # These are the only two *upper* deltas among the three scalars excluded by GenUnicodeProp.
    require(0x0130 not in ucd and managed.pop(0x0131) == 0x0049 and managed.pop(0x017F) == 0x0053,
            "Unexpected UCD mappings for the runtime's three compatibility exceptions")
    return ucd, managed


def generated_bytes(source, name):
    declaration = rb"ReadOnlySpan<byte> " + name + rb" => // (\d+)\s*\[([^]]+)\]"
    match = re.search(declaration, source)
    require(match is not None, f"Missing generated array {name!r}")
    array = bytes(int(value, 16) for value in re.findall(rb"0x([0-9a-f]{2})", match[2]))
    require(len(array) == int(match[1]), f"Wrong generated array size for {name!r}")
    return array


def generated_mapping(source):
    check_source("CharUnicodeInfoData.cs", source)
    level1 = generated_bytes(source, b"CategoryCasingLevel1Index")
    level2 = [word for word, in struct.iter_unpack("<H", generated_bytes(source, b"CategoryCasingLevel2Index"))]
    level3 = generated_bytes(source, b"CategoryCasingLevel3Index")
    deltas = [word for word, in struct.iter_unpack("<H", generated_bytes(source, b"UppercaseValues"))]
    result = {}
    for scalar in itertools.chain(range(0xD800), range(0xE000, 0x110000)):
        block = level1[scalar >> 9]
        page = level2[block * 32 + ((scalar >> 4) & 31)]
        delta = deltas[level3[page * 16 + (scalar & 15)]]
        upper = (scalar & 0xFF0000) | ((scalar + delta) & 0xFFFF)
        if upper != scalar:
            result[scalar] = upper
    return result


def three_profiles():
    require_notice()
    older, current = PROFILES
    tables = {name: path.read_bytes() for name, path in
              (("icu15", older.table), ("managed16", TABLE), ("icu17", current.table))}
    require(match_reference(tables["icu15"]) == older and match_reference(tables["icu17"]) == current,
            "The qualified ICU inputs changed")
    require(sha(tables["managed16"]) == MANAGED and match_reference(tables["managed16"]) is None,
            "Expected the isolated managed reference outside the two-profile qualifier")
    return tables


def differences(maps):
    result = []
    for scalar in sorted(set().union(*maps)):
        values = [mapping.get(scalar, scalar) for mapping in maps]
        if len(set(values)) > 1:
            result.append([scalar, *values])
    return result


def inspect(directory):
    data = {name: check_source(name, (directory / name).read_bytes()) for name in SOURCES}
    repositories = json.loads(data["source-manifest.json"])["repositories"]
    require([r["commitSha"] for r in repositories if r["path"] == "runtime"] == [RUNTIME], "VMR runtime mismatch")
    ucd, managed = managed_from_ucd(data["UnicodeData.txt"])
    require(generated_mapping(data["CharUnicodeInfoData.cs"]) == managed, "CoreLib trie disagrees with UCD reconstruction")
    tables = three_profiles()
    require(encode(managed) == tables["managed16"], "Managed reference disagrees with the reconstructed bytes")
    cross = differences([decode(table) for table in tables.values()])
    encoded = "".join("\t".join(f"{value:06X}" for value in row) + "\n" for row in cross).encode("ascii")
    require(len(cross) == 56 and sha(encoded) == DIFFERENTIAL, "The three-profile differential changed")
    return {
        "format": "ifw-managed-invariant-source-comparison-v1", "runtimeVersion": "10.0.12",
        "vmrCommit": VMR, "runtimeCommit": RUNTIME, "sourceDigests": {name: sha(value) for name, value in data.items()},
        "scannedScalars": 0x110000 - 0x800, "ucdChangedScalars": len(ucd), "ucdTableSha256": UNFILTERED,
        "generatedChangedScalars": len(managed), "managedTableSha256": MANAGED,
        "ucdDifferences": differences([ucd, managed]), "profilesInColumnOrder": list(tables),
        "differentialColumns": ["scalar", *tables], "differential": cross, "differentialSha256": DIFFERENTIAL,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("fetch", help="Download checksum-pinned public inputs to a new directory")
    download.add_argument("directory", type=Path)
    comparison = commands.add_parser("compare", help="Verify complete, pre-staged inputs offline")
    comparison.add_argument("directory", type=Path)
    comparison.add_argument("--writers", nargs=3, type=Path, metavar=("ICU15", "MANAGED16", "ICU17"))
    comparison.add_argument("--readers", nargs=3, type=Path, metavar=("ICU15", "MANAGED16", "ICU17"))
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(args.directory)
        return
    if args.readers and not args.writers:
        parser.error("--readers requires the original --writers captures")
    result = inspect(args.directory)
    if args.writers:
        from store import verify_writers
        tables = three_profiles()
        result["storeObservations"] = verify_writers(args.writers, tables)
        if args.readers:
            from readers import verify_readers
            result["actualReaderComparisons"] = verify_readers(args.readers, args.writers, tables, result["storeObservations"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
