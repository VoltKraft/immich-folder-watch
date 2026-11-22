"""Portable source, budget and resident-page classification checks for the Windows comparison."""
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import inputs
import measure
import residency
from scan_present import correlate

spec = importlib.util.spec_from_file_location("warm_builder", inputs.HERE / "build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WarmTests(unittest.TestCase):
    def test_timed_trial_requires_one_memory_usage_device_and_no_allocator_sampling(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "trial.log"
            device = ("GRAPHICS_MEMORY generation=1 hint=MemoryUsage\nGRAPHICS_READY generation=1\n"
                      "GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Mailbox, Fifo]\n"
                      "GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode=Mailbox latency=Some(1)\n")
            log.write_text(device)
            self.assertEqual(measure.measured_generation(log, "Mailbox")["memoryHint"], "MemoryUsage")
            for invalid in (device.replace("MemoryUsage", "Performance"), device + "GRAPHICS_READY generation=2\n",
                            device + "WGPU_ALLOCATOR unavailable\n"):
                log.write_text(invalid)
                with self.assertRaisesRegex(ValueError, "single warm MemoryUsage"):
                    measure.measured_generation(log, "Mailbox")
            for invalid in (device.replace("[Mailbox, Fifo]", "[Fifo]"), device.replace("Some(1)", "Some(2)"),
                            device.replace("mode=Mailbox", "mode=Fifo")):
                log.write_text(invalid)
                with self.assertRaisesRegex(ValueError, "supported presentation mode"):
                    measure.measured_generation(log, "Mailbox")

    def test_only_owned_non_tearing_presents_on_the_same_work_clock_can_supply_the_comparison(self):
        requests = [dict(action="reopen" if i % 2 == 0 else "close", issuedQpc=20 + 10 * i, responseQpc=25 + 10 * i)
                    for i in range(15)]
        inventory = dict(passes=[dict(firstFileQpc=10, lastFileQpc=200)], eligibleResponses=requests)
        # Every close overlaps one 4 ms present for 3 ms. Reopens share no present call.
        rows = [f"DXGI 42 7 0 0 {32 + 20 * i} {36 + 20 * i}" for i in range(7)]
        trace = "\n".join(["READY", "QPC 42 1000", *rows, "COMPLETE"])

        def read(text, mode="Mailbox"):
            return correlate(text, 42, 1000, [8, 205], inventory, mode)

        result = read(trace)
        self.assertEqual((result["successfulPresents"], result["presentP95Ms"]), (7, 4))
        self.assertEqual(result["actions"]["close"], dict(requests=7, requestsIntersectingPresent=7, longestPresentOverlapP95Ms=3))
        self.assertEqual(result["actions"]["reopen"]["requestsIntersectingPresent"], 0)
        self.assertEqual(read(trace.replace("42 7 0 0", "42 7 1 0"), "Fifo")["syncInterval"], 1)
        for invalid in (trace.replace("QPC 42", "QPC 7"), trace.replace("QPC 42 1000", "QPC 42 2000"),
                        trace.replace("DXGI 42", "DXGI 7"), trace.replace("42 7 0 0", "42 7 1 0"),
                        trace.replace("42 7 0 0", "42 7 0 512"), trace.replace("42 7 0 0", "42 7 0 1"),
                        trace.replace("32 36", "4 36"), trace.replace("COMPLETE", "TRACE_ERROR"),
                        "\n".join(["READY", "QPC 42 1000", *rows[:3], "COMPLETE"])):
            with self.assertRaises(ValueError):
                read(invalid)

    def test_staging_preserves_the_shared_inputs(self):
        if not (builder.GUI / "artifacts/text/egui").is_dir():
            self.skipTest("requires the reconstructed canonical GUI inputs")
        with tempfile.TemporaryDirectory() as temp:
            gui = builder.stage(Path(temp) / "stage")
            for name in ("Cargo.lock", "Cargo.toml", "src/windows_worker.rs", "src/fonts.rs", "src/linux.rs", "src/tray-icon.argb"):
                self.assertEqual(builder.sha(builder.GUI / name), builder.sha(gui / name))
            self.assertEqual(builder.sha(gui / "src/loop_wake.rs"), builder.sha(builder.HERE / "loop_wake.rs"))
            self.assertEqual(builder.sha(gui / "src/windows_present.rs"), builder.sha(builder.HERE / "windows_present.rs"))
            for name, digest in builder.ORIGINALS.items():
                self.assertEqual(builder.sha(builder.GUI / "src" / name), digest)
                self.assertNotEqual(builder.sha(gui / "src" / name), digest)

    def test_resident_pages_are_counted_once_with_image_ownership(self):
        api = Mock()
        def working(proc, blocks, size):
            blocks[0:5] = (4, 1 << 12, 2 << 12, 3 << 12 | 0x100, 4 << 12)
            return True
        def region(proc, address, output, size):
            result = output._obj
            result.base = (address // 4096) * 4096
            result.size, result.state = 4096, 0x1000
            result.kind = {4096: 0x20000, 8192: 0x20000, 12288: 0x1000000, 16384: 0x40000}[address]
            result.allocation = result.base
            return c.sizeof(residency.Region)
        def mapped(proc, address, buffer, size):
            buffer.value = r"\Device\HarddiskVolume3\Windows\System32\d3d10warp.dll"
            return len(buffer.value)
        handlers = {"GetSystemInfo": lambda data: data.__setitem__(1, 4096), "K32QueryWorkingSet": working,
                    "VirtualQueryEx": region, "K32GetMappedFileNameW": mapped}
        with patch("native.bind", side_effect=lambda lib, name, *_: handlers[name]):
            found = residency.sample(api, 123)
        self.assertEqual(found["regionBytes"], {"private": 8192, "image": 4096, "mapped": 4096})
        self.assertEqual(found["imageBytes"], {"d3d10warp.dll": 4096})
        self.assertEqual(found["residentBytes"], 16384)
        self.assertEqual(found["shareableBytes"], 4096)

    def test_old_host_or_changed_budget_cannot_supply_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            where = root / "artifacts/rust/windows-performance/native-x86_64-pc-windows-msvc"
            where.mkdir(parents=True)
            env = {"COMPUTERNAME": "fixture", "ImageVersion": "test"}
            trials = [{"metrics": {"idle_close_p95_ms": 4}}] * 3
            baseline = {"target": inputs.TARGETS[0], "candidateRevision": "rev", "guiBinarySha256": "cold",
                        "guiReceiptSha256": "receipt", "referenceRevision": measure.REFERENCE,
                        "referenceSourceSha256": measure.REFERENCE_SOURCE_SHA256}
            meta = {"run": "1234", "attempt": "1", "revision": "rev", "baseline": "cold", "baselineReceipt": "receipt"}
            (where / "inputs.json").write_text(json.dumps(baseline))
            fixed = {"sourceInputsSha256": inputs.sha(where / "inputs.json"), "reference": {"idle_close_p95_ms": 4},
                     "maximums": {"idle_close_p95_ms": 14.0}}
            budget = where / "reference-budget.json"
            budget.write_text(json.dumps(fixed))
            host = {"host": {"run": "1234", "attempt": "1", "computerIdSha256": hashlib.sha256(b"fixture").hexdigest(),
                             "runnerImage": "test"}, "budgetSha256": inputs.sha(budget), "trials": {"wpf": trials}}
            (where / "result.json").write_text(json.dumps(host))
            with patch.object(measure, "ROOT", root), patch.dict(os.environ, env):
                self.assertEqual(measure.reference(inputs.TARGETS[0], meta)[1], fixed)
                with self.assertRaisesRegex(ValueError, "matching frozen WPF"):
                    measure.reference(inputs.TARGETS[0], {**meta, "attempt": "2"})
                fixed["maximums"]["idle_close_p95_ms"] = 150
                budget.write_text(json.dumps(fixed))
                with self.assertRaisesRegex(ValueError, "matching frozen WPF"):
                    measure.reference(inputs.TARGETS[0], meta)

    def test_fifo_can_report_a_full_over_budget_control_but_cannot_pair_different_or_missing_work(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mailbox.json"
            values = {key: {"candidate": 22.0, "maximum": 14.0, "passed": False} for key in measure.METRICS}
            common = dict(target=inputs.TARGETS[0], run="test", attempt="1", revision="rev", binary="bin",
                          buildReceipt="build", referenceBudgetSha256="budget", observerInputs={}, trials=[{}] * 3,
                          inputs={"workload": {"files": 100000}}, comparison=values)
            fifo = dict(common, presentMode="Fifo", diagnosticControl=True)
            mailbox = dict(common, presentMode="Mailbox", diagnosticControl=False)
            path.write_text(json.dumps(mailbox))
            self.assertEqual(measure.paired_scan(path, fifo)["metrics"]["Fifo"]["scan_close_p95_ms"], values["scan_close_p95_ms"])
            with self.assertRaisesRegex(ValueError, "different inputs"):
                measure.paired_scan(path, dict(fifo, binary="different"))
            with self.assertRaisesRegex(ValueError, "eleven measured"):
                measure.paired_scan(path, dict(fifo, comparison={**values, "startup_ms": {"passed": None}}))
            with self.assertRaisesRegex(ValueError, "different WPF"):
                measure.paired_scan(path, dict(fifo, comparison={**values, "scan_close_p95_ms": {**values["scan_close_p95_ms"], "maximum": 20}}))


if __name__ == "__main__":
    unittest.main()
