"""Exercise native one-shot receipt interpretation without requiring a Windows desktop."""
import copy
import unittest

from frame_ready_trace import intervals, read_trace
from frame_ready_case import METRICS, job_resources, resource_metrics, scan_views

ROOT = dict(pid=11, tid=12, hwnd=130)
ROWS = [("arm", 3, 10, 10), ("input", 3, 15, 15), ("close", 3, 16, 16),
        ("cancel", 3, 17, 17), ("arm", 4, 32, 32), ("signal", 4, 35, 35),
        ("consume", 4, 36, 36), ("present", 4, 37, 46)]
REQUESTS = [dict(action=a, hwnd=130, issuedQpc=b, responseQpc=c) for a, b, c in
            (("close", 12, 20), ("reopen", 21, 31), ("close", 47, 50))]


def raw(rows=ROWS):
    return "\n".join([f"FRAME_READY_BEGIN pid=11 tid=12 hz=1000 count={len(rows)} dropped=0",
                      *(f"FRAME_READY {event} 1 {token} 130 {a} {b}" for event, token, a, b in rows),
                      "FRAME_READY_END immediate=9"])


def parse(text):
    return read_trace(text, ROOT, 1000)


def join(cycles, frames=((40, 42, 0),), active=REQUESTS):
    return intervals(cycles, frames, (5, 48), REQUESTS, active)


class ReadyTests(unittest.TestCase):
    def test_external_hide_and_reopened_dxgi_present_belong_to_their_pending_tokens(self):
        observations = parse(raw())
        self.assertEqual(observations["immediate"], 9)
        result = join(observations["cycles"])
        self.assertEqual(result["serviced"], [dict(token=3, issuedQpc=12, hiddenQpc=20, nativeCloseQpc=16, cancelledQpc=17)])
        self.assertEqual(result["visibleResumes"], [dict(token=4, visibleQpc=31, signalQpc=35, beginQpc=40, endQpc=42)])

    def test_stale_reordered_or_incomplete_kernel_evidence_is_invalid(self):
        source = raw()
        for good, bad in [("pid=11", "pid=10"), ("tid=12", "tid=5"), ("hz=1000", "hz=123"), ("count=8", "count=7"),
                          ("dropped=0", "dropped=1"), ("input 1 3 130", "input 1 3 132"), (" 1 3 130 16 16", " 2 3 130 16 16"),
                          ("signal 1 4", "signal 1 3"), (" 16 16", " 12 12"), ("cancel 1 3", "arm 1 3"),
                          ("consume 1 4", "signal 1 4"), ("present 1 4", "input 1 4"), ("arm 1 4", "arm 1 3"),
                          ("FRAME_READY_END", "ERROR")]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse(source.replace(good, bad))
        with self.assertRaises(ValueError):
            parse(raw(ROWS[:-1]))

    def test_input_return_alone_or_close_after_the_grant_never_proves_window_service(self):
        after_grant = [*ROWS[:2], ("signal", 3, 16, 16), ROWS[3], ("reuse", 4, 36, 36), ROWS[7]]
        r = join(parse(raw(after_grant))["cycles"])
        self.assertEqual((len(r["opportunities"]), r["serviced"]), (1, []))
        with self.assertRaises(ValueError):
            parse(raw([*after_grant[:3], ("close", 3, 16, 16), *after_grant[3:]]))
        for idx, times in ((2, (11, 11)), (3, (21, 21))):
            variant = list(ROWS)
            if idx == 2:
                variant[1] = ("input", 3, 11, 11)
            variant[idx] = (*variant[idx][:2], *times)
            self.assertEqual(join(parse(raw(variant))["cycles"])["serviced"], [])
        self.assertEqual(join(parse(raw())["cycles"], active=[])["serviced"], [])

    def test_reused_credit_requires_prior_grant_and_is_reported_separately(self):
        rows = [("arm", 3, 10, 10), ("signal", 3, 11, 11), ("cancel", 3, 17, 17),
                ("reuse", 4, 35, 35), ("present", 4, 37, 46)]
        out = join(parse(raw(rows))["cycles"])
        self.assertEqual((out["serviced"], out["visibleResumes"]), ([], []))
        self.assertEqual((out["visibleReuse"][0]["originalGrant"], out["visibleReuse"][0]["hiddenQpc"]), (3, 20))
        # A signal after the externally observed hide cannot prove credit survived that hide.
        late = [("arm", 3, 21, 21), ("signal", 3, 22, 22), ("cancel", 3, 24, 24), *rows[3:]]
        self.assertEqual(join(parse(raw(late))["cycles"])["visibleReuse"], [])
        for bad in (rows[3:], [*rows[:2], ("consume", 3, 12, 12), ("present", 3, 14, 16), *rows[3:]],
                    [rows[0], rows[2], *rows[3:]], [*rows[:3], ("arm", 4, 35, 35)]):
            with self.assertRaises(ValueError):
                parse(raw(bad))
        with self.assertRaises(ValueError):
            parse(raw(rows).replace("reuse 1 4", "reuse 2 4"))

    def test_missing_ambiguous_or_wrong_interval_dxgi_is_rejected(self):
        for events in [[], [(40, 50, 0)], [(33, 40, 0)], [(40, 42, 1)], [(39, 40, 0), (42, 44, 0)]]:
            with self.subTest(events=events), self.assertRaises(ValueError):
                join(parse(raw())["cycles"], events)

    def test_visibility_receipts_bind_each_side_to_original_hwnd_and_native_qpc(self):
        views = [dict(hwnd=130, phase=p, action=q["action"], visible=(q["action"]=="close") == (p=="before"),
                      qpc=t) for q in REQUESTS for p,t in (("before", q["issuedQpc"]-1), ("after", q["responseQpc"]))]
        scan_views(views, REQUESTS, 130)
        for i,k,v in [(0,"hwnd",55),(0,"qpc",14),(1,"visible",True),(3,"action","close")]:
            altered = copy.deepcopy(views)
            altered[i][k] = v
            with self.assertRaises(ValueError):
                scan_views(altered, REQUESTS, 130)

    def test_nonzero_idle_etw_rate_is_preserved_for_the_budget_outcome(self):
        metrics = {k: 1 for k in METRICS}
        sample = dict(seconds=15, samples=[1], working_set_mib=1, cpu_one_core_pct=1)
        row = dict(metrics=metrics, presentation=dict(reopenControls=[2, 2], idleCounts=dict(visible=15, hidden=15)),
                   controls=dict(successfulVisibilityCycles=8), termination=dict(method="control-Q", exitCode=0),
                   idleVisibilityMs=dict(close=[1] * 8, reopen=[1] * 8), idleSamples=dict(visible=sample, hidden=sample))
        resource_metrics(row)
        self.assertEqual(metrics["hidden_present_per_second"], 1)
        row["presentation"]["reopenControls"] = [0, 1]
        with self.assertRaises(ValueError):
            resource_metrics(row)

    def test_idle_cpu_and_full_working_set_are_recalculated_from_original_job(self):
        pts = [dict(cpu100ns=t, workingSetBytes={11:1048576, 22:2097152}, totalProcesses=3, membershipAttempts=1)
               for t in (5_000_000, 10_000_000)]
        sample = dict(seconds=20, samples=[3.0], jobSamples=pts, cpu_one_core_pct=2.5)
        job_resources(sample, 11, 22, {11, 22, 33})
        # A previous member may have exited. Unknown PIDs cannot replace its memory.
        with_helper = copy.deepcopy(sample)
        with_helper["jobSamples"][0]["workingSetBytes"][33] = 80
        job_resources(with_helper, 11, 22, {11, 22, 33})
        with self.assertRaises(ValueError):
            job_resources(with_helper, 11, 22, {11, 22})
        for key,value in (("cpu100ns",3), ("workingSetBytes",{11:3145728}), ("membershipAttempts",9), ("totalProcesses",1)):
            altered = copy.deepcopy(sample)
            altered["jobSamples"][1][key] = value
            with self.assertRaises(ValueError):
                job_resources(altered, 11, 22, {11, 22, 33})


if __name__ == "__main__":
    unittest.main()
