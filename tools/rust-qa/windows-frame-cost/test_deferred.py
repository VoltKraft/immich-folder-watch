"""Portable negative controls for the separate one-trial native frame readback."""
from pathlib import Path
import tempfile
import unittest

import deferred_case as native


class DeferredTests(unittest.TestCase):
    def test_retry_requires_one_present_on_its_own_process_and_thread(self):
        spans = [(8, 110, 120, 150)]
        requests = [dict(action="reopen", hwnd=615, responseQpc=107), dict(action="close", hwnd=615, issuedQpc=153)]

        def match(lines):
            return native.matched_presents(lines, 57, (100, 200), spans, requests)
        self.assertEqual(match(["DXGI 57 8 0 0 125 143"]), dict(firstInventory=1, afterObservedReopen=1))
        for rows in ([], ["DXGI 56 8 0 0 125 143"], ["DXGI 57 7 0 0 125 143"],
                     ["DXGI 57 8 0 512 125 143"], ["DXGI 57 8 0 0 119 143"],
                     ["DXGI 57 8 0 0 125 151"], ["DXGI 57 8 0 0 121 130", "DXGI 57 8 0 0 131 145"]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                match(rows)
        with self.assertRaises(ValueError):
            native.matched_presents([], 57, (200, 300), spans, requests)
        requests[1]["issuedQpc"] = 149
        with self.assertRaisesRegex(ValueError, "reopen"):
            match(["DXGI 57 8 0 0 125 143"])

    def test_gate_requires_independent_wait_policy_and_complete_ordered_samples(self):
        graphics = ("GRAPHICS_MEMORY generation=1 hint=MemoryUsage\nGRAPHICS_READY generation=1\n"
                    "GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Fifo, Mailbox]\n"
                    "GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode=Mailbox latency=Some(1)\n"
                    "GRAPHICS_DX12_WAIT generation=1 policy=DontWait\n")
        counts = "DEFERRED_FRAME signalled=5 timeouts=4 resumed=3 early_callbacks=1 dropped=0\n"
        completed = "DEFERRED_PRESENT 8 110 120 150\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subject.log"
            path.write_text(graphics + counts + completed)
            self.assertEqual(native.summary(path)[1], [(8, 110, 120, 150)])
            for invalid in (counts + completed + completed, counts.replace("dropped=0", "dropped=1"),
                            counts.replace("resumed=3", "resumed=5"), counts + completed.replace("110", "121")):
                path.write_text(graphics + invalid)
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    native.summary(path)
            path.write_text(graphics.replace("DontWait", "Wait") + counts)
            with self.assertRaisesRegex(ValueError, "waitable object"):
                native.summary(path)

    def test_idle_reopen_requires_both_positive_native_calibrations(self):
        for samples in ([], [1], [0, 2], [True, True], [1, 1, 2]):
            row = dict(presentation=dict(reopenControls=samples), metrics={})
            with self.subTest(samples=samples), self.assertRaisesRegex(ValueError, "idle control"):
                native.resource_samples(row)
