"""Boundary checks for the predeclared budgets, frame controls and reference material."""
import json
from contextlib import ExitStack
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import uuid

import build
import metrics
import native
from run import present_counts
import scan
import subject


def remove_ledger_image(api, exe, original, timeout=10):
    """Wait for the exited self-test image to be deletable inside its still-pinned directory."""
    if exe.name != "ledger.exe" or not re.fullmatch("ifw-rw02-[0-9a-f]{32}", exe.parent.name):
        raise ValueError("Expected the fixed compiler output in its private test directory")
    deadline = time.monotonic() + timeout
    deletion_requested = False
    while True:
        try:
            handle = api.path_handle(exe, False, delete=True)
            try:
                attributes, identity = api.file_info(handle)
                if identity != original or attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x10):
                    raise native.CleanupUnconfirmed("The ledger image identity or type changed before removal")
                api.delete_handle(handle)
                deletion_requested = True
            finally:
                native.checked(api.close(handle))
        except OSError as error:
            code = getattr(error, "winerror", None)
            if code == 2 and deletion_requested:
                return
            if code not in (5, 32, 33):
                raise native.CleanupUnconfirmed("Could not confirm removal of the original ledger image") from error
        if time.monotonic() >= deadline:
            raise native.CleanupUnconfirmed("The original ledger image was still in use at the cleanup deadline")
        time.sleep(.05)


class RecorderTests(unittest.TestCase):
    def test_failed_search_for_a_second_receiver_cannot_identify_a_unique_window(self):
        find, owner = Mock(side_effect=[73, None]), Mock()
        with patch.object(native.c, "WinDLL", create=True), patch.object(native, "bind", side_effect=[find, owner]), \
             patch.object(native.c, "set_last_error", create=True) as clear, \
             patch.object(native.c, "get_last_error", return_value=1400, create=True), self.assertRaises(OSError) as exc:
            native.wpf_tray_receiver(27)
        self.assertEqual(exc.exception.errno, 1400)
        clear.assert_called_once_with(0)
        self.assertEqual([args.args[1] for args in find.call_args_list], [None, 73])
        owner.assert_not_called()

    def test_wpf_tray_lookup_requires_same_live_receiver_and_nonempty_shell_rect(self):
        api, proc = Mock(), Mock(pid=27)
        api.process_identity.return_value = 789
        receiver = (73, 8)
        for after, exit_code, raw, expected in (
                (receiver, None, {"hresult": 0, "rect": [1, 2, 3, 4]}, "rectangle-returned"),
                (receiver, None, {"hresult": -2147467259, "rect": None}, "no-rectangle"),
                (receiver, None, {"hresult": 0, "rect": [2, 2, 2, 8]}, "no-rectangle"),
                ((73, 9), None, {"hresult": 0, "rect": [1, 2, 3, 4]}, "receiver-changed"),
                (receiver, 0, {"hresult": 0, "rect": [1, 2, 3, 4]}, "receiver-changed")):
            with self.subTest(expected=expected, raw=raw, exit_code=exit_code):
                api.clock.side_effect = [36, 41]
                proc.poll.side_effect = [None, exit_code]
                with patch.object(native, "wpf_tray_receiver", side_effect=[receiver, after]), \
                     patch.object(native, "shell_icon_rect", return_value=raw) as query:
                    result = native.observe_wpf_tray(api, proc, 6)
                query.assert_called_once_with(73, 1)
                self.assertEqual((result["status"], result["query"], result["queryStartQpc"], result["queryEndQpc"]),
                                 (expected, raw, 36, 41))
        proc.poll.side_effect = [None]
        with patch.object(native, "wpf_tray_receiver", return_value=None), patch.object(native, "shell_icon_rect") as query:
            self.assertEqual(native.observe_wpf_tray(api, proc, 6)["status"], "receiver-unavailable")
            query.assert_not_called()

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
        with ExitStack() as stack:
            if os.name == "nt":
                api = native.Win32()
                parent = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()).resolve(strict=True)
                tmp = stack.enter_context(native.owned_directory(api, parent, "ifw-rw02-" + uuid.uuid4().hex))
            else:
                tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            exe = tmp / "ledger.exe"
            if Path(compiler).name.lower() in ("cl", "cl.exe"):
                command = [compiler, "/nologo", "/std:c++17", "/DIFW_LEDGER_SELFTEST", str(cpp), "/Fe:" + str(exe)]
            else:
                command = [compiler, "-std=c++17", "-DIFW_LEDGER_SELFTEST", str(cpp), "-o", str(exe)]
            compiler_env = {**os.environ, "CCACHE_DISABLE": "1", "CCACHE_DIR": str(tmp / "ccache"),
                            "TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp)}
            subprocess.run(command, check=True, cwd=tmp, env=compiler_env, capture_output=True, timeout=90)
            if os.name == "nt":
                with native.pin_path(api, exe, False) as (_, original):
                    # ExitStack performs cleanup after the deny-delete image handle has closed.
                    stack.callback(remove_ledger_image, api, exe, original)
                    subprocess.run([str(exe)], check=True, cwd=tmp, timeout=30)
            else:
                subprocess.run([str(exe)], check=True, cwd=tmp, timeout=30)

    def test_ledger_cleanup_retries_only_its_pinned_id_and_requires_removal(self):
        def windows_error(code):
            exc = OSError("Windows test error")
            exc.winerror = code
            return exc
        exe = Path("ifw-rw02-" + "a" * 32) / "ledger.exe"
        api = Mock()
        api.path_handle.side_effect = [windows_error(5), windows_error(32), 41, windows_error(2)]
        api.file_info.return_value = 0x80, (3, 9)
        with patch("time.sleep"):
            remove_ledger_image(api, exe, (3, 9))
        api.delete_handle.assert_called_once_with(41)
        api.close.assert_called_once_with(41)
        for call in api.path_handle.call_args_list:
            self.assertEqual(call.args, (exe, False))
            self.assertEqual(call.kwargs, {"delete": True})
        for code in (2, 5, 87):
            api.reset_mock()
            api.path_handle.side_effect = windows_error(code)
            with self.subTest(code=code), self.assertRaises(native.CleanupUnconfirmed):
                remove_ledger_image(api, exe, (3, 9), timeout=0)
            api.delete_handle.assert_not_called()
        for facts in ((0x80, (3, 10)), (stat.FILE_ATTRIBUTE_REPARSE_POINT, (3, 9))):
            api.reset_mock()
            api.path_handle.side_effect = [42]
            api.file_info.return_value = facts
            with self.assertRaisesRegex(native.CleanupUnconfirmed, "identity or type"):
                remove_ledger_image(api, exe, (3, 9))
            api.delete_handle.assert_not_called()
            api.close.assert_called_once_with(42)

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

    def test_inventory_staging_requires_the_exact_reviewed_filesystem(self):
        reviewed = json.loads(subject.WORKER_PROFILE.read_text(encoding="utf-8"))
        entry = "rust/crates/safe-fs/src/lib.rs"
        wrong_hash = {**reviewed, entry: "0" * 64}
        missing = {name: digest for name, digest in reviewed.items() if name != entry}
        extra = {**reviewed, "rust/crates/safe-fs/src/extra.rs": "0" * 64}
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "worker-inputs.json"
            project = Path(temp) / "project"
            for label, changed in (("changed", wrong_hash), ("missing", missing), ("extra", extra)):
                with self.subTest(label=label), patch.object(subject, "WORKER_PROFILE", profile):
                    profile.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "reviewed worker profile"):
                        subject.stage_workspace(project)
                    self.assertFalse(project.exists())

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
