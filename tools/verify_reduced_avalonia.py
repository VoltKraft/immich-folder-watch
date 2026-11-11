#!/usr/bin/env python3
"""Reject original or mismatched Avalonia binaries in restored and published output."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from prepare_reduced_avalonia import read_lock
from audit_reduced_avalonia import audit


ASSEMBLIES = {
    "avalonia": "Avalonia.Controls.dll",
    "avalonia.themes.fluent": "Avalonia.Themes.Fluent.dll",
}


def verify(assets_path: Path, source_root: Path, publish: Path | None = None) -> None:
    """Match restored and final DLL bytes to pinned local-build provenance.

    This supplements source exclusions and runtime type/resource tests; a hash
    alone is not a source-license review. All paths come from the exact restored
    package identities, never from a caller-selected provenance file.
    """
    lock = read_lock(source_root)
    recipe = json.loads((source_root / "packaging/avalonia-reduced/removals.json").read_text(encoding="utf-8"))
    assets = json.loads(assets_path.read_text(encoding="utf-8-sig"))
    libraries = {key.lower(): value for key, value in assets.get("libraries", {}).items()}
    roots = [Path(path) for path in assets.get("packageFolders", {})]
    version = lock["packageVersion"]
    commit = lock["source"]["url"].rsplit("/", 1)[1]
    for package, filename in ASSEMBLIES.items():
        identity = f"{package}/{version}"
        library = libraries.get(identity)
        if not library or library.get("type") != "package":
            raise ValueError(f"The reduced package is required: {identity}")
        if any(key.split("/")[0] == package and key != identity for key in libraries):
            raise ValueError(f"Unexpected original or duplicate framework package: {package}")
        candidates = [root / package / version for root in roots]
        directory = next((path for path in candidates if path.is_dir()), None)
        if directory is None:
            raise ValueError(f"Missing restored reduced package: {identity}")
        archive_name = f"{package}.{version}.nupkg"
        built = source_root / "artifacts/reduced-avalonia/feed" / archive_name
        restored = directory / archive_name
        if hashlib.sha512(restored.read_bytes()).digest() != hashlib.sha512(built.read_bytes()).digest():
            raise ValueError(f"Stale package cache differs from the current source build: {identity}")
        # Extracted cache files are mutable independently of NuGet's archive.
        # Trust only the freshly built archive when selecting expected bytes.
        with zipfile.ZipFile(built) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError(f"Duplicate entries in the built package: {identity}")
            provenance_bytes = archive.read("reduced-avalonia.json")
            expected_bytes = archive.read(f"lib/net10.0/{filename}")
        provenance = json.loads(provenance_bytes)
        if (directory / "reduced-avalonia.json").read_bytes() != provenance_bytes:
            raise ValueError(f"Extracted provenance does not match the current source build: {identity}")
        if (provenance.get("schemaVersion") != 1 or provenance.get("upstreamCommit") != commit
                or provenance.get("packageVersion") != version
                or provenance.get("sourceArchiveSha512") != lock["source"]["sha512"]):
            raise ValueError(f"Reduced build provenance does not match the pinned inputs: {identity}")
        if any(provenance.get(key) != recipe[key] for key in ("removedSources", "modifiedSources")):
            raise ValueError(f"Reduced build does not match the current source-removal recipe: {identity}")
        expected = provenance.get("assemblies", {}).get(filename)
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"Missing reduced assembly checksum: {filename}")
        if hashlib.sha256(expected_bytes).hexdigest() != expected:
            raise ValueError(f"Built package assembly checksum mismatch: {filename}")
        binary = directory / "lib" / "net10.0" / filename
        if binary.read_bytes() != expected_bytes:
            raise ValueError(f"Restored reduced assembly checksum mismatch: {filename}")
        # Ref assemblies may legitimately have different bytes, but no fallback
        # framework may retain an upstream executable implementation.
        binaries = list((directory / "lib").rglob(filename))
        if binaries != [binary]:
            raise ValueError(f"Unexpected framework copies in the reduced package: {filename}")
        if publish is not None:
            deployed = list(publish.rglob(filename))
            if deployed != [publish / filename]:
                raise ValueError(f"Missing or duplicate published assembly: {filename}")
            if deployed[0].read_bytes() != expected_bytes:
                raise ValueError(f"Published assembly is not the validated reduced build: {filename}")
    if publish is not None:
        audit([publish])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args()
    try:
        verify(args.assets or args.source_root / "src/ImmichFolderWatch.App.Linux/obj/project.assets.json",
               args.source_root, args.publish)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"Reduced Avalonia verification failed: {exc}", file=sys.stderr)
        return 1
    print("Verified reduced Avalonia package provenance and assembly checksums.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
