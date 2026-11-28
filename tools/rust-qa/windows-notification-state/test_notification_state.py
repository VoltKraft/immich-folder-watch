"""Exercise the Server 2022 state observer with a synthetic clock and Shell identity."""
import ctypes as c
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import notification_state as observe


EARLY = dict(taskbar_hwnd=10, taskbar_pid=11, taskbar_tid=12, taskbar_creation=13, taskbar_session=2,
             taskbar_desktop="Default", shell_hwnd=14, shell_pid=11, shell_tid=15, taskbar_present=True)


class NotificationStateTests(unittest.TestCase):
    def run_trial(self, outcomes, *, samples=None, limit_ms=120_000):
        clock = 1010
        sleeps = []
        def sleep(delay):
            nonlocal clock
            sleeps.append(delay)
            clock += round(delay * 1000)

        def query(output):
            hr, state = next(values)
            c.cast(output, c.POINTER(c.c_int32))[0] = state
            return hr

        values = iter(outcomes)
        host = EARLY | {"verified": True}
        read = Mock(return_value=host) if samples is None else Mock(side_effect=samples)
        report = {}
        with patch.object(observe, "LIMIT_MS", limit_ms):
            status = observe.observe(report, EARLY, read, query, lambda: clock, sleep)
        return status, sleeps, report["samples"]

    def test_only_quiet_time_waits_for_the_same_shell_to_accept_notifications(self):
        status, sleeps, rows = self.run_trial([(0, 6), (0, 6), (0, 5)])
        self.assertEqual((status, sleeps), ("accepts-notifications", [30, 30]))
        self.assertEqual([r["state"] for r in rows], [6, 6, 5])
        self.assertEqual([r["queryStartTick"] for r in rows], [1010, 31010, 61010])
        self.assertTrue(all(r["earlyHostComparison"] == "same-explorer-and-taskbar" and r["before"] == r["after"] for r in rows))

    def test_an_eligible_or_other_state_and_a_failed_query_return_immediately(self):
        for hr, state, expected in ((0, 5, "accepts-notifications"), (0, 1, "other-state"), (0, 7, "other-state"),
                                    (0, 99, "other-state"), (-2147467259, 6, "query-failed"), (1, 5, "query-failed")):
            with self.subTest(hr=hr, state=state):
                status, sleeps, rows = self.run_trial([(hr, state)])
                self.assertEqual((status, sleeps, rows[0]["hresult"]), (expected, [], hr))
                self.assertEqual(rows[0]["state"], state if hr == 0 else None)
        for hr, state, expected in ((0, 4, "other-state"), (-1, 6, "query-failed")):
            self.assertEqual(self.run_trial([(0, 6), (hr, state)])[:2], (expected, [30]))

    def test_quiet_deadline_caps_the_final_sleep(self):
        status, sleeps, rows = self.run_trial([(0, 6)] * 4, limit_ms=65_000)
        self.assertEqual((status, sleeps, len(rows)), ("quiet-time-deadline", [30, 30, 5], 4))
        status, sleeps, rows = self.run_trial([(0, 6)] * 130 + [(0, 5)], limit_ms=65 * 60_000)
        self.assertEqual((status, len(sleeps), sum(sleeps), len(rows)), ("accepts-notifications", 130, 3900, 131))

    def test_native_lookup_failure_retains_the_build_binding_and_error_for_later_observers(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "artifacts/rust/server-2022-notifications"
            directory.mkdir(parents=True)
            env = dict(ImageOS="win22", GITHUB_REPOSITORY="VoltKraft/immich-folder-watch", GITHUB_SHA="a"*40,
                       GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1")
            with (patch.dict(observe.os.environ, env), patch.object(observe, "ROOT", root),
                  patch.object(observe, "hosted", return_value=True), patch.object(observe, "verify_checkout", return_value={}),
                  patch.object(observe, "bind_build", side_effect=lambda *args: args[-1].update(earlyResultSha256="b"*64)),
                  patch.object(observe, "Win32", side_effect=OSError("Shell lookup unavailable")), patch("builtins.print")):
                observe.main()
            result = json.loads((directory / "notification-state.json").read_bytes())
            self.assertEqual((result["run"], result["earlyResultSha256"]), ("123", "b"*64))
            self.assertEqual((result["status"], result["stage"], result["error"]),
                             ("native-lookup-unavailable", "open-desktop-and-query-api", "Shell lookup unavailable"))

    def test_foreign_or_unverified_desktop_and_changed_explorer_cannot_authorize_wait_or_eligibility(self):
        original = EARLY | {"verified": True}
        for replacement in (original | {"verified": False}, original | {"shell_hwnd": 25},
                            original | {"taskbar_session": 3}, original | {"taskbar_creation": 17}):
            with self.subTest(replacement=replacement):
                status, sleeps, rows = self.run_trial([], samples=[replacement])
                self.assertEqual((status, sleeps), ("original-desktop-or-shell-unavailable", []))
                self.assertNotIn("hresult", rows[0])
                status, sleeps, rows = self.run_trial([(0, 5)], samples=[original, replacement])
                self.assertEqual((status, sleeps), ("original-desktop-or-shell-changed", []))
                self.assertEqual(rows[0]["state"], 5)


if __name__ == "__main__":
    unittest.main()
