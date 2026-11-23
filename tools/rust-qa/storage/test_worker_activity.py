"""Regression controls for the data passed between the native worker and SQLite assessment."""

import json
import os
from pathlib import Path
import tempfile
import unittest

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
