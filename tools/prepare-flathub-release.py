#!/usr/bin/env python3
"""Prepare the three Flathub files from a clean, published stable release.

The caller fetches the GitHub release JSON and tag, resolves its commit, and
generates NuGet source lists for both Linux architectures from that checkout.
This helper validates those local inputs without network access, pins the app
manifest to the tag and commit, merges checksummed NuGet sources deterministically,
and disables independent external-data updates in flathub.json. It requires
Python's standard library and Git. The output
directory must be empty or new, outside the source checkout, and contain no input.
It does not verify remote assets or package bytes, build, commit, push, or publish.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


APP_ID = "io.github.voltkraft.immich-folder-watch"
TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA512_RE = re.compile(r"^[0-9a-fA-F]{128}$")
NUGET_URL_RE = re.compile(
    r"https://api\.nuget\.org/v3-flatcontainer/"
    r"(?P<package>[a-z0-9][a-z0-9._-]*)/"
    r"(?P<version>[a-z0-9][a-z0-9.+-]*)/"
    r"(?P<filename>[a-z0-9][a-z0-9.+_-]*\.nupkg)"
)
SOURCE_FIELDS = {"type", "url", "sha512", "dest", "dest-filename"}

# Use the automation checkout's existing pinning helper, including when preparing
# releases that predate this script. The release checkout supplies only app files.
PIN_SPEC = importlib.util.spec_from_file_location(
    "prepare_flatpak_release_manifest",
    Path(__file__).with_name("prepare-flatpak-release-manifest.py"),
)
assert PIN_SPEC is not None and PIN_SPEC.loader is not None
PIN_MODULE = importlib.util.module_from_spec(PIN_SPEC)
PIN_SPEC.loader.exec_module(PIN_MODULE)


class ManifestError(ValueError):
    """Raised when local release inputs cannot produce safe Flathub files."""


def read_json(path: Path) -> object:
    """Read a UTF-8 JSON value; all validation occurs before output is written."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read JSON input {path}: {exc}") from exc


def validate_release(release: object) -> str:
    """Return a stable release tag after checking publication and all four assets."""
    if not isinstance(release, dict):
        raise ManifestError("release input must be a GitHub release JSON object")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise ManifestError("release tag must use stable vMAJOR.MINOR.PATCH format")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ManifestError("release must be published, not a draft or prerelease")
    published_at = release.get("published_at")
    try:
        if not isinstance(published_at, str):
            raise ValueError
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ManifestError("release must have a valid published_at timestamp") from exc

    version = tag[1:]
    expected = {
        f"immich-folder-watch-{version}-win-x64.msi",
        f"immich-folder-watch-{version}-win-arm64.msi",
        f"immich-folder-watch-{version}-linux-x64.flatpak",
        f"immich-folder-watch-{version}-linux-arm64.flatpak",
    }
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) != len(expected):
        raise ManifestError("release must contain exactly the four expected assets")
    names: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ManifestError("release assets must be JSON objects")
        name = asset.get("name")
        if not isinstance(name, str) or name not in expected or name in names:
            raise ManifestError("release must contain exactly the four expected assets")
        size = asset.get("size")
        if type(size) is not int or size <= 0 or asset.get("state") != "uploaded":
            raise ManifestError(f"release asset {name} must be nonempty and uploaded")
        names.add(name)
    return tag


def git_output(source_root: Path, *arguments: str) -> str:
    """Run a read-only Git command without interpreting release data as shell code."""
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestError("could not verify the release checkout with Git") from exc
    return result.stdout.strip()


def validate_checkout(source_root: Path, tag: str, commit: str) -> None:
    """Require the repository root, HEAD and fetched tag to identify a clean release.

    Ignored generated build files are permitted; tracked and untracked changes are
    rejected. Git proves local identity only: the workflow fetches the trusted tag.
    """
    if not SHA_RE.fullmatch(commit):
        raise ManifestError("commit must be a full 40-character hexadecimal SHA")
    if Path(git_output(source_root, "rev-parse", "--show-toplevel")).resolve() != source_root:
        raise ManifestError("source-root must be the root of the release checkout")
    if git_output(source_root, "rev-parse", "HEAD").lower() != commit.lower():
        raise ManifestError("release checkout HEAD does not match commit")
    if git_output(source_root, "rev-parse", f"refs/tags/{tag}^{{commit}}").lower() != commit.lower():
        raise ManifestError("release tag does not resolve to commit")
    if git_output(source_root, "status", "--porcelain", "--untracked-files=all"):
        raise ManifestError("release checkout must have no tracked or untracked changes")


def validate_versions(source_root: Path, version: str) -> None:
    """Require both the assembly version source and latest AppStream release to match."""
    props = ET.parse(source_root / "Directory.Build.props").getroot()
    versions = [element.text for element in props.findall(".//Version")]
    if versions != [version]:
        raise ManifestError("Directory.Build.props Version does not match the release tag")
    metainfo = ET.parse(
        source_root / "packaging" / "flatpak" / f"{APP_ID}.metainfo.xml"
    ).getroot()
    latest_release = metainfo.find("releases/release")
    if latest_release is None or latest_release.get("version") != version:
        raise ManifestError("top AppStream release does not match the release tag")


def validate_nuget_sources(value: object, runtime: str) -> list[dict[str, str]]:
    """Accept only the generator's official, checksummed flat-container downloads.

    Every destination is one NuGet package beneath nuget-sources. Unknown source
    options, URL credentials, alternate hosts, traversal and non-SHA512 hashes are
    rejected rather than copied into the Flathub build. The matching .NET runtime
    pack must be present in each architecture's input.
    """
    if not isinstance(value, list) or not value:
        raise ManifestError(f"NuGet sources for {runtime} must be a nonempty JSON array")
    result: list[dict[str, str]] = []
    packages: set[str] = set()
    for source in value:
        if (
            not isinstance(source, dict)
            or set(source) != SOURCE_FIELDS
            or any(not isinstance(field, str) for field in source.values())
        ):
            raise ManifestError("NuGet source must contain exactly the five generator fields")
        if source["type"] != "file" or source["dest"] != "nuget-sources":
            raise ManifestError("NuGet source must be a file with dest nuget-sources")
        match = NUGET_URL_RE.fullmatch(source["url"])
        if match is None:
            raise ManifestError("NuGet source must use an official HTTPS flat-container URL")
        filename = f"{match['package']}.{match['version']}.nupkg"
        if source["dest-filename"] != filename or match["filename"] != filename:
            raise ManifestError("NuGet source destination must match its package URL filename")
        if not SHA512_RE.fullmatch(source["sha512"]):
            raise ManifestError("NuGet source must have a 128-character hexadecimal SHA-512")
        packages.add(match["package"])
        result.append({**source, "sha512": source["sha512"].lower()})
    if f"microsoft.netcore.app.runtime.{runtime}" not in packages:
        raise ManifestError(f"NuGet sources are missing the {runtime} .NET runtime pack")
    return result


def merge_nuget_sources(x64: object, arm64: object) -> list[dict[str, str]]:
    """Merge both validated architectures by destination with stable ordering.

    Identical shared packages are emitted once; a reused destination with different
    content or URL is an error. Ordering and JSON key order do not affect output.
    """
    by_destination: dict[str, dict[str, str]] = {}
    for source in (
        validate_nuget_sources(x64, "linux-x64")
        + validate_nuget_sources(arm64, "linux-arm64")
    ):
        destination = source["dest-filename"]
        previous = by_destination.get(destination)
        if previous is not None and previous != source:
            raise ManifestError(f"conflicting NuGet sources for destination {destination}")
        by_destination[destination] = source
    return [by_destination[name] for name in sorted(by_destination)]


def render_manifest(text: str, tag: str, commit: str) -> str:
    """Pin the tag and commit, removing the obsolete source-only update checker."""
    try:
        pinned = PIN_MODULE.pin_git_source(text, commit)
    except PIN_MODULE.ManifestError as exc:
        raise ManifestError(str(exc)) from exc
    pinned, count = re.subn(
        rf"(?m)^([ \t]*)commit: {commit.lower()}$",
        rf"\g<1>tag: {tag}\n\g<1>commit: {commit.lower()}",
        pinned,
    )
    if count != 1:
        raise ManifestError("expected exactly one pinned Git commit field")
    # Older releases carry an external checker that updates only the Git source;
    # the release workflow now updates the manifest and both NuGet feeds together.
    lines: list[str] = []
    checker_indent: int | None = None
    for line in pinned.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip())
        if checker_indent is not None:
            if not line.strip() or indent > checker_indent:
                continue
            checker_indent = None
        if line.lstrip().startswith("x-checker-data:"):
            checker_indent = indent
            continue
        lines.append(line)
    return "".join(lines)


def prepare_release(
    source_root: Path,
    release_json: Path,
    commit: str,
    nuget_x64: Path,
    nuget_arm64: Path,
    output_dir: Path,
) -> list[Path]:
    """Validate all inputs, then write exactly three files into an empty directory."""
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(source_root) or source_root.is_relative_to(output_dir):
        raise ManifestError("source-root and output-dir must not overlap")
    for input_path in (release_json, nuget_x64, nuget_arm64):
        if input_path.resolve().is_relative_to(output_dir):
            raise ManifestError("output-dir must not contain an input file")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ManifestError("output-dir must be empty or new")

    tag = validate_release(read_json(release_json))
    validate_checkout(source_root, tag, commit)
    validate_versions(source_root, tag[1:])
    manifest_dir = source_root / "packaging" / "flatpak" / "flathub"
    manifest = render_manifest(
        (manifest_dir / f"{APP_ID}.yml").read_text(encoding="utf-8"), tag, commit
    )
    sources = merge_nuget_sources(read_json(nuget_x64), read_json(nuget_arm64))
    config_path = manifest_dir / "flathub.json"
    config = read_json(config_path)
    if not isinstance(config, dict) or config.get("only-arches") not in (
        ["x86_64", "aarch64"], ["aarch64", "x86_64"],
    ):
        raise ManifestError("flathub.json must enable exactly x86_64 and aarch64")
    config["disable-external-data-checker"] = True
    outputs = {
        output_dir / f"{APP_ID}.yml": manifest,
        output_dir / "nuget-sources.json": json.dumps(sources, indent=4, sort_keys=True) + "\n",
        output_dir / "flathub.json": json.dumps(config, indent=2, sort_keys=True) + "\n",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    return list(outputs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Clean checkout of the release tag")
    parser.add_argument("--release-json", type=Path, required=True, help="GitHub REST release response")
    parser.add_argument("--commit", required=True, help="Full resolved release tag commit SHA")
    parser.add_argument("--nuget-x64", type=Path, required=True, help="Generated linux-x64 NuGet source list")
    parser.add_argument("--nuget-arm64", type=Path, required=True, help="Generated linux-arm64 NuGet source list")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty directory outside the checkout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outputs = prepare_release(
            args.source_root, args.release_json, args.commit,
            args.nuget_x64, args.nuget_arm64, args.output_dir,
        )
    except (ManifestError, OSError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for output in outputs:
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
