#!/usr/bin/env python3
"""Normalize local source paths in a resolved Flatpak manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Make relative source.path entries in a resolved Flatpak "
            "manifest absolute, using the original manifest directory."
        )
    )
    parser.add_argument("resolved_manifest", type=Path)
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        required=True,
        help="Directory that contains the original YAML manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_dir = args.manifest_dir.resolve()
    resolved_manifest = args.resolved_manifest
    data = json.loads(resolved_manifest.read_text(encoding="utf-8"))

    missing_paths: list[Path] = []

    for module in data.get("modules", []):
        for source in module.get("sources", []):
            source_path = source.get("path")
            if not source_path:
                continue

            normalized = Path(source_path)
            if not normalized.is_absolute():
                normalized = (manifest_dir / normalized).resolve()

            if not normalized.exists():
                missing_paths.append(normalized)

            source["path"] = str(normalized)

    if missing_paths:
        missing = "\n".join(f"  - {path}" for path in missing_paths)
        raise SystemExit(f"Resolved Flatpak source path does not exist:\n{missing}")

    resolved_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
