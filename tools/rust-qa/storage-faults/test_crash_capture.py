"""Test crash-file evidence without weakening DB/WAL capture or comparisons."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import run as runner


class CrashCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        runner.ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="capture-check-", dir=runner.ARTIFACTS)
        self.output = Path(self.directory.name)
        for name, data in (("state.db", b"synthetic database"), ("state.db-wal", b"synthetic WAL"),
                           ("state.db-shm", bytes(32768))):
            (self.output / name).write_bytes(data)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_windows_policy_defers_locked_shm_and_names_only_compared_files(self) -> None:
        ordinary_copy = shutil.copyfile

        def locked_copy(source, destination):
            if source.name == "state.db-shm":
                raise PermissionError(13, "injected active Windows WAL-index lock")
            return ordinary_copy(source, destination)

        with patch.object(runner.shutil, "copyfile", side_effect=locked_copy):
            before = runner.capture_crash_files(self.output, "before", include_shm=False)
        self.assertEqual(set(before), {"state.db", "state.db-wal"})
        self.assertFalse((self.output / "before/state.db-shm").exists())
        (self.output / "state.db-shm").write_bytes(b"different transient WAL index")
        after = runner.capture_crash_files(self.output, "after", include_shm=True)
        self.assertEqual(set(after), {"state.db", "state.db-wal", "state.db-shm"})
        self.assertEqual(runner.compare_crash_files(before, after), ["state.db", "state.db-wal"])
        self.assertEqual((self.output / "after/state.db-shm").read_bytes(), b"different transient WAL index")

    def test_linux_policy_compares_shm_too(self) -> None:
        before = runner.capture_crash_files(self.output, "before", include_shm=True)
        after = runner.capture_crash_files(self.output, "after", include_shm=True)
        self.assertEqual(runner.compare_crash_files(before, after), ["state.db", "state.db-shm", "state.db-wal"])
        (self.output / "state.db-shm").write_bytes(b"changed")
        changed = runner.capture_crash_files(self.output, "changed", include_shm=True)
        with self.assertRaisesRegex(RuntimeError, "state.db-shm"):
            runner.compare_crash_files(before, changed)

    def test_db_and_wal_copy_denials_are_fatal(self) -> None:
        ordinary_copy = shutil.copyfile
        for denied in ("state.db", "state.db-wal"):
            with self.subTest(denied=denied):
                def denied_copy(source, destination):
                    if source.name == denied:
                        raise PermissionError(13, "injected required-file denial")
                    return ordinary_copy(source, destination)

                with patch.object(runner.shutil, "copyfile", side_effect=denied_copy):
                    with self.assertRaises(PermissionError):
                        runner.capture_crash_files(self.output, "denied-" + denied, include_shm=False)

    def test_missing_db_or_wal_is_fatal(self) -> None:
        for name in ("state.db", "state.db-wal"):
            with self.subTest(name=name):
                path = self.output / name
                original = path.read_bytes()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    runner.capture_crash_files(self.output, "missing-" + name, include_shm=False)
                path.write_bytes(original)

    def test_same_length_db_or_wal_mutations_are_detected(self) -> None:
        before = runner.capture_crash_files(self.output, "before", include_shm=False)
        for name in ("state.db", "state.db-wal"):
            with self.subTest(name=name):
                path = self.output / name
                original = path.read_bytes()
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                after = runner.capture_crash_files(self.output, "changed-" + name, include_shm=True)
                with self.assertRaisesRegex(RuntimeError, name):
                    runner.compare_crash_files(before, after)
                path.write_bytes(original)

    def test_absent_transient_shm_does_not_claim_a_comparison(self) -> None:
        (self.output / "state.db-shm").unlink()
        before = runner.capture_crash_files(self.output, "before", include_shm=True)
        after = runner.capture_crash_files(self.output, "after", include_shm=True)
        self.assertEqual(runner.compare_crash_files(before, after), ["state.db", "state.db-wal"])

    @unittest.skipUnless(os.name == "nt", "requires actual Windows mandatory byte locks")
    def test_native_windows_active_byte_lock_is_read_only_after_unlock(self) -> None:
        import msvcrt

        path = self.output / "state.db-shm"
        with path.open("r+b") as owner:
            owner.seek(120)
            msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with self.assertRaises(PermissionError):
                    path.read_bytes()
                before = runner.capture_crash_files(self.output, "before", include_shm=False)
            finally:
                owner.seek(120)
                msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)
        after = runner.capture_crash_files(self.output, "after", include_shm=True)
        self.assertEqual(after["state.db-shm"]["bytes"], 32768)
        self.assertEqual(runner.compare_crash_files(before, after), ["state.db", "state.db-wal"])


if __name__ == "__main__":
    unittest.main()
