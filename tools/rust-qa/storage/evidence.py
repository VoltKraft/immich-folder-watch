"""Source and fixture verification for the development-only storage assessment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tomllib


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def external_lock(path: Path) -> dict[tuple[str, str], str]:
    lock = tomllib.loads(path.read_text(encoding="utf-8"))
    return {(entry["name"], entry["version"]): entry["checksum"]
            for entry in lock["package"] if "checksum" in entry}


def target_graph(metadata: dict) -> list[dict]:
    packages = {package["id"]: package for package in metadata["packages"]}
    return sorted([
        {"name": packages[node["id"]]["name"], "version": packages[node["id"]]["version"],
         "features": sorted(node["features"])}
        for node in metadata["resolve"]["nodes"] if packages[node["id"]]["source"]
    ], key=lambda entry: entry["name"])


def relative_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("unsafe source or fixture member")
    return path


def verify_fixture(root: Path, native_os: str) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["Format"] != "ifw-rw01-legacy-v1" or manifest["Platform"] != native_os
            or manifest["SyntheticOnly"] is not True):
        raise ValueError("wrong platform or non-synthetic legacy corpus")
    for name, digest in manifest["Fixtures"].items():
        if sha256(root / relative_member(name)) != digest:
            raise ValueError(f"legacy fixture checksum mismatch: {name}")
    return manifest


def verify_archive(archive: Path, source: Path, expected_digest: str) -> int:
    """Compare every unpacked source byte with the authenticated original archive.

    Cargo bookkeeping files are the only permitted additions. No archive content
    is extracted or executed here, and links/traversal members are rejected.
    """
    if sha256(archive) != expected_digest:
        raise ValueError(f"crate archive checksum mismatch: {archive.name}")
    expected_files: set[Path] = set()
    with tarfile.open(archive, "r:gz") as package:
        for member in package:
            path = relative_member(member.name)
            if not path.parts or path.parts[0] != source.name:
                raise ValueError("unexpected crate archive root")
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) < 2:
                raise ValueError("unsupported crate archive member")
            relative = Path(*path.parts[1:])
            if relative in expected_files:
                raise ValueError("duplicate source archive member")
            expected_files.add(relative)
            actual = source / relative
            if actual.is_symlink() or not actual.is_file():
                raise ValueError("missing or linked unpacked source")
            original = package.extractfile(member)
            if original is None or hashlib.file_digest(original, "sha256").hexdigest() != sha256(actual):
                raise ValueError(f"unpacked crate differs from archive: {source.name}/{relative}")
    actual_files = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("linked unpacked source member")
        if path.is_file():
            actual_files.add(path.relative_to(source))
    extras = actual_files - expected_files - {Path(".cargo-ok"), Path(".cargo-checksum.json")}
    if extras:
        raise ValueError(f"unexpected source files in {source.name}")
    return len(expected_files)


def verify_sources(metadata: dict, inputs: dict, cargo_home: Path, evidence: Path) -> dict:
    packages = {(package["name"], package["version"]): package
                for package in metadata["packages"] if package["source"]}
    expected = {(entry["name"], entry["version"]): entry for entry in inputs["packages"]}
    if packages.keys() != expected.keys():
        raise ValueError("resolved package identities differ from reviewed inputs")
    counts: dict[str, int] = {}
    for key, entry in expected.items():
        source = Path(packages[key]["manifest_path"]).parent
        candidates = list((cargo_home / "registry/cache").glob(f"*/{source.name}.crate"))
        if len(candidates) != 1:
            raise ValueError(f"missing or ambiguous original archive: {source.name}")
        archive = candidates[0]
        counts[source.name] = verify_archive(archive, source, entry["archive_sha256"])
        target = evidence / "source-archives" / archive.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, target)
        for notice in entry["notices"]:
            relative = relative_member(notice["path"])
            original = source / relative
            if sha256(original) != notice["sha256"]:
                raise ValueError(f"reviewed notice changed: {source.name}/{relative}")
            target = evidence / "notices" / source.name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        for file in entry.get("native_sources", []):
            if sha256(source / relative_member(file["path"])) != file["sha256"]:
                raise ValueError("native source input changed")
    return counts
