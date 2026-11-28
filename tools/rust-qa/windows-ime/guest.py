"""Prepare the original Windows x64 desktop compiler ZIP and run the local IME observer."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import HERE, QA, ROOT, checked_build, digest, native_target, read

TARGET = "x86_64-pc-windows-msvc"
BINARY = "native-gui-assessment.exe"


def prepare(archive, expected_digest, source, staging):
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("The expected compiler revision must be a full Git commit")
    expected_digest = expected_digest.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or digest(archive) != expected_digest:
        raise ValueError("The original desktop ZIP differs from the Actions digest")
    with zipfile.ZipFile(archive) as kit:
        limits = {"build.json": 1024 * 1024, "graph.json": 4 * 1024 * 1024, BINARY: 64 * 1024 * 1024}
        if sorted(kit.namelist()) != sorted(limits):
            raise ValueError("Expected the original three desktop compiler outputs")
        for name, limit in limits.items():
            if not 0 < kit.getinfo(name).file_size <= limit:
                raise ValueError(f"Unexpected compiler output size for {name}")
            with kit.open(name) as src, (staging / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
    receipt = staging / "build.json"
    build = read(receipt)
    checked_build(staging / BINARY, receipt, TARGET, 0x8664, source)
    audited = read(ROOT / "rust/audit/gui-profile.json")
    if (build["graphSha256"] != digest(staging / "graph.json")
            or build["graphSha256"] != audited["targetReportSha256"][TARGET]
            or build["lockSha256"] != digest(QA / "gui/Cargo.lock")):
        raise ValueError("The GUI lockfile or the archived native graph differs from the GUI profile")
    rust_sources = [QA / "gui/Cargo.toml", *sorted((QA / "gui/src").glob("*.rs")), QA / "gui/src/tray-icon.argb",
                    ROOT / "rust/Cargo.toml", ROOT / "rust/crates/desktop-lifecycle/Cargo.toml",
                    ROOT / "rust/crates/desktop-lifecycle/src/lib.rs"]
    if build["compilerSources"] != {p.relative_to(ROOT).as_posix(): digest(p) for p in rust_sources}:
        raise ValueError("The checkout differs from the original Rust GUI compiler inputs")
    return {"target": TARGET, "compilerRevision": source, "archiveSha256": expected_digest,
            "receiptSha256": digest(receipt), "binarySha256": build["binarySha256"],
            "graphSha256": build["graphSha256"], "lockSha256": build["lockSha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True, help="digest from the Actions artifact metadata")
    parser.add_argument("--head", required=True, help="full Git commit recorded by the native compiler")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["installed", "japanese"], required=True,
                        help="run initially, or after the administrator has prepared Basic Typing")
    args = parser.parse_args()
    if (os.name != "nt" or os.getenv("GITHUB_ACTIONS") or os.getenv("COMPUTERNAME", "").upper() != "IFW-QA25"
            or native_target() != (TARGET, 0x8664)):
        parser.error("Use the local disposable Windows x64 test VM")
    with tempfile.TemporaryDirectory(prefix="ifw-ime-desktop-") as staging:
        kit = Path(staging)
        record = prepare(args.archive, args.archive_sha256, args.head, kit)
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        record["driverSha256"] = digest(Path(__file__))
        (output / "compiler.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HERE / "guest.ps1",
                   "-Binary", kit / BINARY, "-Receipt", kit / "build.json", "-CompilerRevision", args.head,
                   "-Python", sys.executable, "-Output", output, "-Phase", args.phase]
        return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
