#!/usr/bin/env python3
"""Resolve Flatpak manifest source fragments into a JSON manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing Python module 'yaml'. Install PyYAML "
        "(Fedora: python3-pyyaml, Debian/Ubuntu: python3-yaml)."
    ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def load_source_fragment(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise SystemExit(f"Flatpak source fragment must be a JSON array of objects: {path}")
    return data


def expand_module_sources(module: dict[str, Any], manifest_dir: Path) -> None:
    sources = module.get("sources", [])
    if not isinstance(sources, list):
        raise SystemExit(f"Flatpak module sources must be a list: {module.get('name', '<unnamed>')}")

    expanded_sources: list[dict[str, Any]] = []
    for source in sources:
        if isinstance(source, str):
            expanded_sources.extend(load_source_fragment(manifest_dir / source))
        elif isinstance(source, dict):
            expanded_sources.append(source)
        else:
            raise SystemExit(f"Unsupported Flatpak source entry: {source!r}")

    module["sources"] = expanded_sources


def main() -> int:
    args = parse_args()
    manifest = args.manifest
    manifest_dir = manifest.parent.resolve()

    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Flatpak manifest must be a mapping: {manifest}")

    modules = data.get("modules", [])
    if not isinstance(modules, list):
        raise SystemExit("Flatpak manifest modules must be a list.")

    for module in modules:
        if isinstance(module, dict):
            expand_module_sources(module, manifest_dir)

    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote resolved Flatpak manifest: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
