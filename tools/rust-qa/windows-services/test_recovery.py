"""Exercise shortcut cleanup and desktop observer selection without an installed profile."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from run import recover
from windows_observer import select_powershell


class ObserverSelection(unittest.TestCase):
    def test_times_out_one_host_then_records_the_second_hosts_capability(self):
        finished = subprocess.CompletedProcess([], 0, b"7.7.0\r\n", b"")
        with patch("windows_observer.shutil.which", side_effect=lambda name: name), \
             patch("windows_observer.subprocess.run", side_effect=[subprocess.TimeoutExpired("powershell", 30), finished]) as run:
            program, attempts = select_powershell(Path.cwd(), "shortcut")
        self.assertEqual(program, "pwsh.exe")
        self.assertEqual([entry["status"] for entry in attempts], ["TimeoutExpired", 0])
        self.assertEqual(attempts[1]["version"], "7.7.0")
        for call in run.call_args_list:
            self.assertIn("WScript.Shell", call.args[0][-1])
            self.assertNotIn("UIAutomation", call.args[0][-1])
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)

    def test_unavailable_accessibility_is_reported_without_attempting_shortcut_com(self):
        failed = subprocess.CompletedProcess([], 1, b"", b"Unable to load assembly")
        with patch("windows_observer.shutil.which", side_effect=[None, "pwsh.exe"]), \
             patch("windows_observer.subprocess.run", return_value=failed) as run:
            program, attempts = select_powershell(Path.cwd(), "accessibility")
        self.assertIsNone(program)
        self.assertEqual([entry["status"] for entry in attempts], ["missing", 1])
        self.assertIn("UIAutomationClient", run.call_args.args[0][-1])
        self.assertNotIn("WScript", run.call_args.args[0][-1])


class ShortcutRecovery(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.token = "a" * 32
        folder = self.directory / "Synthetic Startup"
        folder.mkdir()
        self.link = folder / ("IFW-RW02-" + self.token + ".lnk")
        self.marker = self.directory / "private.owned"

    def test_existing_link_without_our_reservation_is_preserved(self):
        self.link.write_bytes(b"existing")
        self.assertEqual(recover(self.directory, self.token, False), [])
        self.assertEqual(self.link.read_bytes(), b"existing")

    def test_replacement_and_wrong_reservation_paths_are_preserved(self):
        self.marker.write_text(str(self.link), encoding="utf-8")
        self.link.write_bytes(b"replacement")
        (self.directory / "private.saved").write_bytes(b"original")
        with self.assertRaises(ValueError):
            recover(self.directory, self.token, False)
        self.marker.write_text(str(self.link.with_name("other.lnk")), encoding="utf-8")
        with self.assertRaises(ValueError):
            recover(self.directory, self.token, False)
        self.assertEqual(self.link.read_bytes(), b"replacement")

    def test_only_the_reserved_unchanged_link_is_removed(self):
        self.marker.write_text(str(self.link), encoding="utf-8")
        self.link.write_bytes(b"owned")
        (self.directory / "private.saved").write_bytes(b"owned")
        self.assertEqual(recover(self.directory, self.token, False), ["private"])
        self.assertFalse(self.link.exists())
