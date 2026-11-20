"""Reproduce audited YAML directory sources; never export the original logo archive."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tomllib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROMOTION = (b'<a href="https://www.jetbrains.com/?from=rust-base64"><img src="/icon_CLion.svg" height="40px"/></a>\n\n'
             b'Made with CLion. Thanks to JetBrains for supporting open source!\n\n')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def graph(metadata: dict) -> list[dict]:
    packages = {entry["id"]: entry for entry in metadata["packages"]}
    return sorted([{"name": packages[node["id"]]["name"], "version": packages[node["id"]]["version"],
                    "features": sorted(node["features"])} for node in metadata["resolve"]["nodes"]
                   if packages[node["id"]]["source"]], key=lambda entry: entry["name"])


def source_files(archive: Path, name: str, checksum: str) -> tuple[dict[str, bytes], list[dict]]:
    if file_digest(archive) != checksum:
        raise ValueError("original archive checksum mismatch")
    files, changes = {}, []
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name
                    or not path.parts or path.parts[0] != name):
                raise ValueError("unsafe archive member")
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) < 2:
                raise ValueError("links and non-file members are forbidden")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in files or any(change["path"] == relative for change in changes):
                raise ValueError("duplicate archive member")
            data = stream.extractfile(member).read()
            if name == "base64-0.23.1" and relative == "icon_CLion.svg":
                changes.append({"path": relative, "action": "removed-non-build-promotional-image",
                                "original_sha256": digest(data)})
                continue
            if name == "base64-0.23.1" and relative == "README.md":
                if data.count(PROMOTION) != 1:
                    raise ValueError("expected exact promotional README block not found")
                filtered = data.replace(PROMOTION, b"")
                changes.append({"path": relative, "action": "removed-promotional-reference",
                                "original_sha256": digest(data), "filtered_sha256": digest(filtered)})
                data = filtered
            files[relative] = data
    if name == "base64-0.23.1" and len(changes) != 2:
        raise ValueError("incomplete audited base64 filter")
    return files, sorted(changes, key=lambda entry: entry["path"])


def prepare(cargo_home: Path, destination: Path, inputs: dict) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    observed = []
    for entry in inputs["packages"]:
        name = entry["name"] + "-" + entry["version"]
        candidates = list((cargo_home / "registry/cache").glob(f"*/{name}.crate"))
        if len(candidates) != 1:
            raise ValueError(f"missing or ambiguous private archive for {name}")
        files, changes = source_files(candidates[0], name, entry["archive_sha256"])
        hashes = {path: digest(data) for path, data in sorted(files.items())}
        identity = {"name": name, "original_archive_sha256": entry["archive_sha256"],
                    "filtered_tree_sha256": digest(canonical(hashes)), "files": hashes, "changes": changes}
        if "filtered_tree_sha256" in entry and identity["filtered_tree_sha256"] != entry["filtered_tree_sha256"]:
            raise ValueError("filtered directory source identity differs from reviewed input")
        for notice in entry["notices"]:
            if hashes[notice["path"]] != notice["sha256"]:
                raise ValueError("a supplied license notice changed")
        directory = destination / name
        for relative, data in files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # Cargo directory sources retain the original package identity. The full
        # explicit source-filter manifest records the changed local file identity.
        write_json(directory / ".cargo-checksum.json", {"files": hashes, "package": entry["archive_sha256"]})
        observed.append(identity)
    return {"format": "ifw-rw02-yaml-filtered-sources-v1", "packages": observed}


def bundle(source: Path, manifest: dict, destination: Path) -> None:
    """Bind the reviewed source bytes independently of a host's DEFLATE encoder."""
    with tarfile.open(destination, mode="w:", format=tarfile.PAX_FORMAT) as archive:
        members = {"source-filter.json": canonical(manifest)}
        members.update({"vendor/" + path.relative_to(source).as_posix(): path.read_bytes()
                        for path in source.rglob("*") if path.is_file()})
        for name, data in sorted(members.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            member.mtime = 0
            archive.addfile(member, io.BytesIO(data))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-inventory", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reviewed = {(entry["name"], entry["version"]): entry
                for entry in json.loads(args.reviewed_inventory.read_text(encoding="utf-8"))}
    lock = tomllib.loads((HERE / "Cargo.lock").read_text(encoding="utf-8"))
    packages = []
    for package in lock["package"]:
        if "checksum" not in package:
            continue
        entry = reviewed[package["name"], package["version"]]
        if entry["archive_sha256"] != package["checksum"]:
            raise ValueError("a locked package lacks matching prior source review")
        packages.append({key: entry[key] for key in
                         ("name", "version", "license_declared", "archive_sha256", "repository", "notices", "assets", "build_targets")})
    inputs = {"format": "ifw-rw02-yaml-inputs-v1", "original_inventory_sha256": file_digest(args.reviewed_inventory),
              "lock_sha256": file_digest(HERE / "Cargo.lock"), "packages": packages}
    args.output.mkdir(parents=True, exist_ok=False)
    observed = prepare(args.cargo_home, args.output / "vendor", inputs)
    for entry, actual in zip(packages, observed["packages"], strict=True):
        entry["filtered_tree_sha256"] = actual["filtered_tree_sha256"]
        entry["source_filter"] = actual["changes"]
        entry["license_selected"] = ("MIT AND Unicode-3.0" if entry["name"] == "unicode-ident" else
                                      "MIT AND BSD-3-Clause" if entry["name"] == "encoding_rs" else "MIT")
    targets = json.loads((ROOT / "rust/toolchain-inputs.json").read_text(encoding="utf-8"))["targets"]
    inputs["target_graphs"] = {}
    for target in sorted(targets):
        metadata = json.loads(subprocess.check_output([
            "cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"), "--format-version", "1",
            "--locked", "--offline", "--filter-platform", target], cwd=ROOT))
        inputs["target_graphs"][target] = graph(metadata)
    write_json(args.output / "source-filter.json", observed)
    bundle(args.output / "vendor", observed, args.output / "filtered-sources.tar")
    inputs["filtered_bundle_sha256"] = file_digest(args.output / "filtered-sources.tar")
    write_json(HERE / "inputs.json", inputs)
    print(f"Recorded {len(packages)} reviewed archives; filtered source bundle {inputs['filtered_bundle_sha256']}")


if __name__ == "__main__":
    main()
