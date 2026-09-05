#!/usr/bin/env python3
"""Create deterministic x64 and ARM64 WinGet manifests for a release."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote


VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PRODUCT_CODE_RE = re.compile(
    r"^\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}$"
)
ARCHITECTURES = ("x64", "arm64")


class ManifestError(ValueError):
    """Raised when release metadata cannot produce safe WinGet manifests."""


def yaml_string(value: str) -> str:
    """Return a JSON-quoted string, which is also a valid YAML scalar."""
    return json.dumps(value, ensure_ascii=False)


def schema_header(metadata: dict[str, object], manifest_type: str) -> str:
    """Return the WinGet schema header for a manifest type."""
    manifest_version = str(metadata["manifestVersion"])
    return (
        "# yaml-language-server: $schema=https://aka.ms/"
        f"winget-manifest.{manifest_type}.{manifest_version}.schema.json"
    )


def read_json_object(path: Path, description: str) -> dict[str, object]:
    """Read *path* and require a JSON object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read {description}: {exc}") from exc

    if not isinstance(value, dict):
        raise ManifestError(f"{description} must be a JSON object")
    return value


def require_string(metadata: dict[str, object], key: str) -> str:
    """Return a required, non-empty string from package metadata."""
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"metadata field '{key}' must be a non-empty string")
    return value.strip()


def validate_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Validate and normalize repository-owned WinGet package metadata."""
    string_fields = (
        "packageIdentifier",
        "packageName",
        "packageLocale",
        "publisher",
        "publisherUrl",
        "publisherSupportUrl",
        "packageUrl",
        "repository",
        "license",
        "moniker",
        "shortDescription",
        "installerLocale",
        "installerType",
        "manifestVersion",
    )
    normalized: dict[str, object] = {
        key: require_string(metadata, key) for key in string_fields
    }

    templates = metadata.get("releaseAssetNameTemplates")
    if not isinstance(templates, dict) or set(templates) != set(ARCHITECTURES):
        raise ManifestError(
            "metadata field 'releaseAssetNameTemplates' must contain exactly "
            "x64 and arm64"
        )
    normalized_templates: dict[str, str] = {}
    for architecture in ARCHITECTURES:
        template = templates.get(architecture)
        if not isinstance(template, str) or template.count("{version}") != 1:
            raise ManifestError(
                f"release asset template for {architecture} must contain "
                "'{version}' exactly once"
            )
        normalized_templates[architecture] = template
    normalized["releaseAssetNameTemplates"] = normalized_templates

    tags = metadata.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
    ):
        raise ManifestError("metadata field 'tags' must be a non-empty string list")
    normalized["tags"] = [tag.strip() for tag in tags]

    if normalized["installerType"] != "wix":
        raise ManifestError("metadata field 'installerType' must be 'wix'")

    return normalized


def validate_installers(
    installers_value: object,
    metadata: dict[str, object],
    version: str,
) -> list[dict[str, str]]:
    """Validate installer descriptors and return them in stable architecture order."""
    if not isinstance(installers_value, list):
        raise ManifestError("installers input must be a JSON array")

    installers_by_architecture: dict[str, dict[str, str]] = {}
    seen_urls: set[str] = set()
    seen_product_codes: set[str] = set()
    templates = metadata["releaseAssetNameTemplates"]
    assert isinstance(templates, dict)
    repository = metadata["repository"]
    assert isinstance(repository, str)

    for index, raw_installer in enumerate(installers_value):
        if not isinstance(raw_installer, dict):
            raise ManifestError(f"installer {index} must be a JSON object")

        required_keys = {"architecture", "url", "sha256", "productCode"}
        if set(raw_installer) != required_keys:
            raise ManifestError(
                f"installer {index} must contain exactly architecture, url, "
                "sha256, and productCode"
            )

        if any(not isinstance(raw_installer[key], str) for key in required_keys):
            raise ManifestError(f"installer {index} fields must all be strings")

        architecture = raw_installer["architecture"]
        url = raw_installer["url"]
        sha256 = raw_installer["sha256"]
        product_code = raw_installer["productCode"]
        assert isinstance(architecture, str)
        assert isinstance(url, str)
        assert isinstance(sha256, str)
        assert isinstance(product_code, str)

        if architecture not in ARCHITECTURES:
            raise ManifestError(f"unsupported installer architecture '{architecture}'")
        if architecture in installers_by_architecture:
            raise ManifestError(f"duplicate installer architecture '{architecture}'")
        if not SHA256_RE.fullmatch(sha256):
            raise ManifestError(f"installer {architecture} has an invalid SHA-256")
        if not PRODUCT_CODE_RE.fullmatch(product_code):
            raise ManifestError(f"installer {architecture} has an invalid ProductCode")
        normalized_product_code = product_code.upper()
        if url in seen_urls:
            raise ManifestError(f"installer {architecture} duplicates another URL")
        if normalized_product_code in seen_product_codes:
            raise ManifestError(
                f"installer {architecture} duplicates another ProductCode"
            )

        template = templates[architecture]
        assert isinstance(template, str)
        asset_name = template.replace("{version}", version)
        expected_url = (
            f"https://github.com/{repository}/releases/download/v{version}/"
            f"{quote(asset_name)}"
        )
        if url != expected_url:
            raise ManifestError(
                f"installer {architecture} URL must be '{expected_url}'"
            )

        installers_by_architecture[architecture] = {
            "architecture": architecture,
            "url": url,
            "sha256": sha256.upper(),
            "productCode": normalized_product_code,
        }
        seen_urls.add(url)
        seen_product_codes.add(normalized_product_code)

    if set(installers_by_architecture) != set(ARCHITECTURES):
        missing = ", ".join(
            architecture
            for architecture in ARCHITECTURES
            if architecture not in installers_by_architecture
        )
        raise ManifestError(f"missing installer architecture(s): {missing}")

    return [installers_by_architecture[architecture] for architecture in ARCHITECTURES]


def render_version_manifest(metadata: dict[str, object], version: str) -> str:
    """Render the WinGet version manifest."""
    return "\n".join(
        (
            schema_header(metadata, "version"),
            "",
            f"PackageIdentifier: {yaml_string(str(metadata['packageIdentifier']))}",
            f"PackageVersion: {yaml_string(version)}",
            f"DefaultLocale: {yaml_string(str(metadata['packageLocale']))}",
            'ManifestType: "version"',
            f"ManifestVersion: {yaml_string(str(metadata['manifestVersion']))}",
            "",
        )
    )


def render_locale_manifest(metadata: dict[str, object], version: str) -> str:
    """Render the WinGet default-locale manifest."""
    fields = (
        ("PackageIdentifier", "packageIdentifier"),
        ("PackageVersion", None),
        ("PackageLocale", "packageLocale"),
        ("Publisher", "publisher"),
        ("PublisherUrl", "publisherUrl"),
        ("PublisherSupportUrl", "publisherSupportUrl"),
        ("PackageName", "packageName"),
        ("PackageUrl", "packageUrl"),
        ("License", "license"),
        ("ShortDescription", "shortDescription"),
        ("Moniker", "moniker"),
    )
    lines: list[str] = [schema_header(metadata, "defaultLocale"), ""]
    for yaml_key, metadata_key in fields:
        value = version if metadata_key is None else str(metadata[metadata_key])
        lines.append(f"{yaml_key}: {yaml_string(value)}")

    tags = metadata["tags"]
    assert isinstance(tags, list)
    lines.append("Tags:")
    lines.extend(f"  - {yaml_string(str(tag))}" for tag in tags)
    repository = str(metadata["repository"])
    lines.extend(
        (
            f"ReleaseNotesUrl: {yaml_string(f'https://github.com/{repository}/releases/tag/v{version}')}",
            'ManifestType: "defaultLocale"',
            f"ManifestVersion: {yaml_string(str(metadata['manifestVersion']))}",
            "",
        )
    )
    return "\n".join(lines)


def render_installer_manifest(
    metadata: dict[str, object],
    installers: list[dict[str, str]],
    version: str,
    release_date: str,
) -> str:
    """Render the two-architecture WinGet installer manifest."""
    lines = [
        schema_header(metadata, "installer"),
        "",
        f"PackageIdentifier: {yaml_string(str(metadata['packageIdentifier']))}",
        f"PackageVersion: {yaml_string(version)}",
        f"InstallerLocale: {yaml_string(str(metadata['installerLocale']))}",
        f"InstallerType: {yaml_string(str(metadata['installerType']))}",
        f"ReleaseDate: {yaml_string(release_date)}",
        "Installers:",
    ]
    for installer in installers:
        lines.extend(
            (
                f"  - Architecture: {yaml_string(installer['architecture'])}",
                f"    InstallerUrl: {yaml_string(installer['url'])}",
                f"    InstallerSha256: {yaml_string(installer['sha256'])}",
                f"    ProductCode: {yaml_string(installer['productCode'])}",
            )
        )
    lines.extend(
        (
            'ManifestType: "installer"',
            f"ManifestVersion: {yaml_string(str(metadata['manifestVersion']))}",
            "",
        )
    )
    return "\n".join(lines)


def prepare_manifests(
    metadata_path: Path,
    installers_path: Path,
    output_dir: Path,
    version: str,
    release_date: str,
) -> list[Path]:
    """Validate inputs and write a complete multi-file WinGet manifest."""
    if not VERSION_RE.fullmatch(version):
        raise ManifestError("version must use stable MAJOR.MINOR.PATCH format")
    if not DATE_RE.fullmatch(release_date):
        raise ManifestError("release date must use YYYY-MM-DD format")
    try:
        date.fromisoformat(release_date)
    except ValueError as exc:
        raise ManifestError("release date must use YYYY-MM-DD format") from exc

    metadata = validate_metadata(read_json_object(metadata_path, "package metadata"))
    try:
        installers_value = json.loads(installers_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read installer metadata: {exc}") from exc
    installers = validate_installers(installers_value, metadata, version)

    package_identifier = str(metadata["packageIdentifier"])
    package_locale = str(metadata["packageLocale"])
    outputs = {
        output_dir / f"{package_identifier}.yaml": render_version_manifest(
            metadata, version
        ),
        output_dir
        / f"{package_identifier}.locale.{package_locale}.yaml": render_locale_manifest(
            metadata, version
        ),
        output_dir
        / f"{package_identifier}.installer.yaml": render_installer_manifest(
            metadata, installers, version, release_date
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    return list(outputs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--installers", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-date", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outputs = prepare_manifests(
            args.metadata,
            args.installers,
            args.output_dir,
            args.version,
            args.release_date,
        )
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for output in outputs:
        print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
