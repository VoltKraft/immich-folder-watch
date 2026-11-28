"""Rebuild the reviewed GUI and YAML directory source from their original crate archives."""
import argparse
import errno
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA / "combined-profile"))
from sources import local_caches, locked, prepare_registry, read, sha256, write, yaml_prepare

# Measured from the two locks against the original complete combined compiler-tree receipt.
RECEIPT_SHA256 = "1fde2469c1e00f08882bb863eca1110eb1c45fe78fe55e4b7767fcd3db0388e3"
CORRECTED_RECEIPT_SHA256 = "6a169a3b2c15a259d24ee23f10fc4625876808ae121e2edd15469ab1e96d0478"
GUI_RECEIPT_SHA256 = "0a4cc8dc3db5daee67b22898a0b4b3ca09a15fd157691e3d19eb72c134f885fe"
GUI_LOCK_RECEIPTS = {
    "6716b1cc5835c1fbec9c9485773bdacfd63c4f5d01568a9aa94a8839c2e81d25": GUI_RECEIPT_SHA256,
    "bdda6dc843f34b90bbe9efd99c84e994fd293a5d6ad88c52f6c70ceb8ea97679": CORRECTED_RECEIPT_SHA256,
}


def selected_inputs():
    selected = locked(QA / "gui")
    for key, digest in locked(QA / "yaml").items():
        if selected.setdefault(key, digest) != digest:
            raise ValueError(f"The checked-in GUI and YAML locks disagree for {key}")
    return selected


def prepare(output, registries, fetch, *, selected=None, receipt_sha=RECEIPT_SHA256):
    if receipt_sha not in {RECEIPT_SHA256, GUI_RECEIPT_SHA256, CORRECTED_RECEIPT_SHA256}:
        raise ValueError("The requested directory source has no reviewed receipt")
    vendor, inputs = prepare_registry(output, registries, fetch, selected_inputs() if selected is None else selected,
                                      jobs=2, stock=receipt_sha != CORRECTED_RECEIPT_SHA256)
    receipt = output / "registry-sources.json"
    write(receipt, inputs)
    if sha256(receipt) != receipt_sha:
        raise ValueError("The compiler directory source differs from the original reviewed projection")
    return vendor


def verify_sources(vendor, selected, catalog):
    projection = {}
    for (name, version), checksum in selected.items():
        key = name + "-" + version
        root = vendor / key
        expected = catalog[key]
        record = read(root / ".cargo-checksum.json")
        archive = vendor.parents[1] / "cache" / vendor.name / (key + ".crate")
        if (root.is_symlink() or not root.is_dir() or archive.is_symlink()
                or record["package"] != checksum or checksum != expected["originalSha256"]
                or sha256(archive) != checksum):
            raise ValueError(f"The supplied compiler source or original archive differs for {key}")
        hashes = {}
        for entry in root.rglob("*"):
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                raise ValueError(f"Unexpected compiler input {entry}")
            if entry.is_file() and entry != root / ".cargo-checksum.json":
                hashes[entry.relative_to(root).as_posix()] = sha256(entry)
        if (hashes != record["files"] or len(hashes) != expected["files"]
                or yaml_prepare.digest(yaml_prepare.canonical(hashes)) != expected["compilerTreeSha256"]):
            raise ValueError(f"The supplied compiler tree differs for {key}")
        projection[key] = expected
    return projection


def compiler_directory(registry, gui=QA / "gui", *, stock=False):
    """Materialize the pinned registry once, then authenticate the actual compiler inputs on each use."""
    lock = sha256(gui / "Cargo.lock")
    if lock not in GUI_LOCK_RECEIPTS:
        raise ValueError("The GUI lock has no reviewed compiler source inventory")
    expected = GUI_LOCK_RECEIPTS[lock]
    if stock and expected == CORRECTED_RECEIPT_SHA256:
        expected = RECEIPT_SHA256
    selected = locked(gui)
    cache = ROOT / "artifacts/rust/gui-registry" / expected
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=cache.parent) as scratch:
            fresh = Path(scratch) / "prepared"
            # The ordinary offline inputs may be split between the GUI and YAML acquisition caches.
            registries = [registry, *(home / "registry" for home in local_caches())]
            prepare(fresh, registries, False, selected=selected, receipt_sha=expected)
            try:
                fresh.rename(cache)
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.EEXIST) or not cache.is_dir():
                    raise
    receipt = cache / "registry-sources.json"
    if sha256(receipt) != expected:
        raise ValueError("The GUI compiler registry receipt differs from its reviewed projection")
    directory = cache / "registry/src/reviewed"
    catalog = read(receipt)
    locked_names = {name + "-" + version for name, version in selected}
    if set(catalog) != locked_names or {p.name for p in directory.iterdir()} != locked_names:
        raise ValueError("The GUI lock differs from the reviewed registry")
    verify_sources(directory, selected, catalog)
    return directory


def configure_cargo_home(home, directory):
    """Select the verified directory for registry crates in a private, offline Cargo home."""
    (home / "config.toml").write_text(
        '[net]\noffline = true\n[source.crates-io]\nreplace-with = "combined-review"\n'
        '[source.combined-review]\ndirectory = ' + json.dumps(str(directory)) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", action="append", type=Path, help="Cargo home with original registry/cache archives")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing checksum-pinned public original crates")
    parser.add_argument("--corrected", action="store_true", help="Prepare the ordinary Flatpak-capable compiler sources")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "artifacts/rust"):
        parser.error("Use a new output directory below artifacts/rust")
    print(prepare(output, [home / "registry" for home in args.cache or local_caches()], args.fetch,
                  receipt_sha=CORRECTED_RECEIPT_SHA256 if args.corrected else RECEIPT_SHA256))
