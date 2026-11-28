"""Build the isolated MSI admission observer on the matching native Windows runner."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = sys.argv[1]
    native = {"amd64": "x86_64-pc-windows-msvc", "arm64": "aarch64-pc-windows-msvc"}
    if os.name != "nt" or native.get(platform.machine().lower()) != target:
        raise ValueError("The matching native Windows runner is required")
    rustc = ROOT / "artifacts/rust/toolchain/bin/rustc.exe"
    subprocess.run([sys.executable, HERE.parents[1] / "check-toolchain.py", target, "--rustc", rustc], check=True)
    out = ROOT / "artifacts/rust/msi-session-endpoint" / target
    out.mkdir(parents=True, exist_ok=False)
    source = HERE / "msi_endpoint.rs"
    subject = out / "msi-session-endpoint.exe"
    subprocess.run([rustc, "--edition=2024", "-C", "opt-level=2", "--target", target, source, "-o", subject], check=True)
    inputs = (source, HERE / "atomic_config.rs", HERE / "installed_writer.rs", Path(__file__).resolve(), HERE.parents[1] / "gui/src/win32_instance.rs")
    receipt = {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "target": target, "executableSha256": sha(subject), "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs},
               "rustc": subprocess.check_output([rustc, "-vV"], text=True)}
    (out / "build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
