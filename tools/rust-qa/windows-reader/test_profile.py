from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from run import private_profile


class ReaderProfileTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.directory = Mock(name="temporary directory")
        self.directory.name = str(self.parent / "private")
        self.locked = PermissionError(13, "in use", "helper.dll")
        self.locked.winerror = 32
        self.report = {}
        self.enterContext(patch("windows_observer.tempfile.TemporaryDirectory", return_value=self.directory))
        self.sleep = self.enterContext(patch("windows_observer.time.sleep"))

    def profile(self):
        return private_profile(self.parent, "ifw-reader-", self.report)

    def test_retries_a_transient_owned_module_lock(self):
        self.directory.cleanup.side_effect = [self.locked, None]
        with self.profile():
            pass
        self.assertEqual(self.directory.cleanup.call_count, 2)
        self.assertEqual(self.report, {"profileRemoved": True})

    def test_persistent_lock_keeps_the_original_observation_failure(self):
        self.directory.cleanup.side_effect = self.locked
        with patch("windows_observer.time.monotonic", side_effect=[100, 121]):
            with self.assertRaisesRegex(RuntimeError, "missing utterance"):
                with self.profile():
                    raise RuntimeError("missing utterance")
        self.assertFalse(self.report["profileRemoved"])
        self.assertEqual(self.report["profileCleanupError"],
                         {"type": "PermissionError", "winerror": 32, "file": "helper.dll"})

    def test_cleanup_failure_after_a_successful_observation_fails_the_run(self):
        self.directory.cleanup.side_effect = self.locked
        with patch("windows_observer.time.monotonic", side_effect=[100, 121]):
            with self.assertRaises(PermissionError):
                with self.profile():
                    pass
        self.assertFalse(self.report["profileRemoved"])

    def test_unrelated_error_is_immediately_reported(self):
        self.directory.cleanup.side_effect = OSError("unrelated cleanup failure")
        with self.assertRaisesRegex(OSError, "unrelated"):
            with self.profile():
                pass
        self.sleep.assert_not_called()
        self.assertFalse(self.report["profileRemoved"])

    def test_successful_cleanup_call_must_remove_the_directory(self):
        Path(self.directory.name).mkdir()
        with self.assertRaisesRegex(OSError, "still present"):
            with self.profile():
                pass
        self.assertFalse(self.report["profileRemoved"])

    def test_outer_handled_error_cannot_hide_a_cleanup_failure(self):
        self.directory.cleanup.side_effect = self.locked
        try:
            raise LookupError("already handled")
        except LookupError:
            with patch("windows_observer.time.monotonic", side_effect=[100, 121]):
                with self.assertRaises(PermissionError):
                    with self.profile():
                        pass
        self.assertFalse(self.report["profileRemoved"])
