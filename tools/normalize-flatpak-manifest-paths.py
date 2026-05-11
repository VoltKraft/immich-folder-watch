#!/usr/bin/env python3
"""Normalize local source handling in a resolved Flatpak manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resolved_manifest", type=Path)
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        required=True,
        help="Directory that contains the original YAML manifest.",
    )
    return parser.parse_args()


def add_build_arg(module: dict, build_arg: str) -> None:
    build_options = module.setdefault("build-options", {})
    build_args = build_options.setdefault("build-args", [])
    if build_arg not in build_args:
        build_args.append(build_arg)


def main() -> int:
    args = parse_args()
    manifest_dir = args.manifest_dir.resolve()
    resolved_manifest = args.resolved_manifest
    data = json.loads(resolved_manifest.read_text(encoding="utf-8"))

    missing_paths: list[Path] = []
    mounted_source_archive: Path | None = None
    mounted_nuget_sources: Path | None = None

    for module in data.get("modules", []):
        normalized_sources = []

        for source in module.get("sources", []):
            source_path = source.get("path")
            if not source_path:
                normalized_sources.append(source)
                continue

            normalized = Path(source_path)
            if not normalized.is_absolute():
                normalized = (manifest_dir / normalized).resolve()

            if not normalized.exists():
                missing_paths.append(normalized)

            if normalized.name == "source.tar.gz":
                add_build_arg(module, f"--filesystem={normalized.parent}:ro")

                replaced_command = False
                commands = module.get("build-commands", [])
                rewritten_commands = []
                for command in commands:
                    rewritten = command.replace(
                        "tar -xzf source.tar.gz && rm source.tar.gz",
                        f"tar -xzf {normalized}",
                    )
                    if rewritten != command:
                        replaced_command = True
                    rewritten_commands.append(rewritten)

                if not replaced_command:
                    raise SystemExit(
                        "Resolved Flatpak manifest did not contain the expected "
                        "'tar -xzf source.tar.gz && rm source.tar.gz' command."
                    )

                module["build-commands"] = rewritten_commands
                mounted_source_archive = normalized
                continue

            if normalized.name == "nuget-sources":
                add_build_arg(module, f"--filesystem={normalized}:ro")
                commands = module.get("build-commands", [])
                copy_command = f"rm -rf nuget-sources && cp -a {normalized} nuget-sources"
                if copy_command not in commands:
                    insert_at = 1 if commands and commands[0].startswith("tar -xzf ") else 0
                    commands.insert(insert_at, copy_command)
                module["build-commands"] = commands
                mounted_nuget_sources = normalized
                continue

            source["path"] = str(normalized)
            normalized_sources.append(source)

        module["sources"] = normalized_sources

    if mounted_source_archive is None:
        raise SystemExit("Resolved Flatpak manifest does not contain source.tar.gz.")

    if mounted_nuget_sources is None:
        raise SystemExit("Resolved Flatpak manifest does not contain nuget-sources.")

    if missing_paths:
        missing = "\n".join(f"  - {path}" for path in missing_paths)
        raise SystemExit(f"Resolved Flatpak source path does not exist:\n{missing}")

    resolved_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Mounted Flatpak source archive: {mounted_source_archive}")
    print(f"Mounted Flatpak NuGet sources: {mounted_nuget_sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
