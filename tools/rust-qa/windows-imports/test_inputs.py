"""Check boundaries that could otherwise validate the wrong source or import ABI."""

import struct
import tempfile
import unittest
from pathlib import Path

from formats import AMD64, ARM64, import_headers
from inputs import upstream
from relink import check_link_response, compare_lock


def import_archive(flags, machine=ARM64):
    strings = b"IsProcessorFeaturePresent\0kernel32.dll\0"
    obj = struct.pack("<HHHHIIHH", 0, 0xffff, 0, machine, 0, len(strings), 792, flags) + strings
    header = f"{'kernel32.dll/':<16}{0:<12}{0:<6}{0:<6}{'644':<8}{len(obj):<10}`\n".encode("ascii")
    return b"!<arch>\n" + header + obj + (b"\n" if len(obj) % 2 else b"")


class InputBoundaries(unittest.TestCase):
    def test_x64_rejects_arm64_despite_identical_export_names(self):
        with tempfile.TemporaryDirectory() as folder:
            lib = Path(folder) / "test.lib"
            lib.write_bytes(import_archive(4, AMD64))
            self.assertIn("kernel32.dll", import_headers(lib, AMD64)[0])
            with self.assertRaisesRegex(ValueError, "machine"):
                import_headers(lib, ARM64)
            lib.write_bytes(import_archive(4, ARM64))
            with self.assertRaisesRegex(ValueError, "machine"):
                import_headers(lib, AMD64)

    def test_link_response_rejects_a_published_sibling_with_the_same_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "published/windows.0.52.0.lib"
            rebuilt = root / "rebuilt/windows.0.52.0.lib"
            for path in (original, rebuilt):
                path.parent.mkdir()
                path.touch()
            response = root / "link.rsp"
            response.write_text(f'"{original}"\r\n', encoding="utf-16")
            with self.assertRaisesRegex(ValueError, "isolated import library"):
                check_link_response(response, rebuilt)
            response.write_text(f'"{rebuilt}"\r\n', encoding="utf-16")
            check_link_response(response, rebuilt)

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
