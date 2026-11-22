"""Check the independent counter and HWND bindings of the diagnostic timeline."""
import unittest

from dispatch import correlate


def sample(single=True):
    requests, spans, presents = [], [], []
    def span(label, thread, start, end, hwnd=0, before=-1, after=-1, sampled=0):
        spans.append(f"DISPATCH {label} {thread} {start} {end} {hwnd} {before} {after} {sampled}")
    for i in range(6):
        t = 100 * i + 10
        requests.extend([dict(action="close", hwnd=9, issuedQpc=t, responseQpc=t + 6),
                         dict(action="reopen", hwnd=9, issuedQpc=t + 20, responseQpc=t + 42)])
        span("close-event", 5, t + 1, t + 7)
        span("hide", 5, t + 2, t + 4, 9, 1, 0, t + 5)
        span("pipe-open", 7, t + 21, t + 25)
        span("user-event", 5, t + 26, t + 56)
        span("open-dequeued", 5, t + 27, t + 27)
        span("show", 5, t + 32, t + 48, 9, 0, 1, t + 49)
        span("focus", 5, t + 50, t + 51)
        span("request-redraw", 5, t + 52, t + 53)
        if single:
            span("private-wake", 5, t + 54, t + 54)
        span("redraw-event", 5, t + 60, t + 75)
        presents.append(f"DXGI 42 5 0 0 {t + 69} {t + 72}")
    trace = "\n".join([f"DISPATCH_BEGIN 42 1000 {int(single)} {len(spans)} 0", *spans, "DISPATCH_END"])
    inventory = dict(guiPid=42, eligibleResponses=requests, allRequests=requests,
                     presentation=dict(guiPid=42, qpcFrequency=1000, firstPassBoundsQpc=[5, 600], successfulPresents=6))
    return trace, "\n".join(presents), inventory


class DispatchTests(unittest.TestCase):
    def test_pipe_ui_state_and_external_confirmation_use_their_independent_clocks(self):
        for single in (False, True):
            trace, dxgi, inventory = sample(single)
            report = correlate(trace, dxgi, inventory, single)
            self.assertEqual(report["presentsByUiCallback"], {"redraw-event": 6})
            self.assertEqual(report["activationsByUiCallback"], {"user-event": 6})
            self.assertEqual(report["privateWakeCallbacks"], 6 if single else 0)
            actions = report["actions"]["reopen"]
            timings = actions["durations"]
            self.assertEqual(timings["pipeToUiDequeueMs"]["median"], 6)
            self.assertEqual(timings["visibilityCallMs"]["p95"], 16)
            self.assertEqual(timings["explicitRedrawCallMs"]["median"], 1)
            self.assertEqual(timings["externalMinusVisibilitySampleMs"]["median"], -7)
            self.assertEqual(actions["responseBeforeNativeVisibilitySample"], 6)
            self.assertEqual(actions["nativeVisibilityBeforeAfter"], {"0-to-1": 6})

    def test_preserves_out_of_thread_presents_and_delayed_native_visibility_as_observed(self):
        trace, dxgi, inv = sample()
        lines = trace.splitlines()
        extra = [f"DISPATCH redraw-event 5 {t + 30} {t + 35} 0 -1 -1 0" for t in range(10, 600, 100)]
        lines[0] = f"DISPATCH_BEGIN 42 1000 1 {len(lines) - 2 + len(extra)} 0"
        lines[-1:-1] = extra
        report = correlate("\n".join(lines).replace(" 9 0 1 ", " 9 0 0 "), dxgi.replace("42 5", "42 7"), inv, True)
        self.assertEqual(report["presentsByUiCallback"], {"other-owned-thread": 6})
        self.assertEqual(report["actions"]["reopen"]["nativeVisibilityBeforeAfter"], {"0-to-0": 6})
        timings = report["actions"]["reopen"]["durations"]
        self.assertEqual(timings["uiCallbackWallMs"]["median"], 16)
        self.assertEqual(timings["redrawCallbackWallMs"]["median"], 5)

    def test_rejects_unmatched_mode_pid_thread_visibility_order_and_lost_spans(self):
        trace, dxgi, inv = sample()
        for bad in (trace.replace("DISPATCH_BEGIN 42", "DISPATCH_BEGIN 41"),
                    trace.replace("1000 1", "999 1"), trace.replace("1000 1", "1000 0"),
                    trace.replace(" 0\n", " 1\n", 1), trace.replace("DISPATCH_END", ""),
                    trace.replace("show 5", "show 7"), trace.replace(" 9 0 1 ", " 9 0 -1 "),
                    trace.replace(" 9 0 1 ", " 8 0 1 "), trace.replace("pipe-open 7", "pipe-open 5"),
                    trace.replace("open-dequeued 5 37 37", "open-dequeued 5 20 20")):
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                correlate(bad, dxgi, inv, True)
        for bad in (dxgi.replace("DXGI 42", "DXGI 99"), dxgi.replace("42 5", "42 0"),
                    dxgi.replace("5 0 0", "5 1 0"), dxgi.replace("5 0 0", "5 0 512"),
                    dxgi.split("\n", 1)[1]):
            with self.assertRaises(ValueError):
                correlate(trace, bad, inv, True)


if __name__ == "__main__":
    unittest.main()
