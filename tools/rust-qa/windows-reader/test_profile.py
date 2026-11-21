import os
import unittest
from unittest.mock import Mock, patch

from run import private_profile


class ReaderProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = Mock(name="temporary directory")
        self.directory.name = "synthetic-reader"
        self.locked = PermissionError(13, "in use", "helper.dll")
        self.report = {}
        self.enterContext(patch.dict(os.environ, RUNNER_TEMP="synthetic"))
        self.enterContext(patch("run.tempfile.TemporaryDirectory", return_value=self.directory))
        self.enterContext(patch("run.time.sleep"))

    def test_retries_a_transient_owned_module_lock(self):
        self.directory.cleanup.side_effect = [self.locked, None]
        with private_profile(self.report):
            pass
        self.assertEqual(self.directory.cleanup.call_count, 2)
        self.assertEqual(self.report, {"profileRemoved": True})

    def test_persistent_lock_keeps_the_original_observation_failure(self):
        self.directory.cleanup.side_effect = self.locked
        with patch("run.time.monotonic", side_effect=[100, 121]):
            with self.assertRaisesRegex(RuntimeError, "missing utterance"):
                with private_profile(self.report):
                    raise RuntimeError("missing utterance")
        self.assertEqual(self.report, {"profileRemoved": False, "cleanupLockedFile": "helper.dll"})

    def test_cleanup_failure_after_a_successful_observation_fails_the_run(self):
        self.directory.cleanup.side_effect = self.locked
        with patch("run.time.monotonic", side_effect=[100, 121]):
            with self.assertRaises(PermissionError):
                with private_profile(self.report):
                    pass
        self.assertFalse(self.report["profileRemoved"])
