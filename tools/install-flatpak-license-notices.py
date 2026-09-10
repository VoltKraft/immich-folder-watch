#!/usr/bin/env python3
"""Install license texts from the offline NuGet build feed without network access.

Every archive is inventoried, including build-only and other-platform inputs.
This is an attribution inventory, not a runtime SBOM or a legal compatibility
assessment. Missing license texts require an exact-version source supplement;
an SPDX expression or an inventory entry never substitutes for license text.
The output directory must be empty or absent. All inputs are validated before
writing any output. Only selected regular notice files are copied from archives.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo


MAX_TEXT_BYTES = 8 * 1024 * 1024
COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
NOTICE_RE = re.compile(r"(?:licen[cs]e|notice|copying|copyright|ofl)", re.IGNORECASE)
LICENSE_RE = re.compile(r"(?:licen[cs]e|copying|ofl)", re.IGNORECASE)


class NoticeError(ValueError):
    """A build input cannot supply safe, traceable license notices."""


def safe_relative_path(value: str) -> PurePosixPath:
    """Reject archive and catalog paths that could escape their destination."""
    if (
        not value or "\\" in value or ":" in value
        or any(ord(character) < 32 for character in value)
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise NoticeError(f"unsafe notice path: {value!r}")
    return PurePosixPath(value)


def archive_text(archive: ZipFile, item: ZipInfo) -> bytes:
    """Read a bounded regular file; never follow archive symlinks."""
    safe_relative_path(item.filename)
    mode = item.external_attr >> 16
    if item.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
        raise NoticeError(f"notice is not a regular file: {item.filename}")
    if item.file_size > MAX_TEXT_BYTES:
        raise NoticeError(f"notice exceeds {MAX_TEXT_BYTES} bytes: {item.filename}")
    data = archive.read(item)
    if not data.strip() or b"\x00" in data:
        raise NoticeError(f"notice is empty or binary: {item.filename}")
    return data


def read_supplements(directory: Path) -> tuple[dict, dict[str, bytes], dict]:
    """Load exact package versions and hash-verified upstream notice sources."""
    catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    sources = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(sources, dict):
        raise NoticeError("supplement catalogs must be JSON objects")
    data: dict[str, bytes] = {}
    for name, source in sources.items():
        relative = safe_relative_path(name)
        path = directory.joinpath(*relative.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise NoticeError(f"unsafe supplemental file: {name}")
        content = path.read_bytes()
        if len(content) > MAX_TEXT_BYTES or not content.strip() or b"\x00" in content:
            raise NoticeError(f"invalid supplemental notice text: {name}")
        if not isinstance(source, dict) or not str(source.get("url", "")).startswith("https://"):
            raise NoticeError(f"supplement lacks an HTTPS provenance URL: {name}")
        if hashlib.sha256(content).hexdigest() != source.get("sha256"):
            raise NoticeError(f"supplement checksum mismatch: {name}")
        data[name] = content
    for package, versions in catalog.items():
        if not COMPONENT_RE.fullmatch(package) or package != package.lower() or not isinstance(versions, dict):
            raise NoticeError(f"invalid supplemental package entry: {package}")
        for version, names in versions.items():
            if not COMPONENT_RE.fullmatch(version) or not isinstance(names, list) or not names:
                raise NoticeError(f"invalid supplemental version entry: {package}/{version}")
            if any(not isinstance(name, str) or name not in data for name in names):
                raise NoticeError(f"unknown supplemental source: {package}/{version}")
    return catalog, data, sources


def collect_package(path: Path, catalog: dict, supplemental_data: dict, sources: dict) -> tuple[dict, dict[str, bytes]]:
    """Return metadata and notice bytes after checking one complete archive."""
    if path.is_symlink():
        raise NoticeError(f"source archive must not be a symlink: {path.name}")
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(names) != len(set(names)):
            raise NoticeError(f"duplicate archive entries: {path.name}")
        nuspecs = [item for item in entries if "/" not in item.filename and item.filename.lower().endswith(".nuspec")]
        if len(nuspecs) != 1:
            raise NoticeError(f"expected one root nuspec: {path.name}")
        root = ET.fromstring(archive_text(archive, nuspecs[0]))
        metadata = next((element for element in root if element.tag.split("}")[-1] == "metadata"), None)
        if metadata is None:
            raise NoticeError(f"nuspec metadata is absent: {path.name}")
        fields = {element.tag.split("}")[-1]: element for element in metadata}

        def value(name: str) -> str:
            element = fields.get(name)
            return "" if element is None else (element.text or "").strip()

        package_id, version = value("id"), value("version")
        if not COMPONENT_RE.fullmatch(package_id) or not COMPONENT_RE.fullmatch(version):
            raise NoticeError(f"invalid package identity: {path.name}")
        package_key = package_id.lower()
        license_element = fields.get("license")
        license_type = "" if license_element is None else license_element.get("type", "")
        declared_license_file = value("license") if license_type == "file" else ""
        if declared_license_file:
            safe_relative_path(declared_license_file)
            if declared_license_file not in names:
                raise NoticeError(f"declared license file is missing: {path.name}: {declared_license_file}")

        selected: dict[str, bytes] = {}
        has_license_text = False
        for item in entries:
            if item.is_dir():
                continue
            if NOTICE_RE.search(PurePosixPath(item.filename).name) or item.filename == declared_license_file:
                relative = safe_relative_path(item.filename)
                selected[f"{package_key}/{version}/archive/{relative}"] = archive_text(archive, item)
                has_license_text |= bool(LICENSE_RE.search(relative.name)) or item.filename == declared_license_file

        supplements = []
        if package_key in catalog:
            if version not in catalog[package_key]:
                raise NoticeError(f"review supplemental notices for new package version: {package_id}/{version}")
            supplements = catalog[package_key][version]
            for name in supplements:
                selected[f"{package_key}/{version}/upstream/{name}"] = supplemental_data[name]
                has_license_text |= bool(LICENSE_RE.search(name))
        if not has_license_text:
            raise NoticeError(f"license text missing; add an upstream supplement: {package_id}/{version}")

        repository = fields.get("repository")
        with path.open("rb") as source:
            archive_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
        return {
            "id": package_id,
            "version": version,
            "authors": value("authors"),
            "copyright": value("copyright"),
            "license": {"type": license_type, "value": value("license"), "url": value("licenseUrl")},
            "repository": {} if repository is None else dict(repository.attrib),
            "source_archive": path.name,
            "source_sha256": archive_sha256,
            "notice_files": sorted(selected),
            "supplemental_sources": [{"file": name, **sources[name]} for name in supplements],
        }, selected


def install_notices(source_dir: Path, output_dir: Path, supplemental_dir: Path) -> list[dict]:
    """Validate the offline feed, then install notices and a deterministic index."""
    if not source_dir.is_dir():
        raise NoticeError(f"NuGet source directory does not exist: {source_dir}")
    if output_dir.is_symlink() or (output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir()))):
        raise NoticeError("output directory must be empty or absent")
    catalog, supplemental_data, sources = read_supplements(supplemental_dir)
    archives = sorted(source_dir.glob("*.nupkg"))
    if not archives:
        raise NoticeError("NuGet source directory contains no .nupkg archives")
    packages: list[dict] = []
    output: dict[str, bytes] = {}
    identities = set()
    for archive in archives:
        metadata, files = collect_package(archive, catalog, supplemental_data, sources)
        identity = (metadata["id"].lower(), metadata["version"].lower())
        if identity in identities:
            raise NoticeError(f"duplicate package identity: {identity[0]}/{identity[1]}")
        identities.add(identity)
        packages.append(metadata)
        output.update(files)
    packages.sort(key=lambda package: (package["id"].lower(), package["version"]))
    index = {
        "schema_version": 1,
        "scope": "All NuGet archives in the offline build feed, including build-only and other-platform inputs; not a runtime SBOM.",
        "packages": packages,
    }
    output["index.json"] = (json.dumps(index, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    for name, content in sorted(output.items()):
        target = output_dir.joinpath(*safe_relative_path(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return packages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--supplemental-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        packages = install_notices(args.source_dir, args.output_dir, args.supplemental_dir)
    except (NoticeError, OSError, BadZipFile, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"License notice installation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Installed license texts and notices for {len(packages)} NuGet archives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
