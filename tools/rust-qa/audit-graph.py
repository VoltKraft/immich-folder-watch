"""Inventory resolved Rust source inputs before selecting a native dependency profile."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[2]
GUI_CRATES = {"eframe", "egui", "epaint", "egui-winit", "egui-wgpu"}
EXCLUDED_FEATURES = {"default_fonts", "system_fonts", "monochrome_emoji_fonts", "inspection"}
EXCLUDED_PACKAGES = {"epaint_default_fonts", "egui_inspection"}
FONT = {".ttf", ".ttc", ".otf", ".otc", ".woff", ".woff2"}
NATIVE = {".c", ".cpp", ".cxx", ".cc", ".h", ".hpp", ".asm", ".s", ".o", ".obj",
          ".so", ".a", ".lib", ".dll", ".exe", ".dylib"}
SHADER = {".spv", ".wgsl", ".glsl", ".hlsl", ".metal", ".dxil", ".dxbc"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_inputs(package, locked, verify_unpacked):
    root = Path(package["manifest_path"]).parent
    registry = root.parent
    archive = registry.parent.parent / "cache" / registry.name / (root.name + ".crate")
    expected = locked[(package["name"], package["version"], package["source"])]
    if verify_unpacked:
        from storage.evidence import verify_archive
        verify_archive(archive, root, expected)
    elif sha256(archive) != expected:
        raise ValueError(f"Archive differs from Cargo.lock: {root.name}")
    files = {"notices": {}, "fonts": [], "native": [], "shaders": []}
    with tarfile.open(archive, "r|gz") as contents:
        for member in contents:
            if not member.isfile():
                continue
            path = Path(member.name).relative_to(root.name)
            name = path.name.lower()
            relative = path.as_posix()
            if package["name"].startswith("wayland-protocols") and path.suffix == ".xml":
                with contents.extractfile(member) as stream:
                    original = stream.read()
                protocol = ET.fromstring(original)
                if protocol.tag == "protocol":
                    notice = protocol.findtext("copyright", default="").strip()
                    files.setdefault("protocols", {})[relative] = {
                        "sha256": hashlib.sha256(original).hexdigest(), "copyright": notice,
                        "licenseIds": sorted(set(re.findall(r"SPDX-License-Identifier:\s*([\w.+-]+)", notice))),
                    }
            if (any(word in name for word in ("license", "licence", "copying", "copyright", "notice"))
                    or relative == package.get("license_file")):
                with contents.extractfile(member) as stream:
                    files["notices"][relative] = hashlib.file_digest(stream, "sha256").hexdigest()
            for category, suffixes in (("fonts", FONT), ("native", NATIVE), ("shaders", SHADER)):
                if path.suffix.lower() in suffixes:
                    files[category].append(relative)
    return {"archiveSha256": expected, **files}


def active_features(manifest, target):
    # Metadata's resolve nodes can contain weak/optional edges that cargo
    # actually omits for this target. Query the selected normal/build tree.
    tree = subprocess.check_output([
        "cargo", "tree", "--frozen", "--workspace", "--manifest-path", str(manifest),
        "--target", target, "--edges", "normal,build", "--prefix", "none", "--format", "{p}|{f}",
    ], text=True)
    active = {}
    for line in tree.splitlines():
        if line == "[build-dependencies]":
            continue
        package, features = line.removesuffix(" (*)").split("|", 1)
        name, version, *_ = package.split()
        if not version.startswith("v"):
            raise ValueError(f"Unexpected Cargo package identifier: {package}")
        key = (name, version[1:])
        active.setdefault(key, set()).add(tuple(sorted(filter(None, features.split(",")))))
    return active


def repository_members():
    workspace = REPOSITORY / "rust"
    source = json.loads(subprocess.check_output([
        "cargo", "metadata", "--frozen", "--no-deps", "--format-version", "1",
        "--manifest-path", str(workspace / "Cargo.toml"),
    ]))
    return {
        Path(p["manifest_path"]).resolve(): (p["name"], p["version"]) for p in source["packages"]
        if p["id"] in source["workspace_members"] and p["source"] is None
        and Path(p["manifest_path"]).resolve().is_relative_to(workspace)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="root Cargo.toml for the assessed workspace")
    parser.add_argument("target", help="native target triple to resolve")
    parser.add_argument("output", type=Path, help="JSON report in an evidence directory")
    parser.add_argument("--verify-unpacked", action="store_true",
                        help="compare the selected compiler input trees to the authenticated crate archives")
    args = parser.parse_args()
    lock = args.manifest.parent / "Cargo.lock"
    entries = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
    locked = {(p["name"], p["version"], p["source"]): p["checksum"] for p in entries if "checksum" in p}
    manifest = args.manifest.resolve()
    metadata = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--frozen", "--format-version", "1", "--manifest-path", str(manifest)]
    ))
    active = active_features(manifest, args.target)
    members = repository_members()
    packages = []
    exclusions = []
    for package in sorted(metadata["packages"], key=lambda p: (p["name"], p["version"])):
        name = package["name"]
        feature_sets = active.get((name, package["version"]))
        if feature_sets is None:
            continue
        features = sorted({feature for group in feature_sets for feature in group})
        if name in EXCLUDED_PACKAGES or (name in GUI_CRATES and set(features) & EXCLUDED_FEATURES):
            exclusions.append({"package": name, "features": features})
        entry = {field: package[field] for field in ("name", "version", "source", "repository", "license", "license_file")}
        entry["features"] = features
        entry["featureSets"] = sorted(feature_sets)
        entry["buildScriptsAndMacros"] = sorted(
            target["name"] for target in package["targets"] if {"custom-build", "proc-macro"} & set(target["kind"])
        )
        if package["source"] and package["source"].startswith("registry+"):
            entry.update(archive_inputs(package, locked, args.verify_unpacked))
        elif package["source"] is None:
            path = Path(package["manifest_path"]).resolve()
            if members.get(path) == (name, package["version"]):
                entry["repositoryManifest"] = path.relative_to(REPOSITORY).as_posix()
            elif package["id"] in metadata["workspace_members"]:
                entry["assessmentWorkspaceMember"] = True
            else:
                raise ValueError(f"Review external path dependency separately: {name}")
        else:
            raise ValueError(f"Review external non-registry source separately: {name}")
        packages.append(entry)
    if len(packages) != len(active):
        raise ValueError("Cargo tree and metadata disagree on the identity of selected packages")
    report = {"target": args.target, "lockSha256": sha256(lock), "packages": packages,
              "excludedPackagesOrFeatures": exclusions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.target}: {len(packages)} packages, {len(exclusions)} excluded package/feature matches.")
    if exclusions:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
