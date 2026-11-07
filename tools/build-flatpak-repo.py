#!/usr/bin/env python3
"""Build an atomic, signed Pages site from a complete release bundle pair.

Requires flatpak, ostree and gpg, and an unlocked signing key in GNUPGHOME.
The output directory must not exist. Existing publication is never modified.
Only current release objects are retained; clients can still update normally.
"""
from __future__ import annotations

import argparse
import base64
import html
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

APP_ID = "io.github.voltkraft.immich-folder-watch"
ARCHITECTURES = {"linux-x64": "x86_64", "linux-arm64": "aarch64"}
# Leave headroom below GitHub Pages' 1 GB site limit, including tar overhead.
MAX_SITE_BYTES = 950_000_000
BUNDLE_PATTERN = re.compile(r"immich-folder-watch-(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-(linux-x64|linux-arm64)\.flatpak")


class RepositoryError(ValueError):
    """Input or generated repository does not meet the publication contract."""


def run(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(args, check=True, capture_output=True, text=not binary)
    return result.stdout


def validate_url(value: str) -> str:
    """Accept an HTTPS site root without credentials, query or fragment."""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in value)):
        raise RepositoryError("Base URL must be an HTTPS site root without credentials, query or fragment.")
    return value.rstrip("/")


def find_bundles(directory: Path) -> tuple[str, dict[str, Path]]:
    """Require exactly one matching stable-version bundle per architecture."""
    bundles: dict[str, Path] = {}
    versions: set[str] = set()
    for path in sorted(directory.glob("*.flatpak")):
        match = BUNDLE_PATTERN.fullmatch(path.name)
        if not match or not path.is_file() or path.is_symlink():
            raise RepositoryError(f"Unexpected bundle: {path.name}")
        version = ".".join(match.groups()[:3])
        architecture = ARCHITECTURES[match.group(4)]
        if architecture in bundles:
            raise RepositoryError(f"Duplicate architecture: {architecture}")
        bundles[architecture] = path.resolve()
        versions.add(version)
    if set(bundles) != set(ARCHITECTURES.values()) or len(versions) != 1:
        raise RepositoryError("Expected x86_64 and aarch64 bundles from exactly one stable release.")
    return versions.pop(), bundles


def write_site_metadata(site: Path, base_url: str, public_key: bytes, branch: str, version: str) -> None:
    """Write Flatpak descriptors and an installation page using the same trust key."""
    key = base64.b64encode(public_key).decode("ascii")
    repo_url = f"{base_url}/repo"
    (site / "public-key.gpg").write_bytes(public_key)
    (site / "immich-folder-watch.flatpakrepo").write_text(
        "[Flatpak Repo]\nTitle=Immich Folder Watch\n"
        f"Url={repo_url}\nHomepage={base_url}/\nDefaultBranch={branch}\n"
        f"Description=Official Immich Folder Watch releases for Linux\nGPGKey={key}\n",
        encoding="utf-8",
    )
    (site / f"{APP_ID}.flatpakref").write_text(
        "[Flatpak Ref]\nTitle=Immich Folder Watch\n"
        f"Name={APP_ID}\nBranch={branch}\nIsRuntime=false\nUrl={repo_url}\n"
        "SuggestRemoteName=immich-folder-watch\n"
        "RuntimeRepo=https://flathub.org/repo/flathub.flatpakrepo\n"
        f"GPGKey={key}\n", encoding="utf-8",
    )
    install_command = f"flatpak install --user {base_url}/{APP_ID}.flatpakref"
    (site / "index.html").write_text(
        '<!doctype html>\n<html lang="en"><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Immich Folder Watch — Flatpak repository</title>\n'
        '<main><h1>Immich Folder Watch</h1>\n'
        f'<p>Version {html.escape(version)} for Linux x86_64 and aarch64.</p>\n'
        f'<p><a href="{APP_ID}.flatpakref">Install with Flatpak</a> · '
        '<a href="immich-folder-watch.flatpakrepo">Add repository</a> · '
        '<a href="https://github.com/VoltKraft/immich-folder-watch/releases">GitHub Releases</a></p>\n'
        f'<pre>{html.escape(install_command)}</pre>\n'
        '<p>Update with <code>flatpak update --user</code>. The Freedesktop runtime '
        'is provided by Flathub.</p>\n'
        '<p><a href="public-key.gpg">Repository signing public key</a></p></main></html>\n',
        encoding="utf-8",
    )
    (site / ".nojekyll").touch()


def build_repository(bundles_dir: Path, output_dir: Path, base_url: str,
                     gpg_key_id: str, branch: str = "master") -> int:
    """Import and sign both refs, then publish a validated site atomically locally."""
    base_url = validate_url(base_url)
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", gpg_key_id):
        raise RepositoryError("GPG key ID must be a full fingerprint.")
    if branch not in {"master", "stable"}:
        raise RepositoryError("Only master or stable release branches are supported.")
    if output_dir.exists():
        raise RepositoryError("Output directory already exists; choose a new staging directory.")
    version, bundles = find_bundles(bundles_dir)
    public_key = run("gpg", "--batch", "--export", gpg_key_id, binary=True)
    if not public_key:
        raise RepositoryError("The configured signing public key was not found.")
    output_dir = output_dir.absolute()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".flatpak-site-", dir=output_dir.parent) as temporary:
        site = Path(temporary) / "site"
        site.mkdir()
        repo = site / "repo"
        run("ostree", "init", f"--repo={repo}", "--mode=archive")
        expected_refs: set[str] = set()
        for architecture, bundle in sorted(bundles.items()):
            run("flatpak", "build-import-bundle", "--no-update-summary",
                f"--gpg-sign={gpg_key_id}", str(repo), str(bundle))
            expected_refs.add(f"app/{APP_ID}/{architecture}/{branch}")
            refs = set(str(run("ostree", "refs", f"--repo={repo}")).splitlines())
            if refs != expected_refs:
                raise RepositoryError(f"Unexpected imported refs: {sorted(refs)}; expected {sorted(expected_refs)}")
        write_site_metadata(site, base_url, public_key, branch, version)
        run("flatpak", "build-update-repo", f"--gpg-sign={gpg_key_id}",
            f"--gpg-import={site / 'public-key.gpg'}", "--title=Immich Folder Watch",
            f"--homepage={base_url}/", f"--default-branch={branch}", str(repo))
        if not (repo / "summary.sig").is_file():
            raise RepositoryError("Signed repository summary is missing.")
        size = sum(path.stat().st_size for path in site.rglob("*") if path.is_file())
        if size > MAX_SITE_BYTES:
            raise RepositoryError(f"Site is {size} bytes, above the {MAX_SITE_BYTES}-byte Pages safety limit.")
        if any(path.is_symlink() for path in site.rglob("*")):
            raise RepositoryError("Pages site contains a symbolic link.")
        site.rename(output_dir)
    return size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--gpg-key-id", required=True)
    parser.add_argument("--branch", choices=("master", "stable"), default="master")
    args = parser.parse_args()
    try:
        size = build_repository(args.bundles_dir, args.output_dir, args.base_url,
                                args.gpg_key_id, args.branch)
    except (RepositoryError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Repository build failed: {error}\n")
    print(f"Prepared signed Flatpak site: {args.output_dir} ({size} bytes)")


if __name__ == "__main__":
    main()
