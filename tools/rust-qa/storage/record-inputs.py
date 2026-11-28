"""Record already reviewed sources; this generator does not grant dependency approval.

Run only after a separate source/license audit. The supplied review inventory must
identify every locked archive and its actual notices. Cargo runs offline and does
not compile packages. The normal assessment runner only verifies this output.
"""

import argparse
import json
import subprocess
from pathlib import Path

from evidence import external_lock, sha256, target_graph, write_json


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGETS = sorted(json.loads((ROOT / "rust/toolchain-inputs.json").read_text())["targets"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-source-inventory", type=Path, required=True)
    args = parser.parse_args()
    review = {(entry["name"], entry["version"]): entry for entry in
              json.loads(args.reviewed_source_inventory.read_text(encoding="utf-8"))}
    locked = external_lock(HERE / "Cargo.lock")
    metadata = json.loads(subprocess.check_output([
        "cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"),
        "--locked", "--offline", "--format-version", "1"], cwd=ROOT))
    paths = {(entry["name"], entry["version"]): Path(entry["manifest_path"]).parent
             for entry in metadata["packages"] if entry["source"]}
    entries = []
    for key, digest in sorted(locked.items()):
        reviewed = review[key]
        if reviewed["archive_sha256"] != digest or "MIT" not in reviewed["license_declared"]:
            raise ValueError("reviewed input or selected MIT license does not match")
        entry = {field: reviewed[field] for field in
                 ["name", "version", "archive_sha256", "license_declared", "repository", "notices"]}
        entry["license_selected"] = "MIT AND Unicode-3.0" if key[0] == "unicode-ident" else "MIT"
        for notice in entry["notices"]:
            if sha256(paths[key] / notice["path"]) != notice["sha256"]:
                raise ValueError("reviewed license notice does not match cached source")
        if key[0] == "libsqlite3-sys":
            entry["native_license"] = "SQLite deliverable source: public domain"
            entry["native_sources"] = [{"path": name, "sha256": sha256(paths[key] / name)} for name in
                                       ["sqlite3/sqlite3.c", "sqlite3/sqlite3.h", "sqlite3/bindgen_bundled_version.rs", "build.rs"]]
        entries.append(entry)
    graphs = {}
    for target in TARGETS:
        graphs[target] = target_graph(json.loads(subprocess.check_output([
            "cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"), "--locked", "--offline",
            "--format-version", "1", "--filter-platform", target], cwd=ROOT)))
    write_json(HERE / "inputs.json", {
        "format": "ifw-rw02-storage-inputs-v1", "review": "docs/rust/rw02-storage-inputs.md",
        "lock_sha256": sha256(HERE / "Cargo.lock"), "packages": entries, "target_graphs": graphs,
        "sqlite": {"version": "3.54.1", "source_id": "2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76",
                   "flags": "-USQLITE_ENABLE_LOAD_EXTENSION -DSQLITE_OMIT_LOAD_EXTENSION"},
    })
    print(f"Recorded {len(entries)} already reviewed archive identities and four target graphs.")


if __name__ == "__main__":
    main()
