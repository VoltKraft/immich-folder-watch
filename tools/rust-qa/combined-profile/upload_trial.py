"""Compare a held Rust file with the shipping C# legacy multipart vectors."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from sources import HERE, ROOT, read, sha256, write


CORPUS = ROOT / "rust/tests/fixtures/behavior/legacy-upload.json"
EPOCH_TICKS = 621355968000000000
CASES = {f"BEH-LEGACY-{index:02d}" for index in range(1, 6)}


def wait_for_body(child, log):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if log.read_bytes().splitlines() == [b"BODY_CONSUMED"]:
            return
        if child.poll() is not None:
            raise RuntimeError(f"Upload subject exited before consuming the first body. See {log.name}")
        time.sleep(0.05)
    raise TimeoutError("Waiting for the initial synthetic upload body")


def seed_file(path, content, mtime_ns):
    with path.open("xb") as stream:
        stream.write(content)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    if path.stat().st_mtime_ns != mtime_ns:
        raise ValueError("The test volume changed the requested last-write timestamp")


def observe(prefix, subject, fixture, case, index, env, output):
    name = f"upload-{index}"
    folder = fixture / name
    folder.mkdir()
    path, retained = folder / "media.jpg", folder / "first.jpg"
    original = base64.b64decode(case["contentBase64"], validate=True) * case.get("contentRepeats", 1)
    ticks = int(case["modifiedDotNetTicks"])
    timestamp = (ticks - EPOCH_TICKS) * 100
    seed_file(path, original, timestamp)
    replacement = bytes(byte ^ 255 for byte in original)
    replacement_time = timestamp
    if case["id"] == "BEH-LEGACY-05":
        replacement += b"other file"
        replacement_time += 60_000_000_000
    log = output / f"{name}.log"
    mapped = str(Path(subject[1]) / name)
    with log.open("xb") as stream, subprocess.Popen(
            [*prefix, subject[0], "--legacy-upload", mapped, case["displayPath"]], cwd=HERE,
            env=env, stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT) as child:
        try:
            wait_for_body(child, log)
            try:
                path.rename(retained)
            except OSError as error:
                if os.name != "nt" or getattr(error, "winerror", None) != 32:
                    raise
                renamed = False
            else:
                renamed = True
                seed_file(path, replacement, replacement_time)
            child.communicate(b"RETRY\n", timeout=30)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
        if child.returncode != 0:
            raise RuntimeError(f"Upload subject exited with {child.returncode}. See {log.name}")
    ready, result = log.read_bytes().splitlines()
    observed = json.loads(result)
    original_hash = hashlib.sha256(original).hexdigest().upper()
    expected = {"firstBodySha256": original_hash, "retryBodySha256": original_hash,
                "originalNameStillMatches": not renamed, "retryPosition": 0,
                "identity": {"length": len(original), "lastWriteTicks": ticks,
                             "contentSha256": original_hash, "deviceAssetId": case["deviceAssetId"]}}
    if (ready != b"BODY_CONSUMED" or expected != observed or original_hash != case["contentSha256Upper"]
            or path.read_bytes() != (replacement if renamed else original)
            or (renamed and (retained.read_bytes() != original or retained.stat().st_mtime_ns != timestamp))
            or path.stat().st_mtime_ns != (replacement_time if renamed else timestamp)):
        raise ValueError(f"Retained upload or replacement differs from shipping case {case['id']}")
    return {"case": case["id"], "displayPath": case["displayPath"], "renamed": renamed,
            "currentPathLength": path.stat().st_size, "currentPathMtimeNs": path.stat().st_mtime_ns,
            "currentPathSha256": sha256(path), "subjectLogSha256": sha256(log), **observed}


def run(prefix, subject, fixture, env, output):
    corpus = read(CORPUS)
    ids = [case["id"] for case in corpus["cases"]]
    if len(ids) != len(CASES) or set(ids) != CASES:
        raise ValueError("Expected all five distinct shipping upload cases")
    cases = [observe(prefix, subject, fixture, case, i, env, output) for i, case in enumerate(corpus["cases"])]
    report = {"referenceRevision": corpus["baselineSourceRevision"], "referenceSha256": sha256(CORPUS), "cases": cases}
    write(output / "legacy-upload.json", report)
    return sha256(output / "legacy-upload.json")
