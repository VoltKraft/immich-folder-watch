#!/usr/bin/env python3
"""Restore an isolated, pinned-SDK NuGet feed for offline Flatpak builds.

The source manifest selects the exact host SDK. Restore runs from a temporary
global.json with roll-forward disabled, fresh NuGet caches, and temporary build
artifacts, leaving the source checkout unchanged. Only nuget.org packages whose
downloaded bytes match the NuGet archive checksum enter the deterministic feed.
No output is replaced until the complete restore and all checks succeed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


NUGET_INDEX = "https://api.nuget.org/v3/index.json"
COMPONENT_RE = re.compile(r"[a-z0-9][a-z0-9._+-]*")
APP_ID = "io.github.voltkraft.immich-folder-watch"
PROJECT = Path("src/ImmichFolderWatch.App.Linux/ImmichFolderWatch.App.Linux.csproj")


class GeneratorError(ValueError):
    """The restored inputs cannot produce a complete, verified offline feed."""


def sdk_version(source_root: Path) -> str:
    """Read the exact SDK from the same manifest consumed by native builders."""
    spec = importlib.util.spec_from_file_location(
        "read_flatpak_sdk", Path(__file__).with_name("read-flatpak-sdk.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_sdk_metadata(
        source_root / "packaging/flatpak/flathub" / f"{APP_ID}.yml"
    )["version"]


def package_identity(value: str) -> tuple[str, str]:
    """Normalize a NuGet identity while rejecting traversal and invalid names."""
    parts = value.lower().split("/")
    if len(parts) != 2 or any(not COMPONENT_RE.fullmatch(part) for part in parts):
        raise GeneratorError(f"invalid restored package identity: {value}")
    return parts[0], parts[1]


def required_packages(artifacts: Path, package_cache: Path) -> set[tuple[str, str]]:
    """Include resolved libraries and SDK/runtime packs requested by every project."""
    asset_files = sorted(artifacts.rglob("project.assets.json"))
    if not asset_files:
        raise GeneratorError("restore produced no project.assets.json files")
    required: set[tuple[str, str]] = set()
    for asset_file in asset_files:
        assets = json.loads(asset_file.read_text(encoding="utf-8"))
        folders = assets.get("packageFolders", {})
        if not folders or any(Path(folder).resolve() != package_cache.resolve() for folder in folders):
            raise GeneratorError("restore used a package folder outside the isolated cache")
        for identity, library in assets.get("libraries", {}).items():
            if library.get("type") == "package":
                required.add(package_identity(identity))
        for framework in assets.get("project", {}).get("frameworks", {}).values():
            for dependency in framework.get("downloadDependencies", []):
                version_range = dependency.get("version", "")
                match = re.fullmatch(r"\[([^,\[\]]+),\s*([^,\[\]]+)\]", version_range)
                if match is None or match[1] != match[2]:
                    raise GeneratorError("download dependency must have one exact version")
                required.add(package_identity(f"{dependency['name']}/{match[1]}"))
    return required


def collect_sources(package_cache: Path, artifacts: Path, runtime: str) -> list[dict[str, str]]:
    """Verify the complete fresh cache and produce official NuGet download entries."""
    required = required_packages(artifacts, package_cache)
    found: set[tuple[str, str]] = set()
    sources: list[dict[str, str]] = []
    for directory in sorted(package_cache.glob("*/*")):
        if not directory.is_dir() or directory.is_symlink() or directory.parent.is_symlink():
            raise GeneratorError("package cache contains an unexpected entry")
        package, version = package_identity(directory.relative_to(package_cache).as_posix())
        filename = f"{package}.{version}.nupkg"
        archive = directory / filename
        hash_file = directory / f"{filename}.sha512"
        metadata_file = directory / ".nupkg.metadata"
        if any(path.is_symlink() or not path.is_file() for path in (archive, hash_file, metadata_file)):
            raise GeneratorError(f"package archive or checksum metadata is missing: {package}/{version}")
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        if metadata.get("source") != NUGET_INDEX:
            raise GeneratorError(f"package was not restored from the official NuGet source: {package}/{version}")
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha512").digest()
        # .nupkg.metadata contentHash excludes the signing file and is not an
        # archive checksum: https://github.com/NuGet/Home/wiki/Nupkg-Metadata-File
        try:
            expected = base64.b64decode(hash_file.read_text(encoding="utf-8").strip(), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GeneratorError(f"invalid NuGet checksum: {package}/{version}") from exc
        if len(expected) != 64 or digest != expected:
            raise GeneratorError(f"NuGet archive checksum mismatch: {package}/{version}")
        found.add((package, version))
        sources.append({
            "type": "file",
            "url": f"https://api.nuget.org/v3-flatcontainer/{package}/{version}/{filename}",
            "sha512": digest.hex(),
            "dest": "nuget-sources",
            "dest-filename": filename,
        })
    missing = required - found
    if missing:
        raise GeneratorError("restored packages are absent from the fresh cache: " + ", ".join(
            f"{package}/{version}" for package, version in sorted(missing)
        ))
    if not any(package == f"microsoft.netcore.app.runtime.{runtime}" for package, _ in found):
        raise GeneratorError(f"self-contained runtime pack is missing for {runtime}")
    return sorted(sources, key=lambda source: source["dest-filename"])


def generate_sources(source_root: Path, runtime: str, output: Path) -> int:
    """Restore and atomically replace the feed, cleaning temporary caches on failure."""
    if runtime not in ("linux-x64", "linux-arm64"):
        raise GeneratorError(f"unsupported runtime: {runtime}")
    source_root = source_root.resolve()
    project = source_root / PROJECT
    if not project.is_file():
        raise GeneratorError(f"Linux project not found: {project}")
    version = sdk_version(source_root)
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise GeneratorError(f"dotnet is not on PATH; install SDK {version}")

    with tempfile.TemporaryDirectory(prefix="immich-flatpak-nuget-") as temporary:
        root = Path(temporary)
        packages = root / "packages"
        artifacts = root / "artifacts"
        (root / "global.json").write_text(json.dumps({
            "sdk": {"version": version, "rollForward": "disable", "allowPrerelease": False}
        }), encoding="utf-8")
        config = root / "NuGet.Config"
        config.write_text(
            '<configuration><packageSources><clear/><add key="nuget.org" value="'
            + NUGET_INDEX + '"/></packageSources><fallbackPackageFolders><clear/>'
            '</fallbackPackageFolders></configuration>', encoding="utf-8"
        )
        environment = {
            **os.environ,
            "DOTNET_CLI_HOME": str(root / "cli"),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "true",
            "NUGET_PACKAGES": str(packages),
            "NUGET_HTTP_CACHE_PATH": str(root / "http-cache"),
            "NUGET_SCRATCH": str(root / "scratch"),
            "NUGET_PLUGINS_CACHE_PATH": str(root / "plugins-cache"),
        }
        sdk = subprocess.run(
            [dotnet, "--version"], cwd=root, env=environment, capture_output=True, text=True
        )
        if sdk.returncode != 0 or sdk.stdout.strip() != version:
            raise GeneratorError(f"the exact Flatpak SDK {version} must be installed and selected")
        print(f"Restoring {runtime} with pinned .NET SDK {version} into a fresh package cache.", flush=True)
        result = subprocess.run([
            dotnet, "restore", str(project), "--runtime", runtime,
            "-p:SelfContained=true", "--packages", str(packages),
            "--artifacts-path", str(artifacts), "--configfile", str(config),
            "--source", NUGET_INDEX, "--force", "--no-http-cache", "--disable-build-servers",
        ], cwd=root, env=environment)
        if result.returncode != 0:
            raise GeneratorError(f"dotnet restore failed for {runtime} (exit code {result.returncode})")
        sources = collect_sources(packages, artifacts, runtime)

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
            temporary_output = Path(stream.name)
            json.dump(sources, stream, indent=4, sort_keys=True)
            stream.write("\n")
        temporary_output.replace(output)
    finally:
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)
    print(f"Wrote {output} for {runtime}: {len(sources)} verified packages.")
    return len(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--runtime", required=True, choices=("linux-x64", "linux-arm64"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        generate_sources(args.source_root, args.runtime, args.output)
    except (GeneratorError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
