"""Restore the reviewed compiler inputs shared by the native inventory workers."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from prepare import HERE, ROOT, bundle, file_digest, prepare


def restore(cache, vendor, archive, offline):
    review = json.loads((HERE / "inputs.json").read_bytes())
    if file_digest(HERE / "Cargo.lock") != review["lock_sha256"]:
        raise ValueError("The inventory acquisition lock differs from its review")
    command = ["cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"),
               "--locked", "--format-version", "1"]
    if offline:
        command.append("--offline")
    subprocess.run(command, cwd=ROOT, env=dict(os.environ, CARGO_HOME=str(cache)),
                   stdout=subprocess.DEVNULL, check=True)
    observed = prepare(cache, vendor, review)
    archive.parent.mkdir(parents=True, exist_ok=True)
    bundle(vendor, observed, archive)
    if file_digest(archive) != review["filtered_bundle_sha256"]:
        raise ValueError("The filtered worker sources differ from the audited archive")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo-home", type=Path, default=ROOT / "artifacts/rust/assessment-cache")
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    restore(args.cargo_home.resolve(), args.vendor.resolve(), args.archive.resolve(), args.offline)
