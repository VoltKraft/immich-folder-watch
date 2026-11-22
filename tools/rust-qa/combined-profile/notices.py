"""Assemble original notices for a source-matched native combined development executable, offline."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
from zipfile import BadZipFile, ZipFile, ZipInfo

import sbom
from sbom import require, sha
from sources import local_caches


SQLITE_HEADER = "sqlite3/sqlite3.h"
TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def safe_path(path):
    parts = path.split("/")
    require(re.fullmatch(r"[A-Za-z0-9_./+-]+", path) and
            all(part and not part.endswith(".") for part in parts), f"Unsafe notice path: {path}")
    return path


def crate_members(prefix, archive_sha, wanted, caches):
    """Read only the selected regular members, preserving original bytes under their original paths."""
    require("/" not in safe_path(prefix), "Invalid crate identity")
    expected = {prefix + "/" + safe_path(path): digest for path, digest in wanted.items()}
    filename = prefix + ".crate"
    archive = next((directory / filename for directory in caches if (directory / filename).is_file()), None)
    require(archive is not None, f"Missing {filename} in reviewed local Cargo caches")
    with archive.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    require(len(raw) <= 64 * 1024 * 1024 and sha(raw) == archive_sha, f"Original archive mismatch: {filename}")
    found = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as contents:
        for member in contents:
            if member.name not in expected:
                continue
            require(member.isfile() and member.name not in found and member.size <= 4 * 1024 * 1024,
                    f"Invalid or duplicate notice member: {member.name}")
            with contents.extractfile(member) as source:
                data = source.read()
            require(sha(data) == expected[member.name], f"Notice checksum mismatch: {member.name}")
            found[member.name] = data
    require(found.keys() == expected.keys(), f"Missing notice members: {sorted(expected.keys() - found.keys())}")
    return {"crates/" + path: data for path, data in found.items()}


def git_member(members, revision, path, digest):
    dest = "repository/" + safe_path(path)
    data = sbom.blob(revision, path)
    require(sha(data) == digest, f"Git notice checksum mismatch: {path}")
    members[dest] = data
    return dest


def external_notices(row, inventory, revision, caches, members):
    prefix = row["name"] + "-" + row["version"]
    root = "crates/" + prefix + "/"
    source = row.get("originalCrate", f"https://static.crates.io/crates/{row['name']}/{prefix}.crate")
    record = {"upstreamArchive": source, "upstreamArchiveSha256": row["archiveSha256"],
              "compilerTree": row["compilerTree"], "reviewedTopLevelLicense": row["selected"]}
    repository = dict(row["supplementalNotices"])
    originals = {}
    if row.get("reconstructedSource"):
        record["reconstructedSource"] = row["reconstructedSource"]
        for path, digest in row["notices"].items():
            require(repository.setdefault(path, digest) == digest, f"Conflicting Git notice digests: {path}")
    else:
        originals.update(row["notices"])
    record["notices"] = [root + path for path in sorted(originals)]
    for path, digest in sorted(repository.items()):
        require(digest == inventory["originalNoticeFiles"][path], f"Unreviewed supplemental notice: {path}")
        record["notices"].append(git_member(members, revision, path, digest))
    require(record["notices"], f"Missing notices for {prefix}")
    protocols = row.get("protocols", {})
    if protocols:
        record["protocolXml"] = []
        for path, item in sorted(protocols.items()):
            require(path.endswith(".xml") and path not in originals, f"Unexpected protocol path: {path}")
            originals[path] = item["sha256"]
            record["protocolXml"].append(root + path)
    if row["name"] == "libsqlite3-sys":
        originals[SQLITE_HEADER] = row["native"][SQLITE_HEADER]
        record["sqlitePublicDomainHeader"] = root + SQLITE_HEADER
    if originals:
        members.update(crate_members(prefix, row["archiveSha256"], originals, caches))
    return record


def readme(manifest):
    lines = ["Immich Folder Watch | Combined development executable notices", "",
             f"Native target: {manifest['target']}", f"Source revision: {manifest['revision']}",
             f"Executable: {manifest['executable']} (SHA-256 {manifest['executableSha256']})", "",
             "The build compiled the Cargo packages listed below. Host roles include build scripts and",
             "procedural macros. The five embedded font faces have individual attributions and OFL texts.",
             "manifest.json maps the original files to authenticated source archives or Git blobs and",
             "records their SHA-256 digests. Installed product packages require separate evidence.", "",
             "Embedded fonts", ""]
    for name, font in manifest["fonts"].items():
        lines.extend([name, font["version"], font["copyright"], *font["trademark"], font["notice"], ""])
    lines.extend(["Cargo packages and original notice paths", ""])
    for name, row in manifest["packages"].items():
        lines.extend([name + "  [" + ", ".join(row["compiledFor"]) + "]", *row["notices"]])
        if "sqlitePublicDomainHeader" in row:
            lines.append(row["sqlitePublicDomainHeader"])
        lines.extend(row.get("protocolXml", []))
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def assemble(receipt, receipt_sha, files, revision, target, archive_sha):
    inventory, _, units, root, _ = sbom.verify(receipt, files, revision, target)
    reviewed = {row["name"] + " v" + row["version"]: row for row in inventory["packages"]}
    local = sbom.first_party(revision, receipt["sources"])
    require(local.keys() <= units.keys() and root in local and not (local.keys() & reviewed.keys()),
            "Inconsistent first-party package identities")
    executable, = (u["targetName"] for u in units[root] if "bin" in u["kinds"] and target in u["compiledFor"])
    manifest = {"format": 1, "scope": "Combined development executable", "revision": revision, "target": target,
                "executable": executable + (".exe" if "windows" in target else ""),
                "executableSha256": receipt["native"]["binarySha256"], "nativeArchiveSha256": archive_sha,
                "nativeReceiptSha256": receipt_sha, "compilerUnitsSha256": receipt["outputs"]["compiler-units.json"],
                "sourceInventorySha256": receipt["outputs"]["inventory.json"], "packages": {}, "fonts": {}}
    members = {"repository/LICENSE": sbom.blob(revision, "LICENSE")}
    caches = sorted(directory for home in local_caches() for directory in (home / "registry/cache").glob("*")
                    if directory.is_dir())
    for key, compiled in sorted(units.items()):
        if key in local:
            project = local[key]
            require(project["licenseDeclared"] == "AGPL-3.0-only", f"Changed first-party license: {key}")
            row = {"reviewedTopLevelLicense": project["licenseDeclared"], "gitSource": project["sourceInfo"],
                   "notices": ["repository/LICENSE"]}
        else:
            row = external_notices(reviewed[key], inventory, revision, caches, members)
        row["compiledFor"] = sorted({role for u in compiled for role in u["compiledFor"]})
        row["compiledUnits"] = len(compiled)
        manifest["packages"][key] = row
    font_metadata = json.loads(sbom.blob(revision, "rust/audit/gui-text-inputs.json"))["fonts"]
    for font in sorted(sbom.fonts(revision, inventory), key=lambda f: f["name"]):
        name = font["name"]
        path = "rust/assets/fonts/" + font_metadata.get(name, {}).get("notice", "OFL-1.1.txt")
        notice = git_member(members, revision, path, inventory["originalNoticeFiles"][path])
        manifest["fonts"][name] = {"source": font["downloadLocation"], "assetSha256": font["checksums"][0]["checksumValue"],
                                   "version": font["versionInfo"], "copyright": font["copyrightText"],
                                   "trademark": font["attributionTexts"], "license": font["licenseConcluded"], "notice": notice}
    members["NOTICE.txt"] = readme(manifest)
    manifest["files"] = {path: {"bytes": len(data), "sha256": sha(data)} for path, data in members.items()}
    members["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    return members


def write_archive(output, members):
    names = sorted(safe_path(path) for path in members)
    files = {p.casefold() for p in names}
    directories = {str(parent) for p in names for parent in PurePosixPath(p).parents}
    folded_directories = {p.casefold() for p in directories}
    require(len(names) == len(files) and len(directories) == len(folded_directories)
            and files.isdisjoint(folded_directories), "Ambiguous notice paths")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / "notices.zip"
        with ZipFile(staged, "w") as archive:
            for path in names:
                info = ZipInfo(path, date_time=TIMESTAMP)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, members[path])
        with ZipFile(staged) as archive:
            require(archive.namelist() == names and all(archive.read(p) == members[p] for p in names),
                    "Completed notice archive differs from its original members")
        with staged.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        try:
            # Publish a complete file with no overwrite, including concurrent writers.
            os.link(staged, output)
        except FileExistsError:
            require(not output.is_symlink() and output.is_file(), f"Destination already exists: {output}")
            with output.open("rb") as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == digest,
                        f"A different file already exists: {output}")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--input", required=True, type=Path, help="Original desktop assessment ZIP")
    parser.add_argument("--archive-sha256", required=True, help="Published SHA-256 of the entire native ZIP")
    parser.add_argument("--revision", required=True, help="Full Git commit of the native build")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(re.fullmatch("[0-9a-f]{40}", args.revision), "Supply a full Git source revision")
    review = json.loads(sbom.blob(args.revision, sbom.PROFILE + "/review.json"))
    require(args.target in review["targets"], "Unsupported native target")
    receipt, digest, files = sbom.read_run(args.input, args.target, args.archive_sha256)
    members = assemble(receipt, digest, files, args.revision, args.target, args.archive_sha256)
    print(write_archive(args.output, members), args.output)


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, BadZipFile, tarfile.TarError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
