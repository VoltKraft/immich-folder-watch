"""Authenticate source-local attributions, original REUSE texts and generator inputs in assessed Cargo packages."""
from contextlib import contextmanager
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

from graphs import audit, fingerprint
from sources import local_caches, source_profile


ORIGINAL_INVENTORY = "244bec73e64cb8702e4c8a409c1d5f985160f173b11ea601a17c0ae027a456ca"
SOURCE_SUFFIXES = {".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".inc", ".inl", ".s", ".asm",
                   ".pl", ".py", ".sh", ".in", ".toml", ".wgsl", ".glsl", ".hlsl", ".metal", ".proto",
                   ".txt", ".cmake", ".bzl", ".json", ".yaml", ".yml", ".vert", ".frag", ".csv", ".tsv",
                   ".md", ".rst", ".js", ".def", ".tbl", ".patch", ".diff", ".ll", ".cu"}
RING_INPUT_SUFFIXES = {".rs", ".c", ".cc", ".h", ".inc", ".inl", ".s", ".asm", ".pl", ".o", ".obj"}
# A source line break and its comment delimiters may split a grant (ring's Poly1305 credit does).
MARKER = re.compile(rb"copyright|\xc2\xa9|SPDX-(?:License-Identifier|FileContributor)|all rights reserved|"
                    rb"permission[\s/*#;@]+(?:is hereby|to use)|redistribution and use|public[\s/*#;@]+domain|"
                    rb"licen[cs]ed under|(?:adapted|derived|ported|copied|translated) from|"
                    rb"Adobe Glyph List|origin:\s*(?:FreeBSD|OpenBSD|NetBSD|musl)", re.I)
COMMENTS = re.compile(rb"^[ \t]*/\*(?s:.*?)\*/[^\S\n]*(?:\n|$)|(?:^[ \t]*//[^\n]*(?:\n|$))+|"
                      rb"(?:^[ \t]*\#[^\n]*(?:\n|$))+|(?:^[ \t]*[;@][^\n]*(?:\n|$))+", re.M)
HEADING = re.compile(rb"^(#{1,6})[ \t]+([^\r\n]+)", re.M)
LEGAL_HEADING = re.compile(rb"\b(?:licen[cs]es?|licensing|attributions?|copyright|credits|legal)\b", re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def caches():
    return [source_profile.CACHE, *sorted(d for h in local_caches() for d in (h / "registry/cache").glob("*")
                                          if d.is_dir())]


@contextmanager
def original(prefix, digest, directories):
    name = prefix + ".crate"
    path = next((d / name for d in directories if (d / name).is_file()), None)
    if path is None:
        raise ValueError(f"Missing {name} in reviewed local Cargo caches")
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024 or sha(raw) != digest:
        raise ValueError(f"Original archive mismatch: {name}")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
        yield archive


def ranges(data, suffix=""):
    """Retain complete marked source comment blocks and exact lines of standalone source attributions."""
    if b"\0" in data:
        return []
    if suffix in {".md", ".rst"}:
        spans = set()
        headings = list(HEADING.finditer(data))
        for index, heading in enumerate(headings):
            if LEGAL_HEADING.search(heading[2]):
                end = next((other.start() for other in headings[index + 1:] if len(other[1]) <= len(heading[1])), len(data))
                spans.add((heading.start(), end))
        for paragraph in re.finditer(rb"(?m)(?:^[^\r\n][^\n]*(?:\n|$))+", data):
            if MARKER.search(paragraph[0]) and not any(a <= paragraph.start() < b for a, b in spans):
                spans.add(paragraph.span())
        return blocks(data, spans)
    if not MARKER.search(data):
        return []
    hints = iter(MARKER.finditer(data))
    hint = next(hints, None)
    spans = set()
    for block in COMMENTS.finditer(data):
        while hint and hint.start() < block.start():
            end = data.find(b"\n", hint.end())
            spans.add((data.rfind(b"\n", 0, hint.start()) + 1, len(data) if end < 0 else end + 1))
            hint = next(hints, None)
        if hint and hint.start() < block.end():
            spans.add(block.span())
            while hint and hint.start() < block.end():
                hint = next(hints, None)
        if not hint:
            break
    while hint:
        end = data.find(b"\n", hint.end())
        spans.add((data.rfind(b"\n", 0, hint.start()) + 1, len(data) if end < 0 else end + 1))
        hint = next(hints, None)
    return blocks(data, spans)


def blocks(data, spans):
    if any(b - a > 128 * 1024 for a, b in spans):
        raise ValueError("Oversized source notice requires individual review")
    return [{"start": a, "bytes": b - a, "sha256": sha(data[a:b])} for a, b in sorted(spans)]


def note_source(records, path, data):
    spans = ranges(data, PurePosixPath(path).suffix.lower())
    if spans:
        records[path] = {"sha256": sha(data), "ranges": spans}


def reconstructed_root(row):
    root = source_profile.SOURCES / row["name"]
    if source_profile.tree_info(root) != row["compilerTree"]:
        raise ValueError(f"Reconstructed compiler source differs: {row['name']}")
    return root


def ring_targets(build, inputs):
    """Follow the reviewed build.rs architecture table, perlasm naming and SHA-256 synthesis."""
    if sha(build) != "9d1928ffb1d8e15766c1c1b9ead73e4b81a21703dd25f7c27b87842a2e6e9cee":
        raise ValueError("Changed ring build recipe requires a new architecture review")
    code = build.decode()
    constants = dict(re.findall(r'const (SHA\d+_[A-Z0-9_]+): &str = "([^"]+)";', code))
    table = code.split("const RING_SRCS:", 1)[1].split("= &[", 1)[1].split("\n];", 1)[0]
    rows = re.findall(r'^    \(&\[([^\]]*)\], (.+)\),$', table, re.M)
    if len(rows) != table.count("(&["):
        raise ValueError("Unparsed ring source-table row")
    result = {}
    for target, arch, flavor in [("x86_64-unknown-linux-gnu", "X86_64", "elf"),
                                 ("x86_64-pc-windows-msvc", "X86_64", "nasm"),
                                 ("aarch64-unknown-linux-gnu", "AARCH64", "linux64"),
                                 ("aarch64-pc-windows-msvc", "AARCH64", "win64")]:
        paths = sorted(constants.get(item, item.strip('"')) for archs, item in rows
                       if not archs or arch in archs.split(", "))
        generated = {}
        for source in paths:
            if source not in inputs:
                raise ValueError(f"Missing ring source {source}")
            if not source.endswith(".pl"):
                continue
            stem = PurePosixPath(source).stem
            stems = [stem, stem.replace("sha512-", "sha256-")] if stem.startswith("sha512-") else [stem]
            for name in stems:
                base = "pregenerated/" + name + "-" + flavor
                outputs = [base + ".asm", base + ".o"] if flavor == "nasm" else [base + ".S"]
                for output in outputs:
                    if output not in inputs:
                        raise ValueError(f"Missing generated ring input {output}")
                    generated[output] = source
        result[target] = {"archSourceCandidates": paths, "generatedFrom": generated,
                          "buildScript": "build.rs", "testLibraryInput": "crypto/constant_time_test.c"}
    return result


def inspect_package(row, directories):
    records = {}
    if row.get("reconstructedSource"):
        root = reconstructed_root(row)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                note_source(records, path.relative_to(root).as_posix(), path.read_bytes())
    else:
        prefix = row["name"] + "-" + row["version"]
        build_recipe = None
        with original(prefix, row["archiveSha256"], directories) as archive:
            for member in archive:
                if not member.isfile():
                    continue
                path = PurePosixPath(member.name).relative_to(prefix)
                relative = path.as_posix()
                protocol = audit.protocol_input(row["name"], path)
                notice = audit.notice_path(path) or relative in row["notices"]
                source = path.suffix.lower() in SOURCE_SUFFIXES
                ring_input = row["name"] == "ring" and path.suffix.lower() in RING_INPUT_SUFFIXES
                if not any((protocol, notice, source, ring_input)):
                    continue
                with archive.extractfile(member) as stream:
                    data = stream.read()
                digest = sha(data)
                if notice and row["notices"].setdefault(relative, digest) != digest:
                    raise ValueError(f"Conflicting original notice: {prefix}/{relative}")
                if protocol:
                    item = audit.protocol_record(data)
                    if item and row.setdefault("protocols", {}).setdefault(relative, item) != item:
                        raise ValueError(f"Conflicting original protocol: {prefix}/{relative}")
                if ring_input:
                    row.setdefault("ringSourceInputs", {})[relative] = digest
                    if relative == "build.rs":
                        build_recipe = data
                if row["name"] == "wayland-client" and relative == "src/lib.rs":
                    macros = ["generate_interfaces", "generate_client_code"]
                    if any(data.count(f'wayland_scanner::{call}!("wayland.xml")'.encode()) != 1 for call in macros):
                        raise ValueError("Changed core Wayland protocol generation requires review")
                    row["coreProtocolGenerator"] = {"path": relative, "sha256": digest, "xml": "wayland.xml",
                                                    "macros": macros}
                # base64's reconstructed README removes promotional material. Publish its two
                # authenticated license files and never take excerpts of that unfiltered original.
                transformed = row["name"] == "base64" and relative == "README.md"
                if source and not (protocol or notice or transformed):
                    note_source(records, relative, data)
        if row["name"] == "ring":
            row["ringTargets"] = ring_targets(build_recipe, row["ringSourceInputs"])
    if records:
        row["sourceAttributions"] = records


def complete_inventory(inventory, directories):
    for row in inventory["packages"]:
        inspect_package(row, directories)
    inventory["sourceNoticeFormat"] = 2
    return inventory


def qualified(inventory, supplemental=None):
    """A historical native receipt remains immutable. Authenticate its supplemental review separately."""
    if inventory.get("sourceNoticeFormat") == 2:
        if supplemental is not None:
            raise ValueError("Native evidence already contains the source attribution inventory")
        return inventory
    if fingerprint(inventory) != ORIGINAL_INVENTORY:
        raise ValueError("Unreviewed historical source inventory")
    result = (complete_inventory(copy.deepcopy(inventory), caches()) if supplemental is None
              else json.loads(supplemental.read_bytes()))
    review = json.loads((Path(__file__).parent / "notice-upgrade.json").read_bytes())
    if review != {"nativeInventorySha256": ORIGINAL_INVENTORY, "qualifiedInventorySha256": fingerprint(result)}:
        raise ValueError("Supplemental source attribution inventory differs from review")
    return result


def excerpt_members(member, data):
    if sha(data) != member["sha256"]:
        raise ValueError("Attribution source checksum mismatch")
    files = {}
    for span in member["ranges"]:
        start, length = span["start"], span["bytes"]
        if not (0 <= start < len(data) and 0 < length <= len(data) - start):
            raise ValueError("Invalid attribution byte range")
        block = data[start:start + length]
        if sha(block) != span["sha256"]:
            raise ValueError("Attribution text checksum mismatch")
        files["source-notices/" + span["sha256"] + ".txt"] = block
    return files


def protocol_license_texts(inventory, compiled):
    """Full REUSE texts used by Plasma and the same tagged server-decoration input in misc."""
    for row in inventory["packages"]:
        prefix = row["name"] + "-" + row["version"]
        if row["name"] == "wayland-protocols-plasma" and row["name"] + " v" + row["version"] in compiled:
            result = {PurePosixPath(p).stem: {"path": f"crates/{prefix}/{p}", "sha256": digest}
                      for p, digest in row["notices"].items() if p.startswith("plasma-wayland-protocols/LICENSES/")}
            if result.keys() != {"BSD-3-Clause", "CC0-1.0", "LGPL-2.1-or-later", "MIT-CMU", "MIT"}:
                raise ValueError("Incomplete Plasma REUSE license directory")
            return result
    return {}
