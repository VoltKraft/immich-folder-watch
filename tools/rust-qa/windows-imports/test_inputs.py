"""Check boundaries that could otherwise validate the wrong source or import ABI."""

import struct
import tempfile
import unittest
from pathlib import Path

from formats import ARM64, import_headers
from inputs import upstream
from relink import compare_lock


def import_archive(flags):
    strings = b"IsProcessorFeaturePresent\0kernel32.dll\0"
    obj = struct.pack("<HHHHIIHH", 0, 0xffff, 0, ARM64, 0, len(strings), 792, flags) + strings
    header = f"{'kernel32.dll/':<16}{0:<12}{0:<6}{0:<6}{'644':<8}{len(obj):<10}`\n".encode("ascii")
    return b"!<arch>\n" + header + obj + (b"\n" if len(obj) % 2 else b"")


class InputBoundaries(unittest.TestCase):
    def test_forged_import_kind_fails_even_with_the_expected_name(self):
        with tempfile.TemporaryDirectory() as folder:
            lib = Path(folder) / "test.lib"
            lib.write_bytes(import_archive(4))
            self.assertEqual(import_headers(lib), ({"kernel32.dll": {"IsProcessorFeaturePresent": 792}}, 0))
            lib.write_bytes(import_archive(5))
            with self.assertRaisesRegex(ValueError, "function type"):
                import_headers(lib)

    def test_unreviewed_filtered_archive_refused_before_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "candidate.tar"
            archive.write_bytes(b"wrong input")
            dest = Path(folder) / "sources"
            with self.assertRaisesRegex(ValueError, "tar identity"):
                upstream(dest, False, archive)
            self.assertFalse(dest.exists())

    def test_variant_may_only_replace_the_one_registry_artifact(self):
        before = {"package": [{"name": "windows_aarch64_msvc", "version": "0.52.6",
                               "source": "registry", "checksum": "original"}]}
        after = {"package": [{"name": "windows_aarch64_msvc", "version": "0.52.6"},
                             {"name": "extra"}]}
        with self.assertRaisesRegex(ValueError, "remaining transport lock"):
            compare_lock(before, after)
