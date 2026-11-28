import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from native_tray import records
import tray_retry


class RefusedRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.token = "1" * 32
        self.owner = dict(pid=12, tid=15, hwnd="0x18", **{"class": "fixture receiver"})
        self.native = SimpleNamespace(witness=Mock(), desk=Mock(), token=self.token)
        self.native.witness.live.return_value = True
        self.native.desk.window.return_value = self.owner
        self.registration = dict(pid=12, hwnd=24, iconId=23, receiver=self.owner)
        self.proc = Mock()
        self.proc.poll.return_value = None
        self.clock = 0
        self.rect = Mock(return_value=dict(hresult=-1, rect=None))
        self.log = self.row("initial")

    def row(self, phase, added=0, version=0):
        return (f"TRAY_REGISTER phase={phase} pid=12 hwnd=24 id=23 token={self.token} "
                f"added={added} version4={version}\n")

    def run_readback(self, next_lines):
        pending = iter(next_lines)
        def advance(_):
            self.clock += 3
            self.log += next(pending, "")
        report = {"registration": self.registration}
        with patch.object(tray_retry.time, "monotonic", lambda: self.clock), patch.object(tray_retry.time, "sleep", advance):
            tray_retry.observe(self.native, self.proc, Mock(), lambda: self.log, report,
                               records=records, read_rect=self.rect)
        return report["afterRefusedAdd"]

    def test_refused_retries_return_the_independent_shell_reads(self):
        report = self.run_readback([self.row("retry"), self.row("retry")])
        self.assertEqual(report["end"], "two automatic retries observed")
        self.assertEqual([v["elapsedMs"] for v in report["observations"]], [3000, 6000])
        self.assertEqual(self.rect.call_count, 2)
        self.assertTrue(report["sameExplorerAtEnd"])

    def test_acknowledgement_and_rectangle_are_separate_observations(self):
        report = self.run_readback([self.row("retry", 1, 1)])
        self.assertEqual(report["end"], "v4 acknowledgement observed")
        self.assertLess(report["observations"][0]["independentIcon"]["hresult"], 0)

    def test_changed_shell_ends_the_original_retry_observation(self):
        report = self.run_readback(["TRAY_HOST pid=12 previous=44 current=55 previous_hwnd=16 current_hwnd=18\n" +
                                    self.row("recreate", 1, 1)])
        self.assertEqual(report["end"], "Shell change observed")
        self.rect.assert_not_called()

    def test_no_native_retry_times_out_without_a_new_request(self):
        report = self.run_readback([])
        self.assertEqual(report["end"], "observation deadline")
        self.assertEqual(report["observations"], [])

    def test_mismatched_receiver_or_owner_prevents_readback(self):
        with self.assertRaisesRegex(ValueError, "history changed"):
            self.run_readback([self.row("retry", 1, 1).replace("hwnd=24", "hwnd=26")])
        self.log = self.row("initial")
        self.native.desk.window.return_value = dict(self.owner, tid=16)
        report = self.run_readback([self.row("retry", 1, 1)])
        self.assertEqual(report["end"], "original Explorer or receiver unavailable")
        self.rect.assert_not_called()
