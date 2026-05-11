#!/usr/bin/env python3
"""Download Flatpak NuGet source files into a local staging directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nuget_sources_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def source_filename(source: dict[str, Any]) -> str:
    filename = source.get("dest-filename")
    if not isinstance(filename, str) or not filename:
        raise SystemExit(f"NuGet source missing dest-filename: {source!r}")
    return filename


def verify_sha512(path: Path, expected_hex: str) -> None:
    actual_hex = hashlib.sha512(path.read_bytes()).hexdigest()
    if actual_hex.lower() != expected_hex.lower():
        raise SystemExit(
            f"Checksum mismatch for {path.name}: expected {expected_hex}, got {actual_hex}"
        )


def download(url: str, path: Path) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with urllib.request.urlopen(url) as response, tmp_path.open("wb") as output:
        shutil.copyfileobj(response, output)
    tmp_path.replace(path)


def main() -> int:
    args = parse_args()
    sources = json.loads(args.nuget_sources_json.read_text(encoding="utf-8"))
    if not isinstance(sources, list):
        raise SystemExit(f"NuGet sources must be a JSON array: {args.nuget_sources_json}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for source in sources:
        if not isinstance(source, dict):
            raise SystemExit(f"NuGet source must be a JSON object: {source!r}")
        if source.get("type") != "file" or source.get("dest") != "nuget-sources":
            raise SystemExit(f"Unsupported NuGet source entry: {source!r}")

        url = source.get("url")
        sha512 = source.get("sha512")
        if not isinstance(url, str) or not isinstance(sha512, str):
            raise SystemExit(f"NuGet source missing url/sha512: {source!r}")

        path = args.output_dir / source_filename(source)
        if path.exists():
            verify_sha512(path, sha512)
            continue

        print(f"Downloading {path.name}", file=sys.stderr)
        download(url, path)
        verify_sha512(path, sha512)

    print(f"Staged {len(sources)} NuGet packages in {args.output_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
