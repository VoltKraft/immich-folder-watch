"""Negative controls for the pre-build source/fixture evidence boundary."""

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from evidence import sha256, verify_archive, verify_fixture
import run


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "synthetic-1.0.0"
        self.source.mkdir()
        (self.source / "LICENSE").write_bytes(b"Synthetic notice\n")
        self.archive = self.root / "synthetic.crate"

    def package(self, members):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, content in members:
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        return sha256(self.archive)

    def test_untouched_source_passes_but_tampered_source_and_archive_fail(self):
        digest = self.package([("synthetic-1.0.0/LICENSE", b"Synthetic notice\n")])
        self.assertEqual(verify_archive(self.archive, self.source, digest), 1)
        (self.source / "LICENSE").write_bytes(b"Replaced notice\n")
        with self.assertRaisesRegex(ValueError, "differs from archive"):
            verify_archive(self.archive, self.source, digest)
        self.archive.write_bytes(b"Replaced archive")
        with self.assertRaisesRegex(ValueError, "archive checksum"):
            verify_archive(self.archive, self.source, digest)

    def test_traversal_duplicate_and_injected_sources_are_rejected(self):
        for name in ("synthetic-1.0.0/../escape", "C:/escape", "synthetic-1.0.0/dir\\escape"):
            digest = self.package([(name, b"x")])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verify_archive(self.archive, self.source, digest)
        member = ("synthetic-1.0.0/LICENSE", b"Synthetic notice\n")
        digest = self.package([member, member])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            verify_archive(self.archive, self.source, digest)
        digest = self.package([member])
        (self.source / "build.rs").write_bytes(b"unreviewed")
        with self.assertRaisesRegex(ValueError, "unexpected source"):
            verify_archive(self.archive, self.source, digest)

    def test_archive_link_members_are_rejected_without_extraction(self):
        with tarfile.open(self.archive, "w:gz") as archive:
            member = tarfile.TarInfo("synthetic-1.0.0/link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../../outside"
            archive.addfile(member)
        with self.assertRaisesRegex(ValueError, "unsupported crate archive member"):
            verify_archive(self.archive, self.source, sha256(self.archive))

    def test_platform_fixture_and_payload_changes_fail(self):
        manifest = {"Format": "ifw-rw01-legacy-v1", "Platform": "linux", "SyntheticOnly": True,
                    "Fixtures": {"LICENSE": sha256(self.source / "LICENSE")}}
        (self.source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        verify_fixture(self.source, "linux")
        with self.assertRaisesRegex(ValueError, "wrong platform"):
            verify_fixture(self.source, "windows")
        (self.source / "LICENSE").write_bytes(b"Changed fixture")
        with self.assertRaisesRegex(ValueError, "fixture checksum"):
            verify_fixture(self.source, "linux")

    def test_source_edit_during_compilation_invalidates_receipt(self):
        file = self.source / "LICENSE"
        with patch.object(run, "ROOT", self.root), patch.object(run, "first_party_paths", return_value=[file]):
            archived = run.archive_first_party(self.root / "retained", self.source, [])
            run.confirm_sources(self.source, [], archived)
            file.write_bytes(b"Edited during compilation\n")
            with self.assertRaisesRegex(ValueError, "sources changed during execution"):
                run.confirm_sources(self.source, [], archived)


if __name__ == "__main__":
    unittest.main()
