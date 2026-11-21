"""Portable regression checks for gating foreground input, restoration and the Windows ABI."""

import ctypes as c
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from job import ExtendedLimits, Process, Startup
from run import pe_machine, switch_back
from win32 import SessionInfo, ordinary_console
from worker import field_center, input_passed, named_desktop


def active(desktop="Default"):
    return {"windowStation": "WinSta0", "stationVisible": True, "threadDesktop": desktop, "inputDesktop": desktop,
            "threadReceivesInput": True, "inputObjectReceivesInput": True, "session": 2, "activeConsoleSession": 2,
            "wts": {"session": 2, "connectionState": 0, "lockFlags": 1}}


class DesktopTests(unittest.TestCase):
    def test_requires_actual_active_unlocked_desktop(self):
        self.assertTrue(ordinary_console(active("default"), "Default"))
        for changes in ({"inputDesktop": "Winlogon"}, {"threadDesktop": "Screen-saver"},
                        {"stationVisible": False}, {"windowStation": "Service-0x0"},
                        {"threadReceivesInput": False}, {"inputObjectReceivesInput": False},
                        {"activeConsoleSession": 1}, {"wts": {"win32Error": 5}},
                        {"wts": {"session": 2, "connectionState": 4, "lockFlags": 1}},
                        {"wts": {"session": 2, "connectionState": 0, "lockFlags": 0}},
                        {"wts": {"session": 2, "connectionState": 0, "lockFlags": -1}}):
            with self.subTest(changes=changes):
                self.assertFalse(ordinary_console({**active(), **changes}, "Default"))

    def test_releases_only_fixture_owned_input_desktop(self):
        name = "IfwQa_" + "a" * 32
        api = Mock()
        api.context.return_value = {**active(), "inputDesktop": name, "threadReceivesInput": False}
        api.input_name.return_value = "default"
        api.switch.return_value = True
        evidence = {}
        with patch("run.c.set_last_error", create=True):
            switch_back(api, 100, name, evidence)
        api.switch.assert_called_once_with(100)
        self.assertTrue(evidence["switchBack"])
        self.assertEqual(evidence["inputAfterRestore"], "default")
        for changes in ({"inputDesktop": "Winlogon"}, {"inputDesktop": "someone-else"},
                        {"wts": {"session": 2, "connectionState": 0, "lockFlags": 0}}):
            api.reset_mock()
            api.context.return_value = {**active(), "inputDesktop": name, **changes}
            with self.assertRaises(RuntimeError):
                switch_back(api, 100, name, {})
            api.switch.assert_not_called()

    def test_already_restored_input_desktop_is_only_read(self):
        api = Mock()
        api.context.return_value = active()
        api.input_name.return_value = "Default"
        switch_back(api, 100, "fixture", {})
        api.switch.assert_not_called()

    def test_native_desktop_name_is_single_generated_component(self):
        self.assertTrue(named_desktop("IfwQa_" + "b" * 32))
        for name in ("Default", "Winlogon", "WinSta0\\Default", "IfwQa_" + "g" * 32):
            self.assertFalse(named_desktop(name))

    def test_checks_process_and_field_geometry(self):
        record = {"processId": 200, "hwnd": 1001, "name": "Dateiname", "center": [286, 201]}
        self.assertEqual(field_center(record, 200, 1001), [286, 201])
        for change in ({"processId": 201}, {"hwnd": 1002}, {"center": [286]}, {"center": [True, 201]}):
            with self.assertRaises(ValueError):
                field_center({**record, **change}, 200, 1001)

    def test_only_completed_guarded_input_passes(self):
        passed = {"processId": 200, "status": "passed", "onInputDesktop": True, "foreground": True,
                  "passwordProperty": True, "passwordCharactersTyped": 3,
                  "englishLabels": ["Filename", "Password"], "unicodeClipboardRoundTrip": True}
        self.assertTrue(input_passed(passed, 200))
        self.assertFalse(input_passed(passed, 201))
        for key in passed:
            self.assertFalse(input_passed({k: v for k, v in passed.items() if k != key}, 200))

    @unittest.skipUnless(c.sizeof(c.c_void_p) == 8, "64-bit Windows targets")
    def test_64_bit_windows_layout(self):
        self.assertEqual([c.sizeof(s) for s in (Startup, Process, ExtendedLimits)], [104, 24, 144])
        self.assertEqual((Startup.desktop.offset, Startup.flags.offset, ExtendedLimits.basic.offset), (16, 60, 0))
        self.assertEqual((SessionInfo.data.offset, SessionInfo.data.offset + 8), (8, 16))

    def test_pe_machine_is_read_from_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "subject.exe"
            header = bytearray(200)
            header[0:2], header[60:64], header[128:134] = b"MZ", struct.pack("<I", 128), b"PE\0\0\x64\xaa"
            exe.write_bytes(header)
            self.assertEqual(pe_machine(exe), 0xaa64)
            exe.write_bytes(b"else")
            with self.assertRaises(ValueError):
                pe_machine(exe)


if __name__ == "__main__":
    unittest.main()
