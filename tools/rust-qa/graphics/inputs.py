"""Identify the frozen supervisor and worker inputs independently of the native target."""

import hashlib
import json


GUI_SOURCES = "3f52b87a1c0ddc710ff37d572ee4904bd2d7285ce7bef8a8341f298b44417db6"
WORKER_SOURCES = "98f6b2702531ca7d1ccd2aee1d74624fc6d309a8c9b890ea5ca9dc29b54407a8"


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def source_digest(receipt):
    exact = json.dumps(receipt["sources"], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(exact).hexdigest()
