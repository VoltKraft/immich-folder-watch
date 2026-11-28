"""Rebuild the reviewed GUI and YAML directory source from their original crate archives."""
import argparse
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA / "combined-profile"))
from sources import local_caches, locked, prepare_registry, write

# Measured from the two locks against the original complete combined compiler-tree receipt.
RECEIPT_SHA256 = "1fde2469c1e00f08882bb863eca1110eb1c45fe78fe55e4b7767fcd3db0388e3"


def prepare(output, homes, fetch):
    selected = locked(QA / "gui")
    for key, digest in locked(QA / "yaml").items():
        if selected.setdefault(key, digest) != digest:
            raise ValueError(f"The checked-in GUI and YAML locks disagree for {key}")
    vendor, inputs = prepare_registry(output, homes, fetch, selected, jobs=2)
    receipt = output / "registry-sources.json"
    write(receipt, inputs)
    if hashlib.sha256(receipt.read_bytes()).hexdigest() != RECEIPT_SHA256:
        raise ValueError("The compiler directory source differs from the original reviewed projection")
    return vendor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", action="append", type=Path, help="Cargo home with original registry/cache archives")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing checksum-pinned public original crates")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "artifacts/rust"):
        parser.error("Use a new output directory below artifacts/rust")
    print(prepare(output, args.cache or local_caches(), args.fetch))
