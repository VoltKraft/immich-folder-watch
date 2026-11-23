"""Portable controls for the retained renderer selection used by the display fixture."""
import ctypes as c
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_display
import retained
from windows_observer import isolated_windows_vm


CPU = "ADAPTER Dx12 Cpu Microsoft Basic Render Driver"
GPU = "ADAPTER Dx12 IntegratedGpu Example adapter"


def device(adapter=CPU, *, mode="Mailbox", depth=1):
    lines = ["GRAPHICS_ATTEMPT generation=1 policy=preferred", "GRAPHICS_DX12_WAIT generation=1 policy=Wait",
             "GRAPHICS_MEMORY generation=1 hint=MemoryUsage", "GRAPHICS_READY generation=1", adapter]
    if adapter == CPU:
        lines.append("GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Mailbox, Fifo]")
        lines.append(f"GRAPHICS_PRESENT generation=1 desktop=WindowsDx12Cpu mode={mode} latency=Some({depth})")
    return lines


class RetainedDisplayTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.log = self.scratch / "subject.log"

    def write(self, rows):
        self.log.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_local_vm_requires_an_explicit_native_non_actions_invocation(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.platform", "win32"):
            self.assertTrue(isolated_windows_vm(True))
            self.assertFalse(isolated_windows_vm(False))
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                self.assertFalse(isolated_windows_vm(True))
            with patch("sys.platform", "linux"):
                self.assertFalse(isolated_windows_vm(True))

    def test_software_reports_its_real_depth_and_hardware_records_its_own_default(self):
        self.write(device())
        policy = retained.presentation(self.log, CPU)
        self.assertEqual((policy["presentMode"], policy["desiredMaximumFrameLatency"], policy["waitPolicy"]),
                         ("Mailbox", 1, "Wait"))
        self.write(device(GPU))
        hardware = retained.presentation(self.log, GPU)
        self.assertIsNone(hardware["presentMode"])
        self.assertIsNone(hardware["desiredMaximumFrameLatency"])
        self.assertEqual((hardware["generation"], hardware["adapter"]), (1, GPU))
        self.write(device()[:-2] + ["GRAPHICS_SURFACE generation=1 desktop=WindowsDx12Cpu offered=[Fifo]"])
        self.assertIsNone(retained.presentation(self.log, CPU)["presentMode"])

    def test_rejects_wrong_adapter_depth_lost_renderer_and_unproved_software_override(self):
        for adapter, rows in ((GPU, device()), (CPU, device(depth=2)), (CPU, device(mode="Fifo")),
                              (CPU, device()[:-1]), (CPU, device() + ["GRAPHICS_LOST generation=1 reason=test"]),
                              (CPU, device() + ["WINDOW_RELEASED passes=10"]),
                              (GPU, device(GPU) + [device()[-1]])):
            with self.subTest(adapter=adapter, last=rows[-1]), self.assertRaises(ValueError):
                self.write(rows)
                retained.presentation(self.log, adapter)

    def test_hide_requires_the_original_owned_hwnd_and_uninterrupted_process_and_device(self):
        hwnd = 33
        for outcome in ("hidden", "destroyed", "owner-changed", "shown", "device-changed", "quit"):
            self.write(device())
            observer = Mock(events=[])
            observer.visible.return_value = None
            observer.is_visible.return_value = outcome == "shown"
            lifetime = Mock(events=[(hwnd, "create", 1)])
            child = Mock(pid=42)
            child.poll.return_value = 0 if outcome == "quit" else None
            def hide(actual):
                self.assertEqual(actual, hwnd)
                observer.events.append(dict(hwnd=hwnd, event="hide", root=True))
                if outcome == "destroyed":
                    lifetime.events.extend([(hwnd, "destroy", 2), (hwnd, "create", 3)])
                if outcome == "device-changed":
                    self.write(device() + ["GRAPHICS_READY generation=2"])
            def owner(_hwnd, pointer):
                c.cast(pointer, c.POINTER(retained.w.DWORD))[0] = 24 if outcome == "owner-changed" else child.pid
                return 123
            observer.close_window.side_effect = hide
            observer.owner.side_effect = owner
            def wait(predicate, _name):
                self.assertTrue(predicate())
            info = {}
            with self.subTest(outcome=outcome):
                if outcome == "hidden":
                    self.assertTrue(retained.close(observer, lifetime, child, hwnd, self.log, CPU, wait, info))
                    self.assertEqual(info["retainedClose"]["hwnd"], hwnd)
                else:
                    with self.assertRaises((ValueError, RuntimeError)):
                        retained.close(observer, lifetime, child, hwnd, self.log, CPU, wait, info)

    def test_requested_rdp_on_retained_subject_keeps_unavailable_result_and_distinct_output(self):
        assess = test_display.DRIVER["assess"]
        def observe(_target, _build, _output, _profile, report, *, require_interactive, retained):
            self.assertTrue(require_interactive and retained)
            report.update(inventoryPassed=True, sourceFrameObserved=True, rdpRenderingObserved=False)
        with (patch.dict(assess.__globals__, measure=observe), patch.dict(os.environ, {"GITHUB_RUN_ID": "other"}),
              redirect_stdout(io.StringIO())):
            self.assertEqual(assess("x86_64-pc-windows-msvc", self.scratch, ["rdp"], require_interactive=True, retained=True), 1)
        path, = self.scratch.glob("windows-display-retained-runs/rdp-*/result.json")
        data = json.loads(path.read_bytes())
        self.assertEqual((data["host"], data["run"], data["subject"]), ("isolated-vm", None, "retained"))
        self.assertEqual((data["status"], data["unmetQualifications"]), ("requirements-unmet", ["rdp"]))
        self.assertTrue(data["profileRemoved"])

    def test_close_preserves_the_attempt_if_no_hide_event_arrives(self):
        self.write(device())
        hwnd = 33
        observer = Mock(events=[{"hwnd": hwnd, "event": "show", "root": True}])
        observer.visible.return_value = hwnd
        child = Mock(pid=42)
        child.poll.return_value = None
        lifetime = Mock(events=[(hwnd, "create", 1)])
        report = {"retainedEvents": {"visibility": observer.events, "objects": lifetime.events}}
        def timed_out(predicate, _name):
            self.assertFalse(predicate())
            raise TimeoutError("no native hide")
        with self.assertRaisesRegex(TimeoutError, "no native hide"):
            retained.close(observer, lifetime, child, hwnd, self.log, CPU, timed_out, report)
        self.assertEqual(report["retainedClose"]["visibilityStart"], 1)
        self.assertEqual(report["retainedClose"]["device"]["desiredMaximumFrameLatency"], 1)
        self.assertEqual(report["retainedEvents"]["objects"], [(hwnd, "create", 1)])


if __name__ == "__main__":
    unittest.main()
