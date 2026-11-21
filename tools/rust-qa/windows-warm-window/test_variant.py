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

spec = importlib.util.spec_from_file_location("warm_builder", inputs.HERE / "build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WarmTests(unittest.TestCase):
    def test_timed_trial_requires_one_memory_usage_device_and_no_allocator_sampling(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "trial.log"
            device = "GRAPHICS_MEMORY generation=1 hint=MemoryUsage\nGRAPHICS_READY generation=1\n"
            log.write_text(device)
            self.assertEqual(measure.measured_generation(log)["memoryHint"], "MemoryUsage")
            for invalid in (device.replace("MemoryUsage", "Performance"), device + "GRAPHICS_READY generation=2\n",
                            device + "WGPU_ALLOCATOR unavailable\n"):
                log.write_text(invalid)
                with self.assertRaisesRegex(ValueError, "single warm MemoryUsage"):
                    measure.measured_generation(log)

    def test_staging_preserves_the_shared_inputs(self):
        if not (builder.GUI / "artifacts/text/egui").is_dir():
            self.skipTest("requires the reconstructed canonical GUI inputs")
        with tempfile.TemporaryDirectory() as temp:
            gui = builder.stage(Path(temp) / "stage")
            for name in ("Cargo.lock", "Cargo.toml", "src/windows_worker.rs", "src/fonts.rs", "src/linux.rs", "src/tray-icon.argb"):
                self.assertEqual(builder.sha(builder.GUI / name), builder.sha(gui / name))
            self.assertEqual(builder.sha(gui / "src/loop_wake.rs"), builder.sha(builder.HERE / "loop_wake.rs"))
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


if __name__ == "__main__":
    unittest.main()
