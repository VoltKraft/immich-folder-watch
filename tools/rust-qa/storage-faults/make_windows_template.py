#!/usr/bin/env python3
"""Recreate the development-only empty FAT16 template, never a device target."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zlib

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_SHA256 = "64926eebf90092dca21b14259a5301b7b98e7b1943e8a201c7d726084809b527"
PARTITION_BYTES = 15 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--mkfs", type=Path, required=True)
    parser.add_argument("--fsck", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "artifacts/rust/storage-faults"):
        raise ValueError("template generation is restricted to fresh storage-fault artifacts")
    if digest(args.source_archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError("unreviewed dosfstools source archive")
    out.mkdir(parents=True, exist_ok=False)
    target = out / "fat16.img"
    arguments = [str(args.mkfs.resolve()), "--invariant", "-C", "-F", "16", "-a", "-s", "4",
                 "-S", "512", "-R", "1", "-f", "2", "-r", "512", "-h", "2048", "-g", "255/63",
                 "-i", "49F0A017", "-n", "IFWFAULT", str(target), str(PARTITION_BYTES // 1024)]
    made = subprocess.run(arguments, capture_output=True, timeout=30, check=True)
    (out / "mkfs.log").write_bytes(made.stdout + made.stderr)
    original = target.read_bytes()
    if len(original) != PARTITION_BYTES or original[54:62] != b"FAT16   ":
        raise ValueError("generator did not create the fixed FAT16 template")
    data = bytearray(original)
    # Remove all 448 bytes of generated x86 boot code/message. The ordinary
    # FAT boot jump/BPB remain; the enclosing MBR has no code or active entry.
    data[62:510] = bytes(448)
    target.write_bytes(data)
    checked = subprocess.run([str(args.fsck.resolve()), "-n", "-v", str(target)],
                             capture_output=True, timeout=30, check=True)
    (out / "fsck.log").write_bytes(checked.stdout + checked.stderr)
    packed = zlib.compress(data, level=9)
    (out / "fat16.img.zlib").write_bytes(packed)
    with tarfile.open(args.source_archive) as archive:
        license_bytes = archive.extractfile("dosfstools-4.2/COPYING").read()
    (out / "COPYING.dosfstools").write_bytes(license_bytes)
    metadata = {"format": "ifw-empty-fat16-v1", "filesystem_bytes": PARTITION_BYTES,
                "filesystem_sha256": digest(data), "compressed_sha256": digest(packed),
                "compressed_bytes": len(packed), "license_sha256": digest(license_bytes),
                "generator_source_url": "https://github.com/dosfstools/dosfstools/releases/download/v4.2/dosfstools-4.2.tar.gz",
                "generator_source_sha256": ARCHIVE_SHA256, "license": "GPL-3.0-or-later",
                "zeroed_boot_code_range": [62, 510]}
    (out / "template.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (out / "generation.json").write_text(json.dumps({"command": arguments,
        "mkfs_binary_sha256": digest(args.mkfs.read_bytes()), "fsck_binary_sha256": digest(args.fsck.read_bytes()),
        "original_image_sha256": digest(original), "template": metadata}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
