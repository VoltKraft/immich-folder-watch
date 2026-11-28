"""Portable checks for selecting the measured executable without rebuilding it."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import cpu_archive


def digest(data):
    return hashlib.sha256(data).hexdigest()


class CpuArchiveTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.archive = workspace / "sample.zip"
        self.stage = workspace / "stage"
        self.stage.mkdir()
        self.image = b"test image"
        self.worker = b"test worker"
        self.enterContext(patch.object(cpu_archive, "GUI_SHA256", digest(self.image)))
        self.enterContext(patch.object(cpu_archive, "WORKER_SHA256", digest(self.worker)))

    def bundle(self, *, gui=None, worker=None, passed=True, recovered=True, timing_link=None):
        original = cpu_archive.ORIGIN
        gui_hash, worker_hash = digest(self.image), digest(self.worker)
        build = json.dumps({**original, "application": {"sha256": gui_hash}}).encode()
        metrics = {str(i): {"passed": i != 0 or passed} for i in range(11)}
        timing = json.dumps({**original, "cpuBuild": digest(build), "binary": gui_hash,
                             "inputs": {"inventory": {"gui": gui_hash, "worker": worker_hash}},
                             "checks": {"resources": {"metrics": metrics}}, "status": "cpu-paint-observed",
                             "presentMode": "CPU-GDI"}).encode()
        recovery = json.dumps({**original, "images": [gui_hash, worker_hash],
                               "measurement": timing_link or digest(timing),
                               "status": "passed" if recovered else "failed"}).encode()
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, data in (("cpu.exe", self.image if gui is None else gui),
                               ("ifw-performance-worker.exe", self.worker if worker is None else worker),
                               ("cpu-build.json", build), ("result.json", timing), ("recovery/result.json", recovery),
                               ("other.exe", b"unrelated image")):
                archive.writestr(cpu_archive.PREFIX + name, data)
        return digest(self.archive.read_bytes())

    def test_only_the_qualified_subject_is_staged_and_an_existing_image_is_preserved(self):
        with patch.object(cpu_archive, "ARCHIVE_SHA256", self.bundle()):
            binary, provenance = cpu_archive.stage(self.archive, self.stage)
            self.assertEqual([binary], list(self.stage.iterdir()))
            self.assertEqual(binary.read_bytes(), self.image)
            self.assertEqual(provenance["binary"], digest(self.image))
            self.assertEqual(provenance["revision"], cpu_archive.ORIGIN["revision"])
            binary.write_bytes(b"already occupied")
            with self.assertRaises(FileExistsError):
                cpu_archive.stage(self.archive, self.stage)
            self.assertEqual(binary.read_bytes(), b"already occupied")

    def test_rejects_a_repacked_input_before_staging(self):
        self.bundle()
        with self.assertRaisesRegex(ValueError, "original Windows x64"):
            cpu_archive.stage(self.archive, self.stage)
        self.assertEqual([], list(self.stage.iterdir()))

    def test_swapped_images_or_disconnected_measurements_never_reach_the_stage(self):
        for change in ({"gui": self.worker}, {"worker": self.image}, {"timing_link": "another measurement"},
                       {"passed": False}, {"recovered": False}):
            with self.subTest(change=change), patch.object(cpu_archive, "ARCHIVE_SHA256", self.bundle(**change)):
                with self.assertRaises(ValueError):
                    cpu_archive.stage(self.archive, self.stage)
                self.assertEqual([], list(self.stage.iterdir()))
