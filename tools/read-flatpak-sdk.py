#!/usr/bin/env python3
"""Read the exact build-only .NET SDK pins from the shared Flatpak manifest.

The two archive source blocks are the source of truth for restore, publish,
and CI SDK selection. This deliberately validates their restricted YAML shape
instead of interpreting arbitrary YAML or introducing a parser dependency.
Changing the shape requires updating this helper and its regression tests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SDK_SOURCE_RE = re.compile(
    r"^      - type: archive\n"
    r"        dest: dotnet-sdk\n"
    r"        strip-components: 0\n"
    r"        only-arches: \[(?P<arch>x86_64|aarch64)\]\n"
    r"        url: (?P<url>\S+)\n"
    r"        sha512: (?P<sha512>[a-f0-9]{128})\n",
    re.MULTILINE,
)
SDK_URL_RE = re.compile(
    r"https://builds\.dotnet\.microsoft\.com/dotnet/Sdk/"
    r"(?P<version>10\.0\.[1-9][0-9]*)/dotnet-sdk-(?P=version)-"
    r"(?P<rid>linux-x64|linux-arm64)\.tar\.gz"
)
ARCHITECTURES = {"linux-x64": "x86_64", "linux-arm64": "aarch64"}


class MetadataError(ValueError):
    """The manifest cannot provide a consistent, verified SDK selection."""


def read_sdk_metadata(manifest: Path) -> dict:
    """Return the common SDK version and both official archive pins.

    Older manifests using an SDK extension do not supply this contract and
    fail explicitly. No remote metadata is fetched and no source is changed.
    """
    content = manifest.read_text(encoding="utf-8")
    runtime = re.search(r'^runtime-version: [\"\']?(\d{2}\.\d{2})[\"\']?$', content, re.MULTILINE)
    if runtime is None:
        raise MetadataError("Flatpak manifest is missing a supported runtime-version")
    matches = list(SDK_SOURCE_RE.finditer(content))
    sdk_urls = re.findall(r"^\s+url: \S*/dotnet-sdk-\S+$", content, re.MULTILINE)
    if len(matches) != 2 or len(sdk_urls) != 2:
        raise MetadataError("Flatpak manifest must contain the two pinned build-only SDK archives; older SDK-extension manifests are unsupported")
    versions = set()
    sources = {}
    for match in matches:
        url = match.group("url")
        details = SDK_URL_RE.fullmatch(url)
        if details is None:
            raise MetadataError("SDK source must be an exact stable .NET 10 archive from builds.dotnet.microsoft.com")
        rid = details.group("rid")
        if match.group("arch") != ARCHITECTURES[rid] or rid in sources:
            raise MetadataError("SDK archives must match distinct x86_64 and aarch64 architecture filters")
        versions.add(details.group("version"))
        sources[rid] = {
            "flatpak_arch": match.group("arch"),
            "url": url,
            "sha512": match.group("sha512"),
        }
    if len(versions) != 1 or set(sources) != set(ARCHITECTURES):
        raise MetadataError("both architectures must use the same exact SDK version")
    return {"version": versions.pop(), "runtime_version": runtime.group(1), "sources": sources}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--format", choices=("version", "json"), default="json")
    args = parser.parse_args()
    try:
        result = read_sdk_metadata(args.manifest)
    except (OSError, MetadataError) as exc:
        print(f"Invalid Flatpak SDK metadata: {exc}", file=sys.stderr)
        return 1
    print(result["version"] if args.format == "version" else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
