#!/usr/bin/env python3
"""Create harmless Pages fixtures or verify their uploaded tar without extracting it."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import tarfile


PUBLIC_FILES = {
    "index.html": b"<html><body>Pages upload validation</body></html>\n",
    "repo/config": b"[core]\nmode=archive-z2\n",
    "repo/summary": b"synthetic summary fixture\n",
    "repo/summary.sig": b"synthetic signature fixture, not a real signature\n",
    "repo/objects/ab/fixture.filez": b"synthetic object fixture\x00\xff\n",
}
HIDDEN_FILES = {".nojekyll": b"", "repo/.hidden-index": b"hidden fixture\n"}
EXCLUDED_FILES = {".git/config": b"excluded fixture\n", ".github/workflows/test.yml": b"excluded fixture\n"}


def create_fixture(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for name, content in (PUBLIC_FILES | HIDDEN_FILES | EXCLUDED_FILES).items():
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (directory / "index-link.html").symlink_to("index.html")
    os.link(directory / "index.html", directory / "index-hardlink.html")


def verify_archive(archive: Path, include_hidden: bool) -> None:
    expected = PUBLIC_FILES | {
        "index-link.html": PUBLIC_FILES["index.html"],
        "index-hardlink.html": PUBLIC_FILES["index.html"],
    }
    if include_hidden:
        expected |= HIDDEN_FILES
    actual = {}
    with tarfile.open(archive, "r:") as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or any(p in {".git", ".github"} for p in path.parts):
                raise ValueError(f"Unsafe or excluded archive path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Expected dereferenced regular file: {member.name}")
            name = str(path)
            if name in actual:
                raise ValueError(f"Duplicate archive entry: {name}")
            if name not in expected or member.size != len(expected[name]):
                raise ValueError(f"Unexpected file or size: {name}")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable file: {name}")
            with stream:
                actual[name] = stream.read()
    if actual != expected:
        raise ValueError("Archive files or bytes differ from the fixture")
    print(f"Verified {len(actual)} files; hidden files included: {include_hidden}; no links or repository metadata")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "verify"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--include-hidden-files", choices=["true", "false"], default="false")
    args = parser.parse_args()
    if args.operation == "create":
        create_fixture(args.path)
    else:
        verify_archive(args.path, args.include_hidden_files == "true")


if __name__ == "__main__":
    main()
