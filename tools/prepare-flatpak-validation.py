#!/usr/bin/env python3
"""Prepare a Flatpak validation candidate from a clean, immutable Git checkout.

Unlike release preparation, this requires no tag or GitHub release. Both native
builders consume the same commit-pinned manifest and merged offline NuGet feed.
The caller must make the commit available from the manifest's public Git remote.
The output directory must be empty or new, outside the checkout and all inputs.
This command does not build, commit, push, or publish anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


RELEASE_SPEC = importlib.util.spec_from_file_location(
    "prepare_flathub_release", Path(__file__).with_name("prepare-flathub-release.py")
)
assert RELEASE_SPEC is not None and RELEASE_SPEC.loader is not None
RELEASE = importlib.util.module_from_spec(RELEASE_SPEC)
RELEASE_SPEC.loader.exec_module(RELEASE)
ManifestError = RELEASE.ManifestError
APP_ID = RELEASE.APP_ID


def validate_checkout(source_root: Path, commit: str) -> None:
    """Require the requested SHA and a clean repository, allowing ignored output."""
    if not RELEASE.SHA_RE.fullmatch(commit):
        raise ManifestError("commit must be a full 40-character hexadecimal SHA")
    if Path(RELEASE.git_output(source_root, "rev-parse", "--show-toplevel")).resolve() != source_root:
        raise ManifestError("source-root must be the root of the validation checkout")
    if RELEASE.git_output(source_root, "rev-parse", "HEAD").lower() != commit.lower():
        raise ManifestError("validation checkout HEAD does not match commit")
    if RELEASE.git_output(source_root, "status", "--porcelain", "--untracked-files=all"):
        raise ManifestError("validation checkout must have no tracked or untracked changes")


def prepare_validation(
    source_root: Path,
    commit: str,
    nuget_x64: Path,
    nuget_arm64: Path,
    output_dir: Path,
) -> list[Path]:
    """Validate all inputs before writing exactly three candidate packaging files."""
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(source_root) or source_root.is_relative_to(output_dir):
        raise ManifestError("source-root and output-dir must not overlap")
    for input_path in (nuget_x64, nuget_arm64):
        if input_path.resolve().is_relative_to(output_dir):
            raise ManifestError("output-dir must not contain an input file")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ManifestError("output-dir must be empty or new")

    validate_checkout(source_root, commit)
    manifest_dir = source_root / "packaging" / "flatpak" / "flathub"
    try:
        manifest = RELEASE.PIN_MODULE.pin_git_source(
            (manifest_dir / f"{APP_ID}.yml").read_text(encoding="utf-8"), commit
        )
    except RELEASE.PIN_MODULE.ManifestError as exc:
        raise ManifestError(str(exc)) from exc
    sources = RELEASE.merge_nuget_sources(
        RELEASE.read_json(nuget_x64), RELEASE.read_json(nuget_arm64)
    )
    config = RELEASE.read_json(manifest_dir / "flathub.json")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Clean Git checkout to validate")
    parser.add_argument("--commit", required=True, help="Full immutable Git commit SHA")
    parser.add_argument("--nuget-x64", type=Path, required=True, help="Generated linux-x64 NuGet source list")
    parser.add_argument("--nuget-arm64", type=Path, required=True, help="Generated linux-arm64 NuGet source list")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty directory outside the checkout")
    args = parser.parse_args()
    try:
        outputs = prepare_validation(
            args.source_root, args.commit, args.nuget_x64, args.nuget_arm64, args.output_dir
        )
    except (ManifestError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for output in outputs:
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
