"""Verify the cold and warm subjects before passing them to a native observer."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
TARGETS = ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
sys.path.insert(0, str(QA / "windows-performance"))
import run as recorder


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def subjects(target):
    if not recorder.hosted() or target not in TARGETS:
        raise ValueError("Use a disposable native Windows runner")
    art = ROOT / "artifacts/rust"
    output = art / "windows-warm-window" / target
    warm = output / "build/release/native-gui-assessment.exe"
    cold = art / "gui-build/release/native-gui-assessment.exe"
    receipt_path = output / "build.json"
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    canonical = art / "gui-native" / target / "build.json"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (record["revision"] != revision or record["target"] != target or record["baselineReceipt"] != sha(canonical)
            or sha(cold) != record["baseline"] or sha(warm) != record["binary"]
            or record["eframeSource"]["archive"] != "eframe-source.zip"
            or sha(output / "eframe-source.zip") != record["eframeSource"]["archiveSha256"]
            or record["compilerEvidence"]["file"] != "compiler.jsonl"
            or sha(output / "compiler.jsonl") != record["compilerEvidence"]["sha256"]
            or any(sha(HERE / name) != digest for name, digest in record["variantInputs"].items())):
        raise ValueError("Unexpected warm-window native build inputs")
    api = recorder.Win32()
    machine = 0xaa64 if target.startswith("aarch64-") else 0x8664
    if api.machine(-1) != (machine, machine) or any(recorder.pe_machine(path) != machine for path in (warm, cold)):
        raise ValueError("The observer and subjects must run natively on the same architecture")
    evidence = dict(target=target, run=os.getenv("GITHUB_RUN_ID"), attempt=os.getenv("GITHUB_RUN_ATTEMPT"),
                    revision=revision, buildReceipt=sha(receipt_path), baselineReceipt=record["baselineReceipt"],
                    baseline=record["baseline"], binary=record["binary"])
    return api, cold, warm, output, evidence
