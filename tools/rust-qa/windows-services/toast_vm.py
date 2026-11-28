"""Read the native compiler's original sender archive on the isolated x64 console."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


TARGET = "x86_64-pc-windows-msvc"
EXE = "ifw-windows-services-probe.exe"


def require_vm(target):
    if sys.platform != "win32" or "GITHUB_ACTIONS" in os.environ or target != TARGET:
        raise ValueError("Use the disposable native Windows x64 VM console")


@contextmanager
def read_sender(archive, expected):
    if not re.fullmatch("[0-9a-f]{64}", expected):
        raise ValueError("Expected the SHA-256 digest published by Actions for the sender archive")
    with archive.open("rb") as stream, TemporaryDirectory(prefix="ifw-native-toast-") as directory:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("The original native sender archive digest changed")
        root = Path(directory)
        original = root / "native"
        original.mkdir()
        executable = f"build/{TARGET}/release/{EXE}"
        prefix = "native-" + TARGET + "/"
        with ZipFile(stream) as bundle:
            files = [entry for entry in bundle.infolist() if not entry.is_dir()]
            if (len(files) > 64 or len(files) != len({entry.filename for entry in files})
                    or sum(entry.file_size for entry in files) > 32 * 1024 * 1024):
                raise ValueError("Unexpected native sender archive inventory")
            report = json.loads(bundle.read(prefix + "result.json"))
            names = set(report["evidenceFiles"])
            if (not all(re.fullmatch(r"[a-z0-9-]+\.(?:json|txt)", name) and name != "result.json" for name in names)
                    or {entry.filename for entry in files} != {executable, prefix + "result.json", *(prefix + n for n in names)}):
                raise ValueError("The native sender archive differs from the build receipt")
            for source in files:
                if source.filename == executable:
                    (root / EXE).write_bytes(bundle.read(source))
                else:
                    name = source.filename.removeprefix(prefix)
                    data = bundle.read(source)
                    if name != "result.json" and hashlib.sha256(data).hexdigest() != report["evidenceFiles"][name]:
                        raise ValueError(f"The archived native compiler evidence changed: {name}")
                    (original / name).write_bytes(data)
        if (report["target"] != TARGET or report["hosted"] is not True or not report["runner"]
                or not re.fullmatch("[0-9a-f]{40}", report["head"])
                or not all(re.fullmatch("[1-9][0-9]*", report[k]) for k in ("workflowRun", "workflowAttempt"))):
            raise ValueError("Missing the original native Windows compiler job identity")
        yield root / EXE, original, report
