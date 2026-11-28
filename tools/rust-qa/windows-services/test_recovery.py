"""Exercise shortcut cleanup and desktop observer selection without an installed profile."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from run import ICON_TEST, observe_services_and_image, recover, verify_icon_rasters
from windows_observer import select_powershell


class TrayImageEvidence(unittest.TestCase):
    def test_native_services_still_run_after_a_failing_image_test_or_an_invalid_capture(self):
        for code in (1, 0):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)
                result = {}
                def step(name, args):
                    self.assertEqual(name, "tray-image")
                    self.assertIn("--exact", args)
                    (output / "tray-image.txt").write_bytes(b"incomplete native image observation\n")
                    if code:
                        raise subprocess.CalledProcessError(code, args)

                shell = Mock(return_value={"failedChecks": [], "completedServiceControl": True})
                with patch("sys.stderr"):
                    observe_services_and_image(result, output, step, shell)
                shell.assert_called_once_with()
                self.assertEqual(result["observations"], shell.return_value)
                self.assertTrue(result["probeCompleted"])
                self.assertEqual(result["trayImage"]["status"], "failed")
                self.assertEqual((output / result["trayImage"]["log"]).read_bytes(), b"incomplete native image observation\n")

    def test_original_pixels_both_colors_sizes_backgrounds_and_cleanup_are_required(self):
        rows = [f"test {ICON_TEST} ... ok"]
        for rgb in ("1fc653", "33c733"):
            for scale, w, lo, hi in (("source", 32, 5, 27), ("systemSmall", 16, 4, 12)):
                n = (hi - lo) ** 2
                for bg in ("ff000000", "ffffffff"):
                    pixels = "".join("ff" + rgb if lo <= x < hi and lo <= y < hi else bg
                                     for y in range(w) for x in range(w))
                    rows.append(f"HICON_RASTER rgb={rgb} scale={scale} width={w} height={w} background={bg} "
                                f"interior={lo},{lo},{hi},{hi} exact={n}/{n} pixels={pixels}")
            rows.append("HICON_RELEASED rgb=" + rgb)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tray-image.txt"
            path.write_text("\n".join(rows))
            verify_icon_rasters(path)
            for mutation in (rows[1:], rows[:-1], [*rows[:3], *rows[4:]],
                             [rows[0], rows[1].replace("ff1fc653", "ff33c733", 1), *rows[2:]],
                             [*rows[:2], rows[2].replace("pixels=ffffffff", "pixels=ff000000"), *rows[3:]]):
                path.write_text("\n".join(mutation))
                with self.assertRaises(ValueError):
                    verify_icon_rasters(path)


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
