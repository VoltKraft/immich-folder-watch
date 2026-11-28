"""Check the project-local cache used after a native build releases its temporary sources."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "rust-qa/native-notice-input.py"
SPEC = importlib.util.spec_from_file_location("native_notice_input", SCRIPT)
assessment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assessment)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name)
        self.filename = self.cache / "sample-1.0.0.crate"
        self.original = b"synthetic original archive"
        self.digest = hashlib.sha256(self.original).hexdigest()

    def ensure(self, fetch):
        return assessment.ensure_archive("sample", "1.0.0", self.digest, [self.cache], self.cache, fetch)

    def test_complete_original_is_available_to_a_later_offline_process(self):
        with self.assertRaises(FileNotFoundError):
            self.ensure(False)

        def acquire(name, staged, checksum):
            self.assertEqual((name, checksum), ("sample", self.digest))
            self.assertNotEqual(staged, self.filename)
            staged.write_bytes(self.original)

        with patch.object(assessment.sources, "public_archive", side_effect=acquire) as network:
            self.assertTrue(self.ensure(True))
            self.assertFalse(self.ensure(False))
            network.assert_called_once()
        self.assertEqual(list(self.cache.iterdir()), [self.filename])
        self.assertEqual(self.filename.read_bytes(), self.original)

    def test_path_dependency_uses_a_secondary_cache_when_offline(self):
        empty = self.cache / "empty"
        secondary = self.cache / "transport"
        cached = secondary / "registry/cache/test" / assessment.hyper_util_source.ARCHIVE.name
        cached.parent.mkdir(parents=True)
        cached.write_bytes(self.original)
        with (patch.object(assessment.sources, "ROOT", self.cache),
              patch.object(assessment.sources, "local_caches", return_value=[empty, secondary]),
              patch.object(assessment.sources, "catalog", return_value={}),
              patch.object(assessment.hyper_util_source, "original", return_value=cached) as original,
              patch.object(assessment.hyper_util_source, "reconstruct", return_value={"treeSha256": self.digest}) as replay,
              redirect_stdout(io.StringIO())):
            assessment.prepare_cache(False)
        original.assert_called_once_with(secondary, False)
        replay.assert_called_once_with(cached, assessment.hyper_util_source.SOURCE)

    def test_failed_acquisition_leaves_no_partial_input(self):
        def interrupted(name, staged, checksum):
            staged.write_bytes(b"partial fixture")
            raise OSError("interrupted")

        with patch.object(assessment.sources, "public_archive", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.ensure(True)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_rejects_a_conflicting_original_without_replacing_it(self):
        def concurrent_acquisition(name, staged, checksum):
            staged.write_bytes(self.original)
            self.filename.write_bytes(b"different fixture")

        with patch.object(assessment.sources, "public_archive", side_effect=concurrent_acquisition):
            with self.assertRaisesRegex(ValueError, "Conflicting archive"):
                self.ensure(True)
        with self.assertRaisesRegex(ValueError, "Changed original archive"):
            self.ensure(False)
        self.assertEqual(self.filename.read_bytes(), b"different fixture")


if __name__ == "__main__":
    unittest.main()
