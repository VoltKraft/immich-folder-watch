"""Check evidence qualification without substituting test data for Windows observations."""

import ctypes as c
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import zlib

DRIVER = runpy.run_path(str(Path(__file__).with_name("run.py")))
from topology import DisplayPath, Mode, Source, Target, Topology, active_input


def png(path, width, height, changed):
    def block(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = b"".join(b"\0" + b"".join((b"\xee" if changed and x < 8 and y < 4 else b"\x10") * 3
                                  for x in range(width)) for y in range(height))
    raw = b"\x89PNG\r\n\x1a\n" + block(b"IHDR", header) + block(b"IDAT", zlib.compress(data)) + block(b"IEND", b"")
    path.write_bytes(raw)
    return {"width": width, "height": height, "sha256": hashlib.sha256(raw).hexdigest()}


class DisplayTests(unittest.TestCase):
    def source_desktop(self, hit, *, topmost=False, expose=True):
        api = Mock()
        self.enterContext(patch.object(c, "set_last_error", create=True))
        self.enterContext(patch.object(c, "get_last_error", create=True, return_value=0))
        state = {"hit": hit, "topmost": topmost}
        def owner(window, out):
            out._obj.value = {100: 42, 101: 42, 200: 43}.get(window, 0)
            return int(out._obj.value != 0)
        def order(window, pid, value):
            self.assertEqual((window, pid), (100, 42))
            state["topmost"] = value
            if value and expose:
                state["hit"] = 101
            return True
        api.owner.side_effect = owner
        api.point_window.side_effect = lambda _: state["hit"]
        api.ancestor.side_effect = lambda h, _: 100 if h == 101 else h
        api.style.side_effect = lambda *_: 8 if state["topmost"] else 0
        api.order_subject.side_effect = order
        return api

    def test_only_a_covered_owned_subject_is_raised_and_original_band_returns_on_failure(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                api = self.source_desktop(200)
                proof = {}
                def observe():
                    with DRIVER["source_field_order"](api, 100, 42, [11.5, 40, 50, 61], lambda: True, proof):
                        self.assertEqual(proof["pointAfterRaise"], "subject")
                        self.assertEqual(proof["point"], [31, 50])
                        if failed:
                            raise ValueError("fixture observer exited")
                if failed:
                    with self.assertRaisesRegex(ValueError, "observer exited"):
                        observe()
                else:
                    observe()
                self.assertEqual(api.order_subject.call_args_list, [call(100, 42, True), call(100, 42, False)])
                self.assertIs(proof["bandRestored"], True)

    def test_visible_missing_or_already_topmost_points_keep_the_original_band(self):
        for point, topmost, classification in ((101, False, "subject"), (0, False, "unavailable"), (200, True, "other")):
            with self.subTest(point=point, topmost=topmost):
                api = self.source_desktop(point, topmost=topmost)
                proof = {}
                with DRIVER["source_field_order"](api, 100, 42, [5, 10, 25, 20], lambda: True, proof):
                    self.assertEqual(proof["initialPointOwner"], classification)
                api.order_subject.assert_not_called()

    def test_lost_hwnd_or_failed_style_read_cannot_confirm_band_restoration(self):
        for cause in ("lost-owner", "read-error"):
            with self.subTest(cause=cause):
                api = self.source_desktop(200)
                normal_order = api.order_subject.side_effect
                def order(hwnd, pid, topmost):
                    result = normal_order(hwnd, pid, topmost)
                    if not topmost:
                        if cause == "lost-owner":
                            api.owner.side_effect = None
                            api.owner.return_value = 0
                        else:
                            c.get_last_error.return_value = 1400
                    return result
                api.order_subject.side_effect = order
                proof = {}
                with self.assertRaises((RuntimeError, OSError)):
                    with DRIVER["source_field_order"](api, 100, 42, [5, 10, 25, 20], lambda: True, proof):
                        pass
                self.assertIs(proof["bandRestored"], False)

    def test_changed_input_session_or_subject_cannot_receive_the_order_request(self):
        for pid, availability in ((99, [True]), (42, [False]), (42, [True, False]), (42, [True, True, False])):
            with self.subTest(pid=pid, availability=availability):
                api = self.source_desktop(200)
                proof = {}
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    with DRIVER["source_field_order"](api, 100, pid, [5, 10, 25, 20], Mock(side_effect=availability), proof):
                        self.fail("The observer ran on a changed desktop")
                if len(availability) == 3:
                    self.assertIs(proof["bandRestored"], True)
                else:
                    api.order_subject.assert_not_called()

    def test_display_and_text_import_the_hash_used_by_the_field_capture(self):
        shell = (Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                 if os.name == "nt" else shutil.which("pwsh"))
        if not shell:
            self.skipTest("PowerShell is required for the shared capture imports")
        qa = Path(__file__).resolve().parents[1]
        driver = """
$ErrorActionPreference = 'Stop'
$env:PSModulePath = $env:IFW_EMPTY_MODULES
$PSModuleAutoloadingPreference = 'None'
if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) { throw 'Expected an isolated module path' }
function Parse-Observer([string]$path) {
    $errors = $null
    $tree = [Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
    if ($errors.Count) { throw $errors[0] }
    return $tree
}
$ast = Parse-Observer $env:IFW_SHARED_CAPTURE
$imports = @((Parse-Observer $env:IFW_CAPTURE_CONSUMER).FindAll({ param($n)
    $n -is [Management.Automation.Language.ForEachStatementAst] -and
    $n.Condition.Extent.Text.Contains("'Capture-SubjectField'")
}, $true))
if ($imports.Count -ne 1) { throw 'Missing the capture import in the observer' }
. ([scriptblock]::Create($imports[0].Extent.Text))
$capture = (Get-Command Capture-SubjectField -CommandType Function).ScriptBlock.Ast
$hash = $capture.Find({ param($n)
    $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-FieldPngHash'
}, $true)
# Isolate the saved file digest from the UIA and screen operations in this imported capture.
if ($hash) { . ([scriptblock]::Create($hash.Extent.Text)) }
$calls = @($capture.FindAll({ param($n)
    $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -ceq 'Get-FieldPngHash'
}, $true))
if ($calls.Count -ne 1) { throw 'Expected the saved PNG digest in the imported capture' }
$png = $env:IFW_SAMPLE_PNG
& ([scriptblock]::Create($calls[0].Extent.Text))
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "source [frame].png"
            expected = png(path, 32, 10, True)["sha256"]
            modules = root / "modules"
            modules.mkdir()
            env = dict(os.environ, IFW_SHARED_CAPTURE=str(qa / "observe-windows-input.ps1"),
                       IFW_SAMPLE_PNG=str(path),
                       IFW_EMPTY_MODULES=str(modules), PSModulePath=str(modules), POWERSHELL_TELEMETRY_OPTOUT="1")
            if os.name != "nt":
                for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
                    env[key] = str(root / key)
            for consumer in ("windows-display/field.ps1", "windows-text/observe.ps1"):
                with self.subTest(consumer=consumer):
                    proc = subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", driver],
                                          cwd=root, env=dict(env, IFW_CAPTURE_CONSUMER=str(qa / consumer)),
                                          capture_output=True, text=True, timeout=30)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stdout.splitlines(), [expected])

    def test_remote_input_uses_the_own_active_unlocked_session(self):
        context = {"session": 3, "activeConsoleSession": 1, "windowStation": "WinSta0", "stationVisible": True,
                   "inputDesktop": "Default", "threadDesktop": "Default", "threadReceivesInput": True,
                   "inputObjectReceivesInput": True, "wts": {"session": 3, "connectionState": 0, "lockFlags": 1}}
        rdp = {"code": 2, "status": "observed"}
        self.assertTrue(active_input(context, rdp))
        self.assertFalse(active_input(context, {"code": 0, "status": "observed"}))
        self.assertFalse(active_input(context, {"status": "unavailable"}))
        for key, value in (("inputDesktop", "Winlogon"), ("threadReceivesInput", False), ("stationVisible", False),
                           ("wts", {"session": 3, "connectionState": 0, "lockFlags": 0})):
            self.assertFalse(active_input({**context, key: value}, rdp))
        self.assertTrue(active_input({**context, "activeConsoleSession": 3}, {"code": 0, "status": "observed"}))

    def test_one_monitor_or_equal_dpi_cannot_create_a_target(self):
        first = {"handle": "0x1", "dpi": 96}
        same = {"handle": "0x2", "dpi": 96}
        other = {"handle": "0x3", "dpi": 120}
        for rows in ([first], [first, same]):
            self.assertEqual(DRIVER["choose_monitor"]({"monitors": rows}, "0x1"), (first, None))
        self.assertEqual(DRIVER["choose_monitor"]({"monitors": [other, same, first]}, "0x2"), (same, other))
        with self.assertRaises(ValueError):
            DRIVER["choose_monitor"]({"monitors": [first]}, "other")

    def test_query_display_config_abi_and_remote_access_errors(self):
        self.assertEqual([c.sizeof(t) for t in (Source, Target, DisplayPath, Mode)], [20, 48, 72, 64])
        self.assertEqual([DisplayPath.target.offset, DisplayPath.flags.offset, Mode.data.offset], [20, 68, 16])
        native = Topology.__new__(Topology)
        for code, status in ((5, "unavailable"), (50, "unavailable"), (87, "failed")):
            native.buffer_sizes = lambda *_: code
            for all_targets in (False, True):
                self.assertEqual(native.display_paths({}, all_targets=all_targets),
                                 {"status": status, "api": "GetDisplayConfigBufferSizes", "win32": code})

    def test_active_paths_retry_and_join_the_queried_source_monitor(self):
        native = Topology.__new__(Topology)
        def sizes(flags, count, modes):
            self.assertEqual(flags, 2)
            count._obj.value = modes._obj.value = 1
            return 0
        calls = []
        def query(flags, count, rows, mode_count, modes, topology_id):
            self.assertIsNone(topology_id)
            calls.append(flags)
            if len(calls) == 1:
                return 122
            rows[0].source.id = modes[0].id = 4
            rows[0].target.id, rows[0].flags, modes[0].type = 7, 1, 1
            modes[0].data.source.width, modes[0].data.source.height = 1440, 900
            return 0
        def source_name(ptr):
            ptr._obj.device = "DISPLAY3"
            return 0
        native.buffer_sizes, native.query, native.source_name = sizes, query, source_name
        rows = native.display_paths({"display3": 2})["paths"]
        self.assertEqual(calls, [2, 2])
        self.assertEqual((rows[0]["monitor"], rows[0]["sourceMode"], rows[0]["active"]), (2, [0, 0, 1440, 900], True))

    def test_all_paths_count_distinct_adapter_targets_and_record_inactive_availability(self):
        native = Topology.__new__(Topology)
        def sizes(flags, paths, modes):
            self.assertEqual(flags, 1)
            paths._obj.value, modes._obj.value = 4, 1
            return 0
        def query(flags, count, paths, mode_count, modes, topology_id):
            self.assertEqual(flags, 1)
            self.assertIsNone(topology_id)
            rows = [(0, 7, True, True), (0, 7, False, True), (1, 7, False, True), (1, 8, False, False)]
            for path, (adapter, target_id, active, available) in zip(paths, rows):
                path.target.adapter.low, path.target.id = adapter, target_id
                path.flags, path.target.available = int(active), int(available)
            return 0
        native.buffer_sizes, native.query = sizes, query
        report = native.display_paths({}, all_targets=True)
        self.assertEqual(report["pathCount"], 4)
        self.assertEqual([(r["adapterLuid"], r["targetId"], r["active"], r["available"]) for r in report["targets"]],
                         [([0, 0], 7, True, True), ([0, 1], 7, False, True), ([0, 1], 8, False, False)])
        def large_inventory(flags, count, modes):
            count._obj.value, modes._obj.value = 10000, 1
            return 0
        native.buffer_sizes = large_inventory
        self.assertEqual(native.display_paths({}, all_targets=True)["status"], "unavailable")

    def test_explicit_qualification_cannot_pass_on_inventory_or_a_console_frame(self):
        required = ["mixed-dpi", "rdp"]
        report = {"inventoryPassed": True, "sourceFrameObserved": True,
                  "rdpSessionObserved": False, "rdpRenderingObserved": None, "mixedDpiPassed": None}
        missing = DRIVER["unmet_qualifications"]
        self.assertEqual(missing(report, required), required)
        self.assertEqual(missing(report, ["source-frame"]), [])
        self.assertEqual(missing({**report, "sourceFrameObserved": False}, ["source-frame"]), ["source-frame"])
        rdp = {**report, "rdpSessionObserved": True, "rdpRenderingObserved": False}
        self.assertEqual(missing(rdp, ["rdp"]), ["rdp"])
        self.assertEqual(missing({**rdp, "rdpRenderingObserved": True}, required), ["mixed-dpi"])
        self.assertEqual(missing({**rdp, "mixedDpiPassed": True}, required), ["rdp"])
        self.assertEqual(missing({**rdp, "mixedDpiPassed": True, "rdpRenderingObserved": True}, required), [])

    def test_moved_cpu_field_requires_a_new_full_frame_at_destination_size(self):
        observe = DRIVER["field_presenter"]
        client = [-900, 20, 60, 620]
        frame = {"begin": 120, "end": 140, "width": 960, "height": 600}
        snapshot = {"route": "cpu-gdi", "fullEditorFrame": frame}
        self.assertEqual(observe(snapshot, client, 100, 150)["fullEditorFrame"], frame)
        for bad in (None, {**frame, "width": 640}, {**frame, "begin": 99}, {**frame, "end": 151}):
            with self.assertRaises(ValueError):
                observe({**snapshot, "fullEditorFrame": bad}, client, 100, 150)
        self.assertIsNone(observe({**snapshot, "route": "wgpu-fallback"}, client, 100, 150)["fullEditorFrame"])

    def test_qualified_runs_preserve_failed_attempts_and_return_distinct_exit_codes(self):
        assess = DRIVER["assess"]
        records = []

        def observe(_target, build_dir, output, profile, report, *, require_interactive, retained, cpu_archive):
            self.assertTrue(require_interactive)
            self.assertFalse(retained)
            self.assertIsNone(cpu_archive)
            self.assertTrue(profile.is_dir())
            self.assertEqual(output.parent.parent, build_dir)
            report.update(inventoryPassed=True, sourceFrameObserved=True, rdpRenderingObserved=len(records) == 1)
            records.append(output / "result.json")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(assess.__globals__, measure=observe), redirect_stdout(io.StringIO()):
            root = Path(tmp)
            self.assertEqual(assess("x86_64-pc-windows-msvc", root, ["rdp"], require_interactive=True), 1)
            first = records[0].read_bytes()
            self.assertEqual(assess("x86_64-pc-windows-msvc", root, ["rdp"], require_interactive=True), 0)
            self.assertNotEqual(*records)
            self.assertEqual(first, records[0].read_bytes())
            self.assertEqual((json.loads(first)["status"], json.loads(first)["unmetQualifications"]), ("requirements-unmet", ["rdp"]))
            self.assertEqual(json.loads(records[1].read_bytes())["status"], "observed")
            for receipt in records:
                self.assertTrue(json.loads(receipt.read_bytes())["profileRemoved"])
                self.assertIn(hashlib.sha256(receipt.read_bytes()).hexdigest(), (receipt.parent / "evidence.sha256").read_text())

    def test_uia_geometry_must_match_both_subject_and_physical_display(self):
        row = {"status": "observed", "pid": 1, "hwnd": 2, "field": "Dateiname", "expectedText": "fixture",
               "dpi": 144, "rect": [-800, 80, -500, 110]}
        layout = {"pid": 1, "hwnd": 2, "awareness": 2, "dpi": 144, "monitor": "left", "client": [-900, 0, -300, 400]}
        monitor = {"handle": "left", "dpi": 144, "bounds": [-1280, 0, 0, 800]}
        self.assertEqual(DRIVER["field_geometry"](row, layout, monitor, "fixture")["logicalFieldSizeAt96"], [200, 20])
        for key, bad in (("pid", 2), ("hwnd", 99), ("expectedText", "other"), ("dpi", 96), ("rect", [-800, 80, -200, 110])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                DRIVER["field_geometry"]({**row, key: bad}, layout, monitor, "fixture")

    def test_scaled_field_and_same_three_characters_follow_dpi_in_both_directions(self):
        a = {"dpi": 96, "rect": [0, 0, 240, 20], "prefixRect": [0, 0, 24, 15]}
        b = {"dpi": 144, "rect": [-900, 40, -540, 70], "prefixRect": [-895, 41, -859, 64]}
        self.assertEqual(DRIVER["scaled_geometry"](a, b)["fieldHeight"]["after"], 30)
        self.assertEqual(DRIVER["scaled_geometry"](b, a)["prefixWidth"]["after"], 24)
        for broken in (a, {**a, "dpi": 144}, {**b, "prefixRect": [0, 0, 24, 15]}):
            with self.assertRaises(ValueError):
                DRIVER["scaled_geometry"](a, broken)

    def test_stationary_frame_requires_own_focus_material_pixels_and_matching_image_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = [root / ("Frame.json." + role + ".png") for role in ("before", "after")]
            record = {"phase": "Frame", "focusAtEntry": True, "focusAtExit": True, "expectedText": DRIVER["FIRST"],
                      "textAfter": DRIVER["SECOND"], "before": png(a, 32, 10, False), "after": png(b, 32, 10, True),
                      "difference": {"columns": 8, "rows": 4, "pixels": 32}}
            self.assertEqual(DRIVER["frame_evidence"](record, root, 96), [a, b])
            for key, value in (("focusAtEntry", False), ("textAfter", "wrong"), ("phase", "../outside"),
                               ("difference", {"columns": 1, "rows": 8, "pixels": 8}),
                               ("after", {**record["after"], "sha256": record["before"]["sha256"]})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    DRIVER["frame_evidence"]({**record, key: value}, root, 96)
            b.write_bytes(a.read_bytes())
            with self.assertRaises(ValueError):
                DRIVER["frame_evidence"](record, root, 96)


if __name__ == "__main__":
    unittest.main()
