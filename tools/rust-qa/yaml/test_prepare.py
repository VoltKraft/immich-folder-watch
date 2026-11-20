"""Negative controls for the filtered corresponding-source recipe."""

import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from prepare import PROMOTION, bundle, digest, file_digest, source_files


class SourceFilterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "source.crate"

    def package(self, entries):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, content in entries:
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        return file_digest(self.archive)

    def test_filter_is_exact_and_keeps_code_and_notices(self):
        code = b"pub fn synthetic() {}\n"
        notice = b"Synthetic test notice\n"
        entries = [("base64-0.23.1/README.md", b"Before\n" + PROMOTION + b"After\n"),
                   ("base64-0.23.1/icon_CLion.svg", b"Synthetic non-image placeholder"),
                   ("base64-0.23.1/src/lib.rs", code), ("base64-0.23.1/LICENSE-MIT", notice)]
        checksum = self.package(entries)
        first, changes = source_files(self.archive, "base64-0.23.1", checksum)
        self.assertEqual(first, source_files(self.archive, "base64-0.23.1", checksum)[0])
        self.assertEqual(first["src/lib.rs"], code)
        self.assertEqual(first["LICENSE-MIT"], notice)
        self.assertEqual(first["README.md"], b"Before\nAfter\n")
        self.assertNotIn("icon_CLion.svg", first)
        self.assertEqual(len(changes), 2)
        with self.assertRaisesRegex(ValueError, "checksum"):
            source_files(self.archive, "base64-0.23.1", "0" * 64)
        checksum = self.package([(name, content.replace(PROMOTION, b"changed promotion")) for name, content in entries])
        with self.assertRaisesRegex(ValueError, "expected exact"):
            source_files(self.archive, "base64-0.23.1", checksum)

    def test_unsafe_duplicate_and_link_members_are_rejected(self):
        for name in ("pkg/../outside", "C:/outside", "pkg/a\\outside"):
            checksum = self.package([(name, b"x")])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                source_files(self.archive, "pkg", checksum)
        checksum = self.package([("pkg/file", b"x"), ("pkg/file", b"y")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            source_files(self.archive, "pkg", checksum)
        with tarfile.open(self.archive, "w:gz") as archive:
            member = tarfile.TarInfo("pkg/link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../outside"
            archive.addfile(member)
        with self.assertRaisesRegex(ValueError, "links"):
            source_files(self.archive, "pkg", file_digest(self.archive))

    def test_filtered_bundle_is_byte_reproducible(self):
        source = self.root / "vendor"
        source.mkdir()
        (source / "LICENSE").write_bytes(b"Synthetic notice\n")
        first, second = self.root / "first.tar.gz", self.root / "second.tar.gz"
        bundle(source, {"test": digest(b"synthetic")}, first)
        bundle(source, {"test": digest(b"synthetic")}, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
