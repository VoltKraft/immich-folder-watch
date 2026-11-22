"""Construct and independently verify one fixed synthetic VHD, never a device."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import struct
import uuid
import zlib

HERE = Path(__file__).resolve().parent
DISK_BYTES = 16 * 1024 * 1024
PARTITION_OFFSET = 1024 * 1024
PARTITION_BYTES = DISK_BYTES - PARTITION_OFFSET
TEMPLATE_SERIAL = 0x49F0A017


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def template() -> tuple[bytes, dict]:
    directory = HERE / "windows-image"
    metadata = json.loads((directory / "template.json").read_text(encoding="utf-8"))
    packed = (directory / "fat16.img.zlib").read_bytes()
    if len(packed) > 32768 or sha256(packed) != metadata["compressed_sha256"]:
        raise ValueError("FAT template archive changed or exceeded its bound")
    decoder = zlib.decompressobj()
    data = decoder.decompress(packed, PARTITION_BYTES + 1)
    if (len(data) != PARTITION_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or sha256(data) != metadata["filesystem_sha256"]):
        raise ValueError("FAT template bytes or decoded size changed")
    if sha256((directory / "COPYING.dosfstools").read_bytes()) != metadata["license_sha256"]:
        raise ValueError("FAT template notice changed")
    if sha256((directory / "dosfstools-4.2.tar.gz").read_bytes()) != metadata["generator_source_sha256"]:
        raise ValueError("FAT template corresponding source changed")
    return data, metadata


def no_reparse(path: Path) -> None:
    """Reject every existing redirect in the supplied ordinary file path."""
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("fixture path contains a symbolic link or reparse point")


def create(path: Path, identity: uuid.UUID) -> dict:
    no_reparse(path)
    if path.exists() or not path.parent.is_dir() or path.suffix != ".vhd":
        raise ValueError("VHD must be a fresh ordinary file in the owned output")
    fat, metadata = template()
    image = bytearray(DISK_BYTES + 512)
    image[PARTITION_OFFSET:DISK_BYTES] = fat
    signature = int.from_bytes(identity.bytes[:4], "little") or 1
    struct.pack_into("<I", image, 440, signature)
    # One inactive FAT16 LBA data partition. No MBR bootstrap instructions.
    image[446:462] = struct.pack("<B3sB3sII", 0, b"\xfe\xff\xff", 0x0e,
                                b"\xfe\xff\xff", PARTITION_OFFSET // 512, PARTITION_BYTES // 512)
    image[510:512] = b"\x55\xaa"
    struct.pack_into("<I", image, PARTITION_OFFSET + 39, signature)
    footer = bytearray(512)
    struct.pack_into(">8sIIQI4sI4sQQHBBII16sB", footer, 0,
                     b"conectix", 2, 0x10000, 0xffffffffffffffff, 0,
                     b"ifwF", 0x10000, b"Wi2k", DISK_BYTES, DISK_BYTES,
                     481, 4, 17, 2, 0, identity.bytes, 0)
    struct.pack_into(">I", footer, 64, (~sum(footer)) & 0xffffffff)
    image[DISK_BYTES:] = footer
    with path.open("xb") as stream:
        stream.write(image)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    receipt = verify(path, identity)
    receipt["template_sha256"] = metadata["filesystem_sha256"]
    return receipt


def verify(path: Path, identity: uuid.UUID) -> dict:
    """Read back the full file and reject changed layout, payload or footer."""
    no_reparse(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != DISK_BYTES + 512 or info.st_nlink != 1:
        raise ValueError("VHD is not the sole-link bounded regular file")
    data = path.read_bytes()
    footer = data[-512:]
    without_checksum = bytearray(footer)
    without_checksum[64:68] = bytes(4)
    if (footer[:8] != b"conectix" or struct.unpack_from(">IIQ", footer, 8) != (2, 0x10000, 0xffffffffffffffff)
            or struct.unpack_from(">QQ", footer, 40) != (DISK_BYTES, DISK_BYTES)
            or struct.unpack_from(">I", footer, 60)[0] != 2 or footer[68:84] != identity.bytes
            or any(footer[84:]) or struct.unpack_from(">I", footer, 64)[0] != (~sum(without_checksum) & 0xffffffff)):
        raise ValueError("not the authenticated fixed, parentless VHD")
    signature = int.from_bytes(identity.bytes[:4], "little") or 1
    if (any(data[:440]) or struct.unpack_from("<I", data, 440)[0] != signature or any(data[444:446])
            or data[446] != 0 or data[450] != 0x0e
            or struct.unpack_from("<II", data, 454) != (2048, PARTITION_BYTES // 512)
            or any(data[462:510]) or data[510:512] != b"\x55\xaa" or any(data[512:PARTITION_OFFSET])):
        raise ValueError("unexpected MBR code, disk signature or partition layout")
    fat = bytearray(data[PARTITION_OFFSET:DISK_BYTES])
    if struct.unpack_from("<I", fat, 39)[0] != signature:
        raise ValueError("filesystem serial does not match the new disk identity")
    struct.pack_into("<I", fat, 39, TEMPLATE_SERIAL)
    expected, metadata = template()
    if fat != expected:
        raise ValueError("filesystem differs from the independently checked empty template")
    sector_bytes, = struct.unpack_from("<H", fat, 11)
    reserved, = struct.unpack_from("<H", fat, 14)
    root_entries, = struct.unpack_from("<H", fat, 17)
    total_sectors, = struct.unpack_from("<H", fat, 19)
    fat_sectors, = struct.unpack_from("<H", fat, 22)
    cluster_sectors, fat_count = fat[13], fat[16]
    root_sectors = (root_entries * 32 + sector_bytes - 1) // sector_bytes
    data_clusters = (total_sectors - reserved - fat_count * fat_sectors - root_sectors) // cluster_sectors
    if (sector_bytes != 512 or cluster_sectors != 4 or fat_count != 2 or reserved != 1
            or root_entries != 512 or total_sectors * 512 != PARTITION_BYTES
            or not 4085 <= data_clusters < 65525 or any(fat[62:510])):
        raise ValueError("unexpected FAT16 geometry or boot program")
    return {"format": "ifw-fixed-vhd-v1", "image_sha256": sha256(data), "image_bytes": len(data),
            "virtual_bytes": DISK_BYTES, "partition_offset": PARTITION_OFFSET, "partition_bytes": PARTITION_BYTES,
            "uuid": str(identity), "disk_signature": signature, "filesystem_serial": signature,
            "bytes_per_sector": sector_bytes, "sectors_per_cluster": cluster_sectors,
            "data_clusters": data_clusters, "data_bytes": data_clusters * cluster_sectors * sector_bytes,
            "template_sha256": metadata["filesystem_sha256"], "boot_program_present": False}
