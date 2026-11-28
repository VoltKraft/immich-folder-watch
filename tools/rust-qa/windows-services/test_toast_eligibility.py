"""Exercise the deadline, native HRESULT, and counter ordering of the separate ARM64 trial."""

from copy import deepcopy
from itertools import count
import unittest
from unittest.mock import patch

import toast_eligibility as e


def observation(start, end, state, hr=0):
    return dict(beginQpc=start, endQpc=end, hresult=hr, state=state)


class NotificationEligibilityTests(unittest.TestCase):
    def waiting(self, states, *, valid_console=True):
        clock = [0.]
        report = dict(status="waiting", samples=[])
        history = []
        replies = iter(states)

        def sample():
            value = next(replies)
            return observation(int(clock[0] * 1000) + 1, int(clock[0] * 1000) + 2, value, 0 if value is not None else -1)

        def sleep(seconds):
            clock[0] += seconds

        accepted = e.wait_for_accepts(report, sample, lambda: valid_console,
                                      lambda: history.append(deepcopy(report)), lambda: clock[0], sleep)
        return accepted, report, history

    def test_only_actual_accepts_issues_permission_and_each_probe_is_retained(self):
        accepted, report, history = self.waiting([6, 2, 5])
        self.assertTrue(accepted)
        self.assertEqual([r["elapsedSeconds"] for r in report["samples"]], [0, 30, 60])
        self.assertEqual([r["state"] for r in report["samples"]], [6, 2, 5])
        self.assertEqual([r["status"] for r in history], ["waiting", "waiting", "accepts-notifications"])

    def test_nonzero_hresult_original_console_loss_and_exhausted_deadline(self):
        for states, available, outcome in [([None], True, "query-failed"), ([], False, "console-changed"),
                                           ((6 for _ in count()), True, "deadline")]:
            with self.subTest(status=outcome):
                accepted, report, history = self.waiting(states, valid_console=available)
                self.assertFalse(accepted)
                self.assertEqual(history[-1]["status"], outcome)
                if outcome == "deadline":
                    self.assertEqual((len(report["samples"]), report["samples"][-1]["elapsedSeconds"]), (131, 3900))
                elif outcome == "query-failed":
                    self.assertIsNone(report["samples"][-1]["state"])

    def test_replay_links_last_observed_eligible_state_to_later_original_sender(self):
        _, observed, _ = self.waiting([6, 5])
        waited = {**observed, "intervalSeconds": 30, "limitSeconds": 3900}
        trace = dict(samples=[observation(50000, 50002, 5)])
        self.assertTrue(e.accepted_wait(waited, trace))
        for index, change in [(0, {"state": 5}), (1, {"elapsedSeconds": 3901}), (1, {"elapsedSeconds": -1}),
                              (1, {"state": 6}), (1, {"endQpc": 70000}), (1, {"hresult": -1}), (1, {"beginQpc": 1})]:
            bad = deepcopy(waited)
            bad["samples"][index].update(change)
            with self.subTest(change=change):
                self.assertFalse(e.accepted_wait(bad, trace))

    def test_nearest_completed_queries_before_and_after_show_preserve_other_states(self):
        rows = [observation(44, 47, 6), observation(95, 98, 5), observation(100, 105, 4), observation(112, 114, 6),
                observation(145, 147, 5)]
        result = e.bracket(rows, (1000, 100, 110))
        self.assertEqual(result, dict(before=rows[1], overlapping=[rows[2]], after=rows[3], beforeMs=2, afterMs=2))

    def test_missing_far_unordered_or_unreadable_state_cannot_appear_as_eligible(self):
        before, after = observation(999, 1000, 5), observation(1050, 1052, 5)
        for changes in [[], [before], [after], [after, before], [observation(400, 999, 5), after],
                        [before, observation(1051, 1600, 5)], [before, {**after, "hresult": -1}],
                        [before, {**after, "state": None}]]:
            with self.subTest(rows=changes), self.assertRaises(ValueError):
                e.bracket(changes, (1000, 1001, 1020))
        refused = {**after, "state": None, "hresult": -1}
        self.assertIsNone(e.bracket([before, refused], (1000, 1001, 1020))["after"]["state"])

    def test_dedicated_wait_cannot_run_on_the_ordinary_job(self):
        with patch.object(e.toast_history, "request_identity"), patch.dict("os.environ", {
            "GITHUB_WORKFLOW": e.WORKFLOW, "GITHUB_JOB": "observe", "IFW_QA_TOAST_ELIGIBILITY": "wait",
            "IFW_QA_TOAST_POLICY": "permitted"}, clear=True):
            e.dedicated()
            for key, bad in [("GITHUB_WORKFLOW", "normal"), ("GITHUB_JOB", "build"),
                             ("IFW_QA_TOAST_ELIGIBILITY", "immediate"), ("IFW_QA_TOAST_POLICY", "original")]:
                with self.subTest(key=key), patch.dict("os.environ", {key: bad}), self.assertRaises(ValueError):
                    e.dedicated()
