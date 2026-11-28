"""Check the native Rust compiler used to produce feasibility evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def native_architecture():
    if sys.platform == "win32":
        # The runner's Python or shell can be an emulated process. Query the
        # OS, then check the compiler's own host triple separately.
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = kernel.IsWow64Process2
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.WORD)]
        query.restype = wintypes.BOOL
        process, native = wintypes.WORD(), wintypes.WORD()
        if not query(kernel.GetCurrentProcess(), ctypes.byref(process), ctypes.byref(native)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {0x8664: "x86_64", 0xAA64: "aarch64"}.get(native.value)
    return platform.machine().lower()


def main():
    inputs = json.loads((Path(__file__).resolve().parents[2] / "rust/toolchain-inputs.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["targets"]))
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--archive", type=Path, help="also check a downloaded full toolchain distribution")
    args = parser.parse_args()
    version = subprocess.check_output([args.rustc, "-vV"], text=True)
    fields = dict(line.split(": ", 1) for line in version.splitlines() if ": " in line)
    expected_os = {"win32": "pc-windows-msvc", "linux": "unknown-linux-gnu"}.get(sys.platform)
    expected_host = f"{native_architecture()}-{expected_os}"
    if (fields.get("release") != inputs["version"] or fields.get("commit-hash") != inputs["commit"]
            or fields.get("host") != args.target or expected_host != args.target):
        raise SystemExit(f"Compiler or native host mismatch for {args.target} (process host {expected_host}):\n{version}")
    if args.archive:
        with args.archive.open("rb") as archive:
            checksum = hashlib.file_digest(archive, "sha256").hexdigest()
        if checksum != inputs["targets"][args.target]["rust"]["sha256"]:
            raise SystemExit("Rust toolchain archive SHA-256 mismatch")
    print(version.strip())


if __name__ == "__main__":
    main()
