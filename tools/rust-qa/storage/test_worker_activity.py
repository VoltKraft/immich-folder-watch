"""Regression controls for the data passed between the native worker and SQLite assessment."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from run import run_worker_activities
from worker_activity import original_bytes, stale_control
from verify_activity import check_peer_requests


class WorkerActivityTests(unittest.TestCase):
    def test_stale_refusal_identifies_the_download_attempt_and_its_before_backup(self):
        request = {"token": "1" * 32, "beforeSha256": "2" * 64}
        refusal = {"format": "ifw-worker-backup-stale-v1", "token": request["token"],
                   "sourceSha256": request["beforeSha256"]}
        line = b"IFW_WORKER_STALE=" + json.dumps(refusal).encode() + b"\n"
        reason = b'Error: "no completed worker download"\n'
        stale_control(line + reason, request, 1)
        for data, code in ((reason, 1), (line + line + reason, 1), (line + reason, 0),
                           (line.replace(b"1" * 32, b"3" * 32) + reason, 1),
                           (line.replace(b"2" * 64, b"4" * 64) + reason, 1)):
            with self.subTest(data=data, code=code), self.assertRaises(ValueError):
                stale_control(data, request, code)

    def test_stale_upload_and_download_refusals_cannot_be_exchanged(self):
        request = {"token": "1" * 32, "beforeSha256": "2" * 64}
        marker = json.dumps({"format": "ifw-worker-upload-backup-stale-v1", "token": request["token"],
                             "sourceSha256": request["beforeSha256"]}).encode()
        refusal = b"IFW_WORKER_STALE=" + marker + b'\nError: "no completed worker upload"\n'
        stale_control(refusal, request, 1, upload=True)
        with self.assertRaises(ValueError):
            stale_control(refusal, request, 1)
        with self.assertRaises(ValueError):
            stale_control(refusal.replace(b"worker-upload-backup", b"worker-backup"), request, 1, upload=True)
        with self.assertRaises(ValueError):
            stale_control(refusal.replace(b"completed worker upload", b"completed worker download"), request, 1, upload=True)

    def test_restarted_peer_requires_its_original_asset_without_new_requests(self):
        asset = {"id": "asset-original", "originalFileName": "capture.jpg"}
        valid = {"uploads": 0, "downloads": 0, "rejectedRequests": [], "listings": [asset]}
        check_peer_requests(valid, 0, asset)
        for key, value in (("uploads", 1), ("downloads", 1), ("rejectedRequests", [{"method": "AddAssetsToAlbumAsync",
                           "arguments": ["Camera", "asset-original"]}]), ("listings", []), ("listings", [None]),
                           ("listings", [dict(asset, id="asset-other")])):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                check_peer_requests({**valid, key: value}, 0, asset)

    def test_earlier_repair_and_deletion_donors_need_their_own_refusal(self):
        request = {"token": "1" * 32, "beforeSha256": "2" * 64}
        for kind, reason in (("repair", "no pending worker timestamp repair"), ("deletion", "no worker tombstone")):
            marker = {"format": f"ifw-worker-{kind}-backup-stale-v1", "token": request["token"],
                      "sourceSha256": request["beforeSha256"]}
            lines = b"IFW_WORKER_STALE=" + json.dumps(marker).encode() + f'\nError: "{reason}"\n'.encode()
            with self.subTest(kind=kind):
                stale_control(lines, request, 1, kind=kind)
                other = "deletion" if kind == "repair" else "repair"
                with self.assertRaises(ValueError):
                    stale_control(lines, request, 1, kind=other)

    def test_oversized_backup_is_rejected_before_readback(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "returned.db")
            with path.open("xb") as file:
                file.truncate((16 << 20) + 1)
            with self.assertRaises(ValueError):
                original_bytes(path, 16 << 20)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires a Unix FIFO")
    def test_archive_reader_refuses_a_fifo_and_its_link_without_waiting(self):
        with tempfile.TemporaryDirectory() as root:
            fifo = Path(root, "fifo")
            link = Path(root, "returned.db")
            os.mkfifo(fifo)
            link.symlink_to(fifo)
            for path in (fifo, link):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    original_bytes(path, 16 << 20)


class WorkerActivityRunnerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)
        self.probe = self.output / "probe"
        self.assembly = self.output / "assembly"
        self.probe.write_bytes(b"Rust fixture")
        self.assembly.write_bytes(b"C# fixture")
        self.result = {"source": "test-source"}

    def run_cases(self, trial):
        with patch("worker_activity.run", side_effect=trial):
            run_worker_activities(self.output, self.result, self.probe, self.assembly,
                                  sys.executable, os.environ, "synthetic-target")

    def test_independent_cases_retain_their_original_results_and_failures(self):
        def trial(directory, *args, kind):
            directory.mkdir()
            (directory / "worker.log").write_text(kind)
            if kind in ("upload", "deletion"):
                raise ValueError(kind + " fixture failed")
            return {"case": kind}

        with self.assertRaisesRegex(RuntimeError, "upload, deletion"):
            self.run_cases(trial)
        activity = json.loads((self.output / "result.json").read_bytes())["workerActivity"]
        self.assertEqual(activity["readback"], {"case": "download"})
        self.assertEqual(activity["repairReadback"], {"case": "repair"})
        self.assertEqual(set(activity["failures"]), {"upload", "deletion"})
        for kind, failure in activity["failures"].items():
            self.assertIn("ValueError: " + kind + " fixture failed", (self.output / failure["log"]).read_text())
            self.assertEqual((self.output / failure["directory"] / "worker.log").read_text(), kind)

    def test_success_keeps_the_existing_readback_names(self):
        self.run_cases(lambda *args, kind: kind)
        self.assertEqual(set(self.result["workerActivity"]),
                         {"rustExecutable", "testAssembly", "readback", "uploadReadback", "deletionReadback", "repairReadback"})

    def test_failed_case_with_a_changed_executable_stops_the_remaining_cases(self):
        for changed in (self.probe, self.assembly):
            attempted = []

            def change_and_fail(*args, kind):
                attempted.append(kind)
                changed.write_bytes(changed.read_bytes() + b" changed")
                raise ValueError("fixture failed")

            with self.subTest(changed=changed.name), self.assertRaisesRegex(ValueError, "executable changed"):
                self.run_cases(change_and_fail)
            self.assertEqual(attempted, ["download"])
            self.assertEqual(self.result["workerActivity"]["failures"]["download"]["error"], "fixture failed")

    def test_cancellation_stops_before_the_next_case(self):
        attempted = []

        def cancel(*args, kind):
            attempted.append(kind)
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.run_cases(cancel)
        self.assertEqual(attempted, ["download"])
        self.assertNotIn("failures", self.result["workerActivity"])
