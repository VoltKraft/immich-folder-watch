"""Checks for native package identity and retained shipping data."""
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from run import RELEASE, TABLES, check_retained, evidence_hashes, prepare_package, prepare_seed, run, write_json


class ShippingReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.area = Path(temporary.name)

    def test_foreign_target_fails_before_creating_output(self):
        output = self.area / "result"
        with patch("run.native_target", return_value="linux-x64"), self.assertRaisesRegex(ValueError, "native"):
            run("windows-x64", output, None)
        self.assertFalse(output.exists())

    def test_local_package_requires_exact_pinned_bytes(self):
        reference = self.area / "original.bin"
        reference.write_bytes(b"original")
        member = {"bytes": 8, "sha256": hashlib.sha256(b"original").hexdigest(), "name": "fixture.bin"}
        with patch.dict(RELEASE["assets"], {"fixture": member}):
            destination = self.area / "exact"
            destination.mkdir()
            self.assertEqual(prepare_package("fixture", destination, reference).read_bytes(), b"original")
            reference.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                prepare_package("fixture", self.area, reference)
            reference.write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "pinned size"):
                prepare_package("fixture", self.area, reference)

    def test_retained_yaml_and_all_sqlite_rows_must_match_the_seed(self):
        for system in ("linux", "windows"):
            with self.subTest(system=system):
                base = self.area / system
                native = base / "native"
                native.mkdir(parents=True)
                seed = base / "seed"
                initial = prepare_seed(system, seed)
                self.assertEqual(set(initial["rows"]), set(TABLES))
                retained = native / "retained"
                shutil.copytree(seed, retained)
                write_json(native / "result.json", {"status": "passed"})
                check_retained(base, initial, evidence_hashes(base))
                with sqlite3.connect(retained / "sync-state.db") as db:
                    db.execute("UPDATE sync_entries SET album_name = 'different'")
                db.close()
                with self.assertRaisesRegex(ValueError, "sync-state.db"):
                    check_retained(base, initial, evidence_hashes(base))
                shutil.copyfile(seed / "sync-state.db", retained / "sync-state.db")
                (retained / "config.yaml").write_bytes(b"changed\n")
                with self.assertRaisesRegex(ValueError, "config.yaml"):
                    check_retained(base, initial, evidence_hashes(base))

    def test_evidence_index_refuses_a_directory_link(self):
        link = self.area / "linked"
        try:
            link.symlink_to(self.area, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "linked evidence"):
            evidence_hashes(self.area)
