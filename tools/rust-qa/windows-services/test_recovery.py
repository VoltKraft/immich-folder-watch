"""Exercise the timeout recovery boundary using only new temporary directories."""

from pathlib import Path
import tempfile
import unittest

from run import recover


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
