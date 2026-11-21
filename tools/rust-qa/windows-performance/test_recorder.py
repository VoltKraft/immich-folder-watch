"""Boundary checks for the predeclared budgets, frame controls and reference material."""
import json
from contextlib import ExitStack
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build
import metrics
import native
from run import present_counts
import scan
import subject


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

    def test_scan_requires_distinct_file_directory_and_active_input_evidence(self):
        rows = ["READY 42 wpf", "COUNTS 750000 2300000 0 0 0 0 0 0"]
        for sweep, offset in enumerate((100, 200000)):
            rows.extend(f"D {sweep} {d} {offset + (d * 1000)} 1000" for d in range(100))
            rows.extend(f"B {sweep} {offset + i * 32 + 1} {offset + i * 32 + 32} 32" for i in range(3125))
        trace = "\n".join([*rows, "COMPLETE"])
        actions = [dict(action="close" if i % 2 == 0 else "reopen", issuedQpc=1000 + i * 100,
                        responseQpc=1001 + i * 100, hwnd=1) for i in range(10)]
        past = dict(action="close", issuedQpc=100102, responseQpc=100110, hwnd=1)
        def read(text, events=actions, first=100105, pid=42):
            return scan.coverage(text, events, first, 300001, 10000, pid, "wpf")
        observed = read(trace, [*actions, past])
        self.assertEqual([r["distinctFiles"] for r in observed["passes"]], [100000, 100000])
        self.assertEqual(observed["eligibleResponses"], actions)
        for text in (trace.replace("D 0 10 10100 1000", "D 0 10 10100 999"),
                     trace.replace("D 1 0 200000 1000", "D 1 0 0 1000"),
                     trace.replace("D 1 0 200000 1000", "D 1 0 100099 1000"),
                     trace.replace("B 0 101 132 32", "B 0 101 132 31"),
                     trace.replace("2300000 0 0", "2300000 1 0"), trace + "\nDECODE_ERROR"):
            with self.assertRaises(ValueError):
                read(text)
        with self.assertRaisesRegex(ValueError, "Fewer than five"):
            read(trace, [*actions[:-1], past])
        with self.assertRaises(ValueError):
            read(trace, first=99999)
        with self.assertRaises(ValueError):
            read(trace, pid=99)
        # A request which finishes outside actual first-pass work cannot meet the sample minimum.
        with self.assertRaisesRegex(ValueError, "Fewer than five"):
            read(trace, [*actions[:-1], {**actions[-1], "responseQpc": 100109}])

    def test_only_complete_ordered_subject_lines_qualify(self):
        zero = "INVENTORY_COMPLETE files=100000 changed=100000 pass=0\n"
        one = "INVENTORY_COMPLETE files=100000 changed=0 pass=1"
        self.assertEqual(scan.completion_count(zero + one, "rust", "root"), 1)
        self.assertEqual(scan.completion_count(zero + one + "\n", "rust", "root"), 2)
        for wrong in (zero + one + "0\n", one + "\n" + zero, zero + zero, zero + one + " extra\n"):
            with self.assertRaises(ValueError):
                scan.completion_count(wrong, "rust", "root")
        marker = "time [Information] category: Persistent reconciliation for uploadNew queued 0 changed file(s) from root.\n"
        self.assertEqual(scan.completion_count(marker * 2, "wpf", "elsewhere"), 0)
        self.assertEqual(scan.completion_count(marker * 2, "wpf", "root"), 2)

    def test_marker_must_match_original_secret_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = "a" * 32
            (root / "inventory.owner").write_bytes(token.encode())
            scan.verify_marker(root / "trial", token)
            for bad in ("b" * 32, None):
                with self.assertRaises(ValueError):
                    scan.verify_marker(root / "trial", bad)
            (root / "inventory.owner").write_bytes(token.encode() + b"\n")
            with self.assertRaises(ValueError):
                scan.verify_marker(root / "trial", token)

    def test_native_ledger_rejects_failed_and_incomplete_operations(self):
        cpp = Path(scan.__file__).with_name("file-observer.cpp")
        compiler = shutil.which("c++") or shutil.which("cl")
        if compiler is None:
            self.skipTest("No C++ compiler is installed")
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "ledger.exe"
            if Path(compiler).name.lower() in ("cl", "cl.exe"):
                command = [compiler, "/nologo", "/std:c++17", "/DIFW_LEDGER_SELFTEST", str(cpp), "/Fe:" + str(exe)]
            else:
                command = [compiler, "-std=c++17", "-DIFW_LEDGER_SELFTEST", str(cpp), "-o", str(exe)]
            subprocess.run(command, check=True, cwd=tmp, capture_output=True)
            subprocess.run([str(exe)], check=True, cwd=tmp)

    def test_windows_staging_preserves_the_reviewed_inventory_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = subject.stage_workspace(Path(temp) / "project")
            old = (subject.ORIGINAL / "src/main.rs").read_text(encoding="utf-8")
            new = (worker / "src/main.rs").read_text(encoding="utf-8")
            inventory = lambda s: s[s.index("fn inventory("):s.index("fn offline_probe(")]
            self.assertEqual(inventory(old), inventory(new))
            for marker in ("fn main()", "Two immediate initial reconciliation passes"):
                self.assertIn(marker, new)
            self.assertEqual(subject.sha(worker / "Cargo.lock"), subject.LOCK_HASH)
            self.assertEqual(subject.sha(worker / "Cargo.toml"), subject.MANIFEST_HASH)
            self.assertIn("inventory_release()?;", new)

    def test_process_totals_follow_the_supervisor_and_its_verified_descendants(self):
        class Snapshot:
            def __init__(self):
                self.entries = {10: (2, "gui"), 11: (10, "worker"), 12: (11, "child"), 99: (2, "other")}
            def processes(self):
                return self.entries
            def open(self, flags, inherit, pid):
                return pid
            def close(self, handle):
                return True
            def process_identity(self, handle):
                return 100 * handle
            def exit_code(self, handle, result):
                result._obj.value = 259 if handle in self.entries else 0
                return True
            def usage(self, handle, *, working_set):
                return handle, handle * 2 if working_set else 0

        api = Snapshot()
        with ExitStack() as stack:
            tree = scan.SubjectTree(api, stack, 10, {10, 11})
            self.assertEqual(tree.usage(), (33, 66))
            self.assertEqual(set(tree.records), {10, 11, 12})
            del api.entries[12]
            self.assertEqual(tree.usage(), (33, 42))
            del api.entries[11]
            with self.assertRaises(ValueError):
                tree.usage()

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
