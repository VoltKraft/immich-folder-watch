"""Boundary checks for the predeclared budgets, frame controls and reference material."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import build
import metrics
import native
from run import present_counts


class RecorderTests(unittest.TestCase):
    def test_three_trials_and_fixed_budgets(self):
        rows = [{"metrics": {"startup_ms": v, "visible_cpu_one_core_pct": 2.0, "hidden_present_per_second": 0.0,
                             "visible_working_set_mib": 130}} for v in (80, 100, 1000)]
        summary = metrics.summarize(rows)
        self.assertEqual(metrics.budgets(summary), {"startup_ms": 120., "visible_cpu_one_core_pct": 3.,
                         "hidden_present_per_second": .067, "visible_working_set_mib": 143.})
        del rows[0]["metrics"]["hidden_present_per_second"]
        self.assertNotIn("hidden_present_per_second", metrics.summarize(rows))
        with self.assertRaises(ValueError):
            metrics.summarize(rows[:2])
        self.assertEqual(metrics.p95([.1] * 7 + [8]), 8)
        self.assertIsNone(metrics.comparison({}, {})["startup_ms"]["passed"])
        self.assertFalse(metrics.comparison({"startup_ms": 120}, {"startup_ms": 121})["startup_ms"]["passed"])

    def test_interval_and_independent_reopen_controls(self):
        text = "READY\nP D3D9 10\nP D3D9 20\nP D3D9 25\nP D3D9 45\nCOMPLETE\n"
        spans, controls = {"visible": [20, 25], "hidden": [30, 40]}, [[10, 11], [45, 47]]
        rates, coverage = present_counts(text, spans, controls, 10)
        self.assertEqual(rates, {"visible_present_per_second": 2, "hidden_present_per_second": 0})
        self.assertEqual(coverage["idleCounts"], {"visible": 1, "hidden": 0})
        self.assertEqual(present_counts(text, spans, [[11, 12]], 10)[0], {})
        self.assertEqual(present_counts(text + "TRACE_ERROR 1\n", spans, controls, 10)[0], {})

    def test_reference_archive_and_pe_machine(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            archive = build.extract_reference(area / "source")
            self.assertEqual(len(archive), 64)
            self.assertTrue((area / "source/src/ImmichFolderWatch.App/App.xaml").is_file())
            self.assertEqual(json.loads((area / "source/global.json").read_text())["sdk"]["version"], "10.0.401")
            (area / "source/extra.cs").touch()
            with self.assertRaisesRegex(ValueError, "source tree has changed"):
                build.verify_reference(area / "source")
            mock = bytearray(134)
            mock[:2] = b"MZ"
            struct.pack_into("<I", mock, 60, 128)
            mock[128:132] = b"PE\0\0"
            struct.pack_into("<H", mock, 132, 0xaa64)
            (area / "mock").write_bytes(mock)
            self.assertEqual(build.pe_machine(area / "mock"), 0xaa64)

    def test_refuses_existing_product_profile_or_shortcut(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            local, startup = area / "Local", area / "Startup"
            local.mkdir()
            startup.mkdir()
            profile = local / "Immich Folder Watch"
            shortcut = startup / "Immich Folder Watch.lnk"
            with patch.object(native, "hosted", return_value=True), patch.object(
                    native, "known_folder", side_effect=lambda id: local if id.startswith("f1") else startup):
                for occupied in (profile, shortcut):
                    occupied.write_bytes(b"existing")
                    with self.assertRaises(ValueError), native.wpf_profile(area, "http://127.0.0.1:9"):
                        self.fail("Existing application data must refuse launch")
                    self.assertEqual(occupied.read_bytes(), b"existing")
                    occupied.unlink()


if __name__ == "__main__":
    unittest.main()
