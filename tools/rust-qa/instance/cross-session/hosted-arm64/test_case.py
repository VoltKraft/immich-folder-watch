"""Portable controls for the dedicated two-logon participant."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import worker
from fixture import read
from standard import TEMPORARY


class TemporaryAccountTests(unittest.TestCase):
    def run_fixture(self, folder, qualifies, os_probe):
        config = {"mode": TEMPORARY}
        identity = {"sessionId": 0, "elevated": not qualifies}
        result = {}
        with (patch.object(worker, "own_identity", return_value=(config, None, "synthetic", identity)),
              patch.object(worker, "qualifies", return_value=qualifies),
              patch.object(worker, "basic_user") as fallback,
              patch("logon.current_logon", side_effect=os_probe) as observed,
              patch.object(worker, "participant", return_value=True) as participant):
            try:
                worker.run(folder, result)
            finally:
                fallback.assert_not_called()
                if not qualifies or isinstance(os_probe, Exception):
                    participant.assert_not_called()
                else:
                    participant.assert_called_once_with(folder, "scheduled")
                if not qualifies:
                    observed.assert_not_called()
        return result

    def test_admin_token_fails_without_a_fallback_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "ordinary user"):
                self.run_fixture(Path(directory), False, None)

    def test_failed_os_logon_identity_stops_before_the_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "wrong logon"):
                self.run_fixture(Path(directory), True, ValueError("wrong logon"))

    def test_matching_standard_user_reaches_the_unmodified_participant(self):
        evidence = {"wtsSessionId": 0, "logonType": 4}
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_fixture(Path(directory), True, lambda *args: evidence)
            self.assertTrue(result["passed"])
            self.assertEqual(result["osLogon"], evidence)
            self.assertEqual(read(Path(directory) / "scheduled-bootstrap.json")["sessionId"], 0)


if __name__ == "__main__":
    unittest.main()
