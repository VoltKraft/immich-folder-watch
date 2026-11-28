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


def notice_path(path, license_file=None):
    name = path.name.lower()
    return (any(word in name for word in ("license", "licence", "copying", "copyright", "notice"))
            or path.stem.lower() in {"authors", "contributors", "credits", "attribution", "attributions", "patents"}
            or any(part.lower().lstrip(".") in {"licenses", "licences"} for part in path.parts[:-1])
            or path.as_posix() == license_file)


def protocol_input(name, path):
    # wayland-client generates both its core interfaces and client bindings from wayland.xml.
    # wayland-scanner's two scanner_assets XMLs are test fixtures of the generator.
    return (name.startswith("wayland-protocols") and path.suffix == ".xml"
            or name == "wayland-client" and path.as_posix() == "wayland.xml")


def protocol_record(original):
    protocol = ET.fromstring(original)
    if protocol.tag != "protocol":
        return None
    notice = protocol.findtext("copyright", default="").strip()
    return {"sha256": hashlib.sha256(original).hexdigest(), "copyright": notice,
            "licenseIds": sorted(set(re.findall(r"SPDX-License-Identifier:\s*([^\r\n]+)", notice)))}


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
            relative = path.as_posix()
            if protocol_input(package["name"], path):
                with contents.extractfile(member) as stream:
                    protocol = protocol_record(stream.read())
                if protocol is not None:
                    files.setdefault("protocols", {})[relative] = protocol
            if notice_path(path, package.get("license_file")):
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


def private_gui_input(root, name, approved, *, source_root=None):
    from gui import source_profile
    expected = (source_root or source_profile.SOURCES) / name
    if root != expected or source_profile.tree_info(root) != approved["trees"][name]:
        raise ValueError(f"Private GUI package is outside its reviewed path or changed: {name}")
    extras = {"native": [], "shaders": [], "fonts": []}
    for file in sorted(root.rglob("*")):
        if file.is_file():
            for section, suffixes in (("native", NATIVE), ("shaders", SHADER), ("fonts", FONT)):
                if file.suffix.lower() in suffixes:
                    extras[section].append(file.relative_to(root).as_posix())
    if name == "unicode-bidi":
        archive = approved["originals"]["unicode-bidi-0.3.18.crate"]["sha256"]
        upstream = {"upstreamCommit": approved["unicodeBidiRevision"],
                    "unicodeTableSha256": approved["reconstructedTableSha256"]}
        notices = {k: v for k, v in approved["noticeFiles"].items() if "unicode-bidi-" in k or k.endswith(("Unicode-LICENSE.txt", "ucd-readme.txt"))}
    else:
        archive = approved["baseCrates"][name]
        upstream = {"patchCommit": approved["patchHead"], "appliedRustDiffSha256": approved["appliedRustDiffSha256"]}
        notices = {k: v for k, v in approved["noticeFiles"].items() if "/egui-" in k}
    return {"archiveSha256": archive, "notices": notices, "reconstructedSource": dict(approved["trees"][name], **upstream),
            **extras}

def private_hyper_input(root, archive):
    from realtime import hyper_util_source
    if root != hyper_util_source.SOURCE:
        raise ValueError("Expected the reviewed local CONNECT metadata source")
    receipt = hyper_util_source.verify(archive, root)
    return dict(archiveSha256=receipt["archiveSha256"], reconstructedSource=receipt,
                notices=receipt["notices"], fonts=[], native=[], shaders=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="root Cargo.toml for the assessed workspace")
    parser.add_argument("target", help="native target triple to resolve")
    parser.add_argument("output", type=Path, help="JSON report in an evidence directory")
    parser.add_argument("--verify-unpacked", action="store_true",
                        help="compare the selected compiler input trees to the authenticated crate archives")
    parser.add_argument("--startup-vendor", type=Path, metavar="DIRECTORY",
                        help="audit the qualified staged Linux startup profile using its filtered directory source")
    args = parser.parse_args()
    if args.startup_vendor and not args.verify_unpacked:
        parser.error("--startup-vendor requires --verify-unpacked")
    lock = args.manifest.parent / "Cargo.lock"
    entries = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
    locked = {(p["name"], p["version"], p["source"]): p["checksum"] for p in entries if "checksum" in p}
    manifest = args.manifest.resolve()
    approved = None
    staged = None
    if args.startup_vendor:
        from gui.startup.audit_profile import StartupAudit
        from gui import source_profile
        if manifest == REPOSITORY / "tools/rust-qa/gui/Cargo.toml":
            staged = StartupAudit.for_canonical(manifest, args.startup_vendor, args.target)
        else:
            staged = StartupAudit(manifest, args.startup_vendor, args.target)
        approved = source_profile.validate()
    elif manifest == REPOSITORY / "tools/rust-qa/gui/Cargo.toml":
        from gui import source_profile
        approved = source_profile.validate()
    metadata = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--frozen", "--format-version", "1", "--manifest-path", str(manifest)]
    ))
    active = active_features(manifest, args.target)
    members = {} if staged else repository_members()
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
        if approved is not None and name in approved["trees"]:
            if package["source"] is not None:
                raise ValueError(f"Expected the reconstructed GUI source for {name}")
            entry.update(private_gui_input(Path(package["manifest_path"]).resolve().parent, name, approved,
                                           source_root=staged.gui / "artifacts/text" if staged else None))
        elif name == "hyper-util" and manifest == REPOSITORY / "tools/rust-qa/realtime/Cargo.toml":
            from realtime import hyper_util_source
            if package["source"] is not None:
                raise ValueError("Expected the reconstructed hyper-util package")
            entry.update(private_hyper_input(Path(package["manifest_path"]).resolve().parent, hyper_util_source.ARCHIVE))
        elif package["source"] and package["source"].startswith("registry+"):
            key = name, package["version"], package["source"]
            filtered = staged.filtered(package, locked[key]) if staged else None
            entry.update(archive_inputs(package, locked, args.verify_unpacked and filtered is None))
            if filtered is not None:
                entry["filteredCompilerSource"] = filtered
        elif package["source"] is None:
            path = Path(package["manifest_path"]).resolve()
            if staged:
                entry.update(staged.local(package))
            elif members.get(path) == (name, package["version"]):
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
    if approved is not None:
        feature_record = {f"{name} v{version}": sorted(sets) for (name, version), sets in active.items()}
        feature_bytes = json.dumps(feature_record, sort_keys=True, separators=(",", ":")).encode()
        features = {"packages": len(feature_record), "nativeFeatureSetsSha256": hashlib.sha256(feature_bytes).hexdigest()}
        expected = staged.features if staged else approved["nativeFeatureReports"][args.target]
        if features != expected:
            raise ValueError(f"Selected GUI features differ from the reviewed {args.target} inputs")
        report["desktopFontAssets"] = approved["fonts"]
        report["textNotices"] = approved["noticeFiles"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.target}: {len(packages)} packages, {len(exclusions)} excluded package/feature matches.")
    if exclusions:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
