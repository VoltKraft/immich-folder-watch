import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import window_quit_guest as guest


class CanonicalWindowQuitTests(unittest.TestCase):
    def test_only_the_original_canonical_gui_is_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            kit = base / "kit.zip"
            key = "canonical/native-gui-assessment.exe"
            with ZipFile(kit, "w") as archive:
                archive.writestr(key, b"ordinary GUI")
                archive.writestr("native-gui-assessment.exe", b"retained GUI")
            worker = base / "ifw-performance-worker.exe"
            worker.write_bytes(b"inventory")
            sha = hashlib.sha256(b"ordinary GUI").hexdigest()
            record = {"revision": "a" * 40, "files": {key: sha},
                      "inventory": {"worker": guest.local_tray.file_sha(worker)}}
            with patch.object(guest.local_tray, "stage", return_value=(record, {})) as stage:
                with self.assertRaisesRegex(ValueError, "requested revision"):
                    guest.canonical_pair(kit, "digest", "b" * 40, base)
                gui, selected_worker, hashes, actual = guest.canonical_pair(kit, "digest", "a" * 40, base)
                stage.assert_called_with(kit, "digest", base)
                self.assertEqual((gui.read_bytes(), selected_worker, hashes["gui"], actual),
                                 (b"ordinary GUI", worker, sha, record))

    def test_changed_canonical_bytes_are_rejected_after_archive_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            kit = base / "kit.zip"
            key = "canonical/native-gui-assessment.exe"
            with ZipFile(kit, "w") as archive:
                archive.writestr(key, b"different GUI")
            (base / guest.local_tray.WORKER).write_bytes(b"inventory")
            record = {"revision": "a" * 40, "files": {key: "0" * 64},
                      "inventory": {"worker": hashlib.sha256(b"inventory").hexdigest()}}
            with patch.object(guest.local_tray, "stage", return_value=(record, {})):
                with self.assertRaisesRegex(ValueError, "after staging"):
                    guest.canonical_pair(kit, "digest", "a" * 40, base)
