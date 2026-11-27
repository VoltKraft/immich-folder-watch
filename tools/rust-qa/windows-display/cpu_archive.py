"""Stage the measured Windows x64 display subject from its original Actions ZIP."""
import hashlib
import json
from pathlib import Path
import zipfile


ARCHIVE_SHA256 = "2338eba8784f413b77493bc2d9499d2d2127b5895a748115aaf46ef20407a16b"
GUI_SHA256 = "b84080b16e365d5297e5d2eb93be9f647f43b57b21bd80332b9917e85dfa36ec"
WORKER_SHA256 = "e1a8d77170f60a54a72549a0712dc67aa59159f7e378954a6fc1e9a338372f75"
ORIGIN = {
    "target": "x86_64-pc-windows-msvc",
    "revision": "483f0534ffdddb0f677b62fcd3b5b48cc2b0fa98",
    "run": "45979619561",
    "attempt": "1",
}
PREFIX = "windows-warm-window/x86_64-pc-windows-msvc/cpu-paint/"


def stage(archive: Path, directory: Path) -> tuple[Path, dict]:
    """Verify the qualified build and stage only cpu.exe in the caller's private directory.

    Return the new file and its original build, timing and recovery provenance.
    The caller owns the directory and must hold the staged image for launch.
    """
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Expected the original Windows x64 CPU timing and recovery ZIP")
        stream.seek(0)
        with zipfile.ZipFile(stream) as bundle:
            def record(name):
                data = bundle.read(PREFIX + name)
                return json.loads(data), hashlib.sha256(data).hexdigest()

            build, build_hash = record("cpu-build.json")
            timing, timing_hash = record("result.json")
            recovery, recovery_hash = record("recovery/result.json")
            with bundle.open(PREFIX + "ifw-performance-worker.exe") as worker:
                worker_hash = hashlib.file_digest(worker, "sha256").hexdigest()
            image = bundle.read(PREFIX + "cpu.exe")

    if any(row[key] != value for row in (build, timing, recovery) for key, value in ORIGIN.items()):
        raise ValueError("The archived build, timing and recovery have different origins")
    inventory = timing["inputs"]["inventory"]
    if (hashlib.sha256(image).hexdigest() != GUI_SHA256 or worker_hash != WORKER_SHA256
            or not build["application"]["sha256"] == timing["binary"] == inventory["gui"] == GUI_SHA256
            or inventory["worker"] != worker_hash or recovery["images"] != [GUI_SHA256, worker_hash]
            or timing["cpuBuild"] != build_hash or recovery["measurement"] != timing_hash):
        raise ValueError("The archived images do not match their build, timing and recovery receipts")
    metrics = timing["checks"]["resources"]["metrics"]
    if (timing["status"] != "cpu-paint-observed" or timing["presentMode"] != "CPU-GDI"
            or len(metrics) != 11 or not all(metric["passed"] is True for metric in metrics.values())
            or recovery["status"] != "passed"):
        raise ValueError("The archived CPU build must pass the WPF timing limits and device recovery")

    binary = directory / "cpu.exe"
    with binary.open("xb") as output:
        output.write(image)
    return binary, {**ORIGIN, "binary": GUI_SHA256, "worker": worker_hash, "artifactId": "15191997288",
                    "archiveSha256": ARCHIVE_SHA256, "cpuBuild": build_hash, "timingSha256": timing_hash,
                    "recoverySha256": recovery_hash}
