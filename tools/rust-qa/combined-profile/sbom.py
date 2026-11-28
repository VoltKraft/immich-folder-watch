"""Emit SPDX 2.3 from a verified combined-profile native build. Requires Python 3.11+ and Git."""
import argparse
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import cache
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import tomllib
from zipfile import BadZipFile, ZipFile

from units import compiler_units
import source_notices

ROOT = Path(__file__).resolve().parents[3]
PROFILE = "tools/rust-qa/combined-profile"
BINARY = "SPDXRef-NativeExecutable"
DOCUMENT = "SPDXRef-DOCUMENT"
UNKNOWN = "NOASSERTION"

# These normalized bodies match the listed SPDX templates; each XML retains its original attribution.
PROTOCOL_GRANTS = {
    "abb345952b84d7de8c42b680f36772e3cfdc7551e2ea6e2a10c693e4c3964c98": "MIT",
    "56959050891f7b737ac4e803051170c7197f02df73d80bd9a78d968e305bf558": "MIT",
    "f260dfe37bd3edccc3da1d85943ace2e1e01970086da4a3281bb5032f6ee6bd4": "HPND-sell-variant",
}
ADDITIONAL_GRANTS = {
    "rust/audit/notices/tiny-skia-BSD": ("6d41e05f1d54fe726997cb0334ec539f1dff50600b1d5d90462ec2b392770ced", "BSD-3-Clause"),
    "rust/audit/notices/accesskit-Chromium-BSD": ("845022e0c1db1abb41a6ba4cd3c4b674ec290f3359d9d3c78ae558d4c0ed9308", "BSD-3-Clause"),
    "rust/audit/notices/SPIRV-Headers": ("ea43b1de38a6f90c488800d66dec1ed671e68cda530266bc96951fb5b6307613", "MIT-Khronos-old"),
    "tools/rust-qa/legacy/licenses/Unicode-LICENSE.txt": ("e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96", "Unicode-3.0"),
}

# The native inventory stores the digest of this package-specific redistribution notice.
# Retain its exact bytes for offline SPDX extraction and authenticate them against that inventory.
GRANIT_NOTICE = """Inherited license notices:

Code up to and including commit `da52a68615f2ecdd6b7e4567019f280c433c1521` is licensed by Chen Yuheng under either of:
  - [Apache License, Version 2.0](.licenses/ChenYuheng-Apache) (http://www.apache.org/licenses/LICENSE-2.0)
  - [MIT License](.licenses/ChenYuheng-MIT) (http://opensource.org/licenses/MIT)

Code modifications starting with commit `1d71a23b151dcc12b289d0f06d8207dd9c764216` (included) are licensed by Ethiraric under either of:
  - [Apache License, Version 2.0](.licenses/Ethiraric-Apache) (http://www.apache.org/licenses/LICENSE-2.0)
  - [MIT License](.licenses/Ethiraric-MIT) (http://opensource.org/licenses/MIT)

granit-parser modification notice:

Modifications after commit `825edf857426d034954523fed19599635cbb5043` are Copyright (c) 2026 Bourumir Wyngs and licensed under MIT OR Apache-2.0.

Redistributions of this Work must include all inherited and new license notices, including the notices for Chen Yuheng, Ethiraric, and Bourumir Wyngs.
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def require_hash(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "Invalid SHA-256")
    return value


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


@cache
def blob(revision, path):
    require(re.fullmatch(r"[a-zA-Z0-9_./-]+", path) and
            all(part not in ("", ".", "..") for part in path.split("/")), f"Invalid source path {path}")
    return git("cat-file", "blob", f"{revision}:{path}")


def source_matches(data, expected, windows, path):
    if sha(data) == expected:
        return
    # A native Windows Git checkout can materialize text sources with CRLF.
    require(windows and b"\0" not in data and sha(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")) == expected,
            f"Source checksum differs from the Git revision: {path}")


def read_run(location, target, archive_hash):
    with ExitStack() as stack:
        if location.is_dir():
            require(archive_hash is None, "--archive-sha256 applies to ZIP inputs")
            def read(name):
                return (location / name).read_bytes()
        else:
            require(archive_hash is not None, "ZIP input requires an independently verified --archive-sha256")
            with location.open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == require_hash(archive_hash),
                        "Desktop archive checksum mismatch")
            archive = stack.enter_context(ZipFile(location))
            prefix = f"combined-profile/runs/{target}/"
            names = [name for name in archive.namelist() if name.startswith(prefix)]
            require(len(names) == len(set(names)) and prefix + "result.json" in names, "Missing or ambiguous target run")
            def read(name):
                return archive.read(prefix + name)
        raw = read("result.json")
        receipt = json.loads(raw)
        keep = {"profile.json", "inventory.json", "source-trees.json", "compiler-units.json", "smoke.json",
                "build.log", target + ".json", target + ".tree"}
        if "accesskitUnix" in receipt["native"]:
            keep.add("accesskit-unix.d")
        files = {}
        for name, expected in receipt["outputs"].items():
            require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in (".", "..", "result.json"),
                    f"Invalid output name {name}")
            data = read(name)
            require(sha(data) == require_hash(expected), f"Output checksum mismatch: {name}")
            if name in keep:
                files[name] = data
        require(files.keys() == keep, "Missing a required native build output")
        return receipt, sha(raw), files


def graph_edges(tree, features):
    """Read Cargo's ASCII normal/build tree. Build sections belong to the node at their indentation."""
    stack, edges, seen = [], set(), set()
    root = None
    for line in tree.splitlines():
        match = re.fullmatch(r"((?:\|   |    )*)(\|-- |`-- )?(.+)", line)
        require(match is not None, "Malformed Cargo tree")
        indent, connector, body = match.groups()
        depth = len(indent) // 4 + bool(connector)
        if body == "[build-dependencies]":
            require(not connector and depth < len(stack), "Unexpected Cargo build section")
            stack[depth][1] = True
            continue
        name, _, groups = body.removesuffix(" (*)").partition("|")
        name = name.removesuffix(" (proc-macro)")
        require("|" in body and name in features and sorted(filter(None, groups.split(","))) in features[name]
                and depth <= len(stack), "Tree differs from reviewed compiler features")
        if depth:
            parent, is_build = stack[depth - 1]
            edges.add((name, "BUILD_DEPENDENCY_OF", parent) if is_build else (parent, "DEPENDS_ON", name))
        else:
            require(root is None, "Multiple Cargo tree roots")
            root = name
        stack[depth:] = [[name, False]]
        seen.add(name)
    require(seen == features.keys(), "Missing Cargo tree packages")
    return root, edges


def verify(receipt, files, revision, target):
    require(receipt["passed"] is True and receipt["revision"] == revision, "Expected a passed build at requested revision")
    native, outputs = receipt["native"], receipt["outputs"]
    require(native["target"] == target and f"host: {target}" in receipt["rustc"], "Native compiler target mismatch")
    require_hash(native["binarySha256"])
    sources = receipt["sources"]
    required = {"rust/Cargo.toml", "rust/audit/gui-inputs.json", "rust/audit/gui-text-inputs.json",
                "tools/rust-qa/gui/src/fonts.rs", "tools/rust-qa/storage/inputs.json",
                PROFILE + "/review.json", PROFILE + "/Cargo.lock", PROFILE + "/Cargo.toml", PROFILE + "/src/main.rs"}
    require(required <= sources.keys(), "Incomplete Git source witness")
    for path, expected in sources.items():
        source_matches(blob(revision, path), require_hash(expected), "windows" in target, path)
    for field, file in [("buildLogSha256", "build.log"), ("linkedLibrariesSha256", "linked-libraries.txt"),
                        ("smokeSha256", "smoke.json"), ("clippyLogSha256", "clippy.log")]:
        require(native[field] == outputs[file], f"Native receipt mismatch: {file}")
    review = json.loads(blob(revision, PROFILE + "/review.json"))
    inventory = json.loads(files["inventory.json"])
    trees = json.loads(files["source-trees.json"])
    graph = json.loads(files[target + ".json"])
    features = graph["features"]
    require(json.loads(files["profile.json"]) == review and receipt["profileSha256"] == outputs["profile.json"]
            and receipt["lock"] == receipt["emptyLockReplaySha256"] == review["lockSha256"]
            == sources[PROFILE + "/Cargo.lock"], "Combined profile or lock differs from source review")
    require(sha(canonical(inventory).encode()) == review["inventorySha256"] and
            sha(canonical(trees).encode()) == review["allCompilerTreesSha256"], "Changed reviewed source inventory")
    summary = review["targets"][target]
    require(graph["summary"] == summary and outputs[target + ".tree"] == summary["treeSha256"] and
            sha(canonical(features).encode()) == summary["normalBuildFeatureSetsSha256"], "Changed target graph")
    for path, expected in inventory["originalNoticeFiles"].items():
        require(sha(blob(revision, path)) == expected, f"Supplemental notice changed: {path}")
    for row in inventory["packages"]:
        if "registryCorrection" not in row:
            continue
        import unix_adapter
        require(row["name"] + "-" + row["version"] == unix_adapter.CRATE, "Unexpected registry correction")
        correction = row["registryCorrection"]
        paths = {p.relative_to(ROOT).as_posix() for p in unix_adapter.reconstruction_inputs()}
        require(set(correction["inputs"]) == paths and
                all(sources.get(path) == value for path, value in correction["inputs"].items()),
                "Missing the patch, source review or reconstructor in the compiler witness")
        tree = trees[unix_adapter.CRATE]
        require(tree == row["compilerTree"] and tree["originalSha256"] == row["archiveSha256"],
                "Changed AccessKit Unix compiler tree")
        key = row["name"] + " v" + row["version"]
        if "linux" in target:
            proof = native["accesskitUnix"]
            library = unix_adapter.compiled_library(files["build.log"].decode(), target)
            modules = {item["path"]: item["after"] for item in tree["transformations"]}
            require(key in features and str(library) == proof["library"] and modules == proof["modules"]
                    and len(modules) == 2 and proof["rlibSha256"] == outputs["accesskit-unix.rlib"]
                    and proof["depfileSha256"] == outputs["accesskit-unix.d"], "Native Unix adapter evidence differs")
            unix_adapter.check_depfile(files["accesskit-unix.d"].decode(), library, modules)
        else:
            require(key not in features and "accesskitUnix" not in native, "Unix adapter in a Windows build")
    observed = json.loads(files["compiler-units.json"])
    count = native["compilerUnits"]
    # Reuse the native verifier on the retained Cargo machine messages, including host/target and link directives.
    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        for name in ("build.log", target + ".json"):
            (scratch / name).write_bytes(files[name])
        require(compiler_units(scratch, target) == count and
                json.loads((scratch / "compiler-units.json").read_bytes()) == observed,
                "Compiler unit evidence differs from the native Cargo build log")
    require(observed["nativeTarget"] == target and count["reportSha256"] == outputs["compiler-units.json"]
            and count["packages"] == observed["compiledPackages"] == summary["packages"] == len(features)
            and count["units"] == len(observed["units"]), "Compiler unit receipt mismatch")
    units = defaultdict(list)
    for unit in observed["units"]:
        require(unit["compiledFor"] and set(unit["compiledFor"]) <= {"host", target} and unit["kinds"],
                "Unit has no valid compilation target")
        units[unit["package"]].append(unit)
    require({key: sorted({tuple(u["features"]) for u in group}) for key, group in units.items()} ==
            {key: sorted(map(tuple, groups)) for key, groups in features.items()}, "Compiled feature sets differ")
    require(observed["nativeBuildDirectives"].keys() <= units.keys(), "Unknown native directive source")
    root, edges = graph_edges(files[target + ".tree"].decode(), features)
    return inventory, observed["nativeBuildDirectives"], units, root, edges


def ident(kind, name):
    # Keep Cargo's underscore, plus and hyphen distinct in SPDX's restricted identifier alphabet.
    return "SPDXRef-" + kind + "-" + re.sub(r"[^A-Za-z0-9.]", lambda m: f"-{ord(m[0]):02x}", name)


def package(identifier, name, purpose, declared=UNKNOWN, concluded=UNKNOWN, url=UNKNOWN, checksum=None):
    entry = {"SPDXID": identifier, "name": name, "primaryPackagePurpose": purpose, "filesAnalyzed": False,
             "downloadLocation": url, "licenseDeclared": declared, "licenseConcluded": concluded,
             "copyrightText": UNKNOWN}
    if checksum:
        entry["checksums"] = [{"algorithm": "SHA256", "checksumValue": require_hash(checksum)}]
    return entry


def extract(extracted, name, grant):
    license_id = "LicenseRef-" + name + "-" + sha(grant.encode())
    extracted[license_id] = {"licenseId": license_id, "extractedText": grant, "name": name}
    return license_id


def protocol_package(parent, path, info, row, extracted, reuse=None):
    grant = info["copyright"]
    licenses = info["licenseIds"]
    start = re.search(r"Permission (?:is hereby|to use)", grant, re.IGNORECASE)
    if licenses:
        require(len(licenses) == 1, f"Review the combination of XML license identifiers for {path}")
        license_id = licenses[0]
    elif grant:
        body = " ".join(grant[start.start():].lower().split()) if start else ""
        license_id = PROTOCOL_GRANTS.get(sha(body.encode())) or extract(extracted, "Protocol", grant)
    else:
        notice = "rust/audit/notices/weston-1.5.0-COPYING"
        require(path == "plasma-wayland-protocols/src/protocols/fullscreen-shell.xml" and
                info["sha256"] == "ed7ded0629f9f05adb9326a378258255d623522b85ec4d47c787742da7fd5c7c" and
                notice in row["supplementalNotices"], "Unreviewed protocol without an embedded grant")
        license_id = "HPND-sell-variant"
    entry = package(ident("Protocol", parent + "/" + path), path, "SOURCE", license_id if grant else UNKNOWN,
                    license_id, checksum=info["sha256"])
    entry["sourceInfo"] = "Retained XML input in the reviewed Cargo source tree."
    if grant:
        attribution = grant[:start.start()] if start else grant.split("SPDX-License-Identifier:", 1)[0]
        if attribution.strip():
            entry["copyrightText"] = attribution.strip()
    if not grant:
        entry["licenseComments"] = "The reviewed Weston 1.5.0 main COPYING grant covers this historical XML."
    if licenses and reuse is not None:
        require(license_id in reuse, f"Missing full REUSE license for {path}")
        entry["licenseComments"] = "Full original text: " + canonical(reuse[license_id])
    if row.get("coreProtocolGenerator", {}).get("xml") == path:
        entry["sourceInfo"] += " Generated by the compiled client library: " + canonical(row["coreProtocolGenerator"])
    return entry


def external_package(key, row, extracted):
    tree = row["compilerTree"]
    private = bool(row.get("reconstructedSource") or tree.get("transformations"))
    declared = {"Apache-2.0/MIT": "Apache-2.0 OR MIT", "MIT/Apache-2.0": "MIT OR Apache-2.0"}.get(
        row["declared"], row["declared"])
    notices = {**row["notices"], **row["supplementalNotices"]}
    # These source-level additions are identified in the existing GUI source review.
    additions = set()
    for path in notices.keys() & ADDITIONAL_GRANTS.keys():
        expected, license_id = ADDITIONAL_GRANTS[path]
        require(notices[path] == expected, f"Changed supplemental license requires review: {path}")
        additions.add(license_id)
    if row["name"] == "granit-parser":
        require(sha(GRANIT_NOTICE.encode()) == notices["LICENSE"], "Changed inherited granit-parser conditions")
        additions.add(extract(extracted, "GranitParserNotice", GRANIT_NOTICE))
    concluded = " AND ".join([row["selected"], *sorted(additions - set(row["selected"].split()))])
    # File-local notices can add conditions beyond the Cargo declaration. The package's explicit
    # inherited granit-parser grant has its own separately attributable SPDX source record below.
    if row.get("protocols") or row.get("sourceAttributions") or row["name"] == "libsqlite3-sys":
        concluded = UNKNOWN
    url = row.get("originalCrate", f"https://static.crates.io/crates/{row['name']}/{row['name']}-{row['version']}.crate")
    entry = package(ident("Cargo", key), row["name"], "SOURCE", declared, concluded,
                    UNKNOWN if private else url, None if private else row["archiveSha256"])
    entry["versionInfo"] = row["version"]
    entry["licenseComments"] = (f"Cargo declaration: {row['declared']}. Reviewed top-level selection: {row['selected']}. "
                                "Original and supplemental notice hashes: " + canonical(notices))
    input_data = {"upstreamArchive": url, "upstreamArchiveSha256": row["archiveSha256"], "compilerTree": tree,
                  "retainedNativeInputs": row["native"], "retainedShaderInputs": row["shaders"],
                  "inventoryRowSha256": sha(canonical(row).encode())}
    if "reconstructedSource" in row:
        input_data["reconstruction"] = row["reconstructedSource"]
    if "registryCorrection" in row:
        input_data["registryCorrection"] = row["registryCorrection"]
    if row.get("sourceAttributions"):
        input_data["sourceAttributions"] = row["sourceAttributions"]
        entry["licenseComments"] += (" Source-local notices are keyed by original file hash and byte range. "
                                     "The conservative source set includes target-conditional, generator and test inputs.")
    if "ringSourceInputs" in row:
        input_data["ringSourceInputs"] = row["ringSourceInputs"]
    entry["sourceInfo"] = canonical(input_data)
    return entry


def first_party(revision, witnesses):
    workspace = tomllib.loads(blob(revision, "rust/Cargo.toml").decode())["workspace"]["package"]
    result = {}
    for path in witnesses:
        if path != PROFILE + "/Cargo.toml" and not re.fullmatch(r"rust/crates/[^/]+/Cargo.toml", path):
            continue
        fields = tomllib.loads(blob(revision, path).decode())["package"]
        def field(name):
            return workspace[name] if fields[name] == {"workspace": True} else fields[name]
        name, version, license_id = fields["name"], field("version"), field("license")
        key = name + " v" + version
        entry = package(ident("Cargo", key), name, "SOURCE", license_id, license_id)
        entry.update(versionInfo=version, sourceInfo=f"Git {revision}, {path}, witnessed SHA-256 {witnesses[path]}")
        result[key] = entry
    return result


def fonts(revision, inventory):
    # The current runner retains the binary digest and drawing smoke, not a copy of the executable.
    # Require the actual reviewed embedding code before assigning DATA_FILE_OF to its five faces.
    main = blob(revision, PROFILE + "/src/main.rs")
    start = main.index(b"fn draw(")
    draw = main[start:main.index(b"\n}", start) + 2]
    require(sha(draw) == "a4fcd095ab318b11adfe0c02b109b2f09f60eb805f15c7d520b983c0b7f32acf" and
            sha(blob(revision, "tools/rust-qa/gui/src/fonts.rs")) ==
            "7ec6288fe311e1e3aef7da3eb2be9fd6286e1b856020f59497418b71bae18cf7",
            "Changed native font embedding requires review")
    spec = importlib.util.spec_from_file_location("font_coverage_inputs", ROOT / "tools/rust-qa/font-coverage/inputs.py")
    font_inputs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(font_inputs)
    meta = json.loads(blob(revision, "rust/audit/gui-text-inputs.json"))["fonts"]
    sources = json.loads(blob(revision, "rust/audit/gui-inputs.json"))["files"]
    base = {PurePosixPath(row["path"]).name: row for row in sources if row["path"].endswith((".otf", ".ttf"))}
    require(inventory["fonts"].keys() == base.keys() | meta.keys() and len(inventory["fonts"]) == 5,
            "Font set differs from the two authenticated source manifests")
    for name, item in inventory["fonts"].items():
        facts = meta.get(name, base.get(name))
        require(item["sha256"] == facts["sha256"] and item["source"] == facts.get("url", facts.get("source")),
                f"Font source differs for {name}")
        notice = "rust/assets/fonts/" + facts.get("notice", "OFL-1.1.txt")
        entry = package(ident("Font", name), name, "FILE", "OFL-1.1", "OFL-1.1", item["source"], item["sha256"])
        entry["packageFileName"] = name
        entry["licenseComments"] = f"{notice}, SHA-256 {inventory['originalNoticeFiles'][notice]}"
        if name in meta:
            entry["versionInfo"] = facts["version"]
            entry["copyrightText"] = "\n".join(facts["copyright"])
            entry["attributionTexts"] = facts["trademark"]
        else:
            data = blob(revision, "rust/" + facts["path"])
            require(sha(data) == item["sha256"], f"Font bytes differ for {name}")
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / name
                path.write_bytes(data)
                names = font_inputs.font_names(path)
            entry["copyrightText"] = "\n".join(names["0"])
            entry["versionInfo"] = "\n".join(names["5"])
            entry["attributionTexts"] = names["7"]
        yield entry


def assemble(receipt, result_hash, files, revision, target, supplemental=None):
    inventory, directives, units, root, cargo_edges = verify(receipt, files, revision, target)
    inventory = source_notices.qualified(inventory, supplemental)
    reuse = source_notices.protocol_license_texts(inventory, units)
    checked = {p["name"] + " v" + p["version"]: p for p in inventory["packages"]}
    local = first_party(revision, receipt["sources"])
    require(local.keys() <= units.keys() and root in local, "Incomplete first-party source manifest set")
    entries, extracted, edges = [], {}, set()
    for key, compiled in sorted(units.items()):
        if key in local:
            entry = local[key]
        else:
            row = checked[key]
            entry = external_package(key, row, extracted)
            if "registryCorrection" in row:
                details = json.loads(entry["sourceInfo"])
                details["nativeCompiler"] = receipt["native"]["accesskitUnix"]
                entry["sourceInfo"] = canonical(details)
            for field, selection in (("ringTargets", "ringTargetSelection"), ("compressionSourceByTarget", "compressionSource")):
                if field in row:
                    details = json.loads(entry["sourceInfo"])
                    details[selection] = row[field][target]
                    entry["sourceInfo"] = canonical(details)
            if row["name"] == "granit-parser" and entry["licenseConcluded"] == UNKNOWN:
                custom = extract(extracted, "GranitParserNotice", GRANIT_NOTICE)
                inherited = package(ident("Notice", key + "/LICENSE"), "granit-parser inherited LICENSE", "SOURCE",
                                    custom, custom, checksum=row["notices"]["LICENSE"])
                inherited["sourceInfo"] = "Original package LICENSE links to the separate .licenses/ grant texts."
                entries.append(inherited)
                edges.add((entry["SPDXID"], "CONTAINS", inherited["SPDXID"]))
            for path, info in row.get("protocols", {}).items():
                xml = protocol_package(key, path, info, row, extracted, reuse)
                entries.append(xml)
                edges.add((entry["SPDXID"], "CONTAINS", xml["SPDXID"]))
        entry["comment"] = canonical({"compiledUnits": [{k: v for k, v in u.items() if k != "package"} for u in compiled],
                                      "nativeLinkDirectives": directives.get(key, [])})
        entries.append(entry)
    for source, relationship, dest in cargo_edges:
        if relationship == "DEPENDS_ON" and all(u["compiledFor"] == ["host"] for u in units[dest]):
            source, relationship, dest = dest, "BUILD_DEPENDENCY_OF", source
        edges.add((ident("Cargo", source), relationship, ident("Cargo", dest)))
    binary_name, = (u["targetName"] for u in units[root] if "bin" in u["kinds"] and target in u["compiledFor"])
    binary = package(BINARY, binary_name + (".exe" if "windows" in target else ""),
                     "APPLICATION", checksum=receipt["native"]["binarySha256"])
    binary["sourceInfo"] = (f"Native {target} development executable measured by the build runner; "
                            f"result.json SHA-256 {result_hash}. Linked-library observations: "
                            f"linked-libraries.txt SHA-256 {receipt['outputs']['linked-libraries.txt']}.")
    if "windows" in target:
        binary["sourceInfo"] += (" The PE dependency listing identifies imported names. Loaded DLL file bytes, "
                                 "late-loaded modules and published import-library reconstruction have separate evidence.")
    entries.append(binary)
    edges.add((BINARY, "GENERATED_FROM", ident("Cargo", root)))
    smoke = json.loads(files["smoke.json"])
    require(smoke["tessellatedPrimitives"] > 0, "Missing native font drawing smoke")
    for font in fonts(revision, inventory):
        entries.append(font)
        edges.add((font["SPDXID"], "DATA_FILE_OF", BINARY))
    sqlite_key, = (key for key in units if key.startswith("libsqlite3-sys v"))
    pin = json.loads(blob(revision, "tools/rust-qa/storage/inputs.json"))["sqlite"]
    checksum = checked[sqlite_key]["native"]["sqlite3/sqlite3.c"]
    require(pin["source_id"] == smoke["sqliteSourceId"] and
            "static=sqlite3" in directives[sqlite_key] and
            checksum == "0c657666d819f261cc4007526ad57e1669de9949df7a8ea847aa284a2bf0ee52",
            "SQLite source, license or static linkage requires review")
    sqlite = package("SPDXRef-SQLiteSource", "SQLite amalgamation", "SOURCE", "blessing", "blessing", checksum=checksum)
    sqlite.update(versionInfo=pin["version"], packageFileName="sqlite3/sqlite3.c",
                  sourceInfo=f"sqlite_source_id(): {pin['source_id']}. Cargo emitted static=sqlite3.",
                  licenseComments="SQLite's public-domain dedication and blessing apply to the original amalgamation.")
    entries.append(sqlite)
    edges.update({(ident("Cargo", sqlite_key), "CONTAINS", sqlite["SPDXID"]), (BINARY, "GENERATED_FROM", sqlite["SPDXID"])})
    epoch = int(git("show", "-s", "--format=%ct", revision))
    date = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    generator = {p: sha((ROOT / p).read_bytes().replace(b"\r\n", b"\n")) for p in
                 [PROFILE + "/sbom.py", PROFILE + "/units.py", PROFILE + "/source_notices.py", PROFILE + "/unix_adapter.py",
                  PROFILE + "/notice-upgrade.json", "tools/rust-qa/audit-graph.py", "tools/rust-qa/font-coverage/inputs.py"]}
    doc = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": DOCUMENT,
           "name": f"Immich Folder Watch combined development profile {target} at {revision}",
           "creationInfo": {"created": date, "creators": ["Tool: ifw-combined-profile-sbom"],
                            "comment": ("Reproducible timestamp uses the native source commit time. Generator, compiler "
                                        "unit verifier and sfnt reader SHA-256 (LF): " + canonical(generator))},
           "documentDescribes": [BINARY],
           "comment": (f"Git {revision}, target {target}. SHA-256 of native evidence: " +
                       canonical({k: receipt["outputs"][k] for k in ["inventory.json", "compiler-units.json",
                                 "source-trees.json", "profile.json", target + ".tree", target + ".json"]}) +
                       ". Qualified source inventory SHA-256 (canonical JSON): " + sha(canonical(inventory).encode()) +
                       ". Cargo edges describe compilation. Host-only units and retained native/shader source paths "
                       "have separate evidence from the executable and its embedded fonts. System redistribution, "
                       "installed packages and binary license conclusions require separate evidence."),
           "packages": sorted(entries, key=lambda p: p["SPDXID"]),
           "relationships": [{"spdxElementId": a, "relationshipType": rel, "relatedSpdxElement": b}
                             for a, rel, b in sorted(edges)]}
    if extracted:
        doc["hasExtractedLicensingInfos"] = [extracted[k] for k in sorted(extracted)]
    doc["documentNamespace"] = "https://github.com/VoltKraft/immich-folder-watch/spdx/" + sha(canonical(doc).encode())
    validate_references(doc)
    return doc


def validate_references(doc):
    ids = {p["SPDXID"] for p in doc["packages"]}
    require(len(ids) == len(doc["packages"]) and ids.issuperset(doc["documentDescribes"]), "Duplicate or missing SPDX ID")
    for r in doc["relationships"]:
        require(r["spdxElementId"] in ids and r["relatedSpdxElement"] in ids, "Dangling SPDX relationship")
    licenses = {p["licenseId"] for p in doc.get("hasExtractedLicensingInfos", [])}
    for p in doc.get("hasExtractedLicensingInfos", []):
        require(p["licenseId"] == "LicenseRef-" + p["name"] + "-" + sha(p["extractedText"].encode()),
                "Changed extracted grant")
    used = {ref for p in doc["packages"] for field in ["licenseDeclared", "licenseConcluded"]
            for ref in re.findall(r"LicenseRef-[A-Za-z0-9.-]+", p[field])}
    require(used == licenses, "Dangling or unreferenced extracted license")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--revision", required=True, help="Full Git commit of the native build")
    parser.add_argument("--archive-sha256", help="Published digest of the complete desktop ZIP")
    parser.add_argument("--source-inventory", type=Path, help="Pinned supplemental source inventory for historical receipts")
    args = parser.parse_args()
    require(re.fullmatch("[0-9a-f]{40}", args.revision), "Supply a full Git source revision")
    review = json.loads(blob(args.revision, PROFILE + "/review.json"))
    require(args.target in review["targets"], "Unsupported native target")
    receipt, result_hash, files = read_run(args.input, args.target, args.archive_sha256)
    destination = args.output.resolve()
    require(destination != args.input.resolve() and not (destination.parent == args.input.resolve() and
            destination.name in {*receipt["outputs"], "result.json"}), "Output would overwrite native evidence")
    document = assemble(receipt, result_hash, files, args.revision, args.target, args.source_inventory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        complete = Path(scratch) / "document.spdx.json"
        complete.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        complete.replace(destination)
    print(args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, BadZipFile) as error:
        sys.exit(str(error))
