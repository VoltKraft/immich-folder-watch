#!/usr/bin/env python3
"""Download verified framework build inputs and invoke the offline source builder.

The checked-in input lock is the only download authority. Outputs are local
packages, never upstream package replacements in the global NuGet cache. The
CLI removes only stale cache entries for the two current private package
identities before restore; Flatpak invokes the same builder offline.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


LOCK_PATH = Path("packaging/avalonia-reduced/inputs.json")
PACKAGE_IDS = {"avalonia", "avalonia.themes.fluent", "avalonia.remote.protocol"}
CUSTOM_IDS = {"avalonia", "avalonia.themes.fluent"}
MAX_INPUT_BYTES = 256 * 1024 * 1024


class PreparationError(ValueError):
    """An input is untrusted, incomplete, or the source build failed."""


def read_lock(source_root: Path) -> dict:
    """Validate the narrow immutable upstream archive and official package set."""
    lock = json.loads((source_root / LOCK_PATH).read_text(encoding="utf-8"))
    if lock.get("schemaVersion") != 1 or lock.get("upstreamVersion") != "12.1.6" or lock.get("packageVersion") != "12.1.6.1" or lock.get("sdkVersion") != "10.0.401":
        raise PreparationError("Unreviewed reduced Avalonia package version")
    source = lock.get("source", {})
    if source.get("filename") != "avalonia-source.tar.gz" or not re.fullmatch(
        r"https://codeload\.github\.com/AvaloniaUI/Avalonia/tar\.gz/[0-9a-f]{40}", source.get("url", "")
    ):
        raise PreparationError("Source must be the immutable upstream Avalonia archive")
    if source["url"].rsplit("/", 1)[-1] != lock.get("upstreamCommit"):
        raise PreparationError("Source URL must identify the locked upstream commit")
    packages = lock.get("packages", [])
    if not isinstance(packages, list) or len(packages) != len(PACKAGE_IDS):
        raise PreparationError("Expected exactly the reviewed upstream NuGet input set")
    seen = set()
    for item in [source, *packages]:
        if not re.fullmatch(r"[0-9a-f]{128}", item.get("sha512", "")):
            raise PreparationError("Each input needs a SHA-512 archive checksum")
    for package in packages:
        identity = package.get("id", "").lower()
        version = package.get("version")
        if identity not in PACKAGE_IDS or identity in seen or version != lock["upstreamVersion"]:
            raise PreparationError("Unexpected or duplicate upstream NuGet input")
        expected = f"https://api.nuget.org/v3-flatcontainer/{identity}/{version}/{identity}.{version}.nupkg"
        if package.get("url") != expected or package.get("filename") != f"{identity}.{version}.nupkg":
            raise PreparationError("Package input must use its official NuGet archive URL")
        seen.add(identity)
    return lock


def download_verified(url: str, digest: str, destination: Path) -> None:
    """Atomically cache a bounded download; existing input must also match its lock."""
    if destination.is_symlink():
        raise PreparationError(f"Input path is a symbolic link: {destination.name}")
    if destination.exists():
        with destination.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha512").hexdigest()
        if actual != digest:
            raise PreparationError(f"Cached input checksum mismatch: {destination.name}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ImmichFolderWatch-source-builder"})
        with urllib.request.urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as target:
            temporary = Path(target.name)
            checksum = hashlib.sha512()
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_INPUT_BYTES:
                    raise PreparationError("Framework input exceeds the download size limit")
                checksum.update(chunk)
                target.write(chunk)
        if checksum.hexdigest() != digest:
            raise PreparationError(f"Downloaded input checksum mismatch: {destination.name}")
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def official_sources(lock: dict) -> list[dict[str, str]]:
    """Return hash-pinned original packages required only as compiler inputs."""
    return [{
        "type": "file", "url": item["url"], "sha512": item["sha512"],
        "dest": "nuget-sources",
        "dest-filename": f"{item['id'].lower()}.{item['version']}.nupkg",
    } for item in lock["packages"]]


def global_package_cache(source_root: Path, dotnet: str) -> Path:
    """Resolve NuGet's effective package cache without clearing any cache scope."""
    configured = os.environ.get("NUGET_PACKAGES")
    if configured:
        path = Path(configured).expanduser()
        return (path if path.is_absolute() else source_root / path).resolve()
    result = subprocess.run(
        [dotnet, "nuget", "locals", "global-packages", "--list", "--force-english-output"],
        cwd=source_root, capture_output=True, text=True, timeout=30,
    )
    prefix = "global-packages: "
    paths = [line[len(prefix):].strip() for line in result.stdout.splitlines() if line.startswith(prefix)]
    if result.returncode or len(paths) != 1 or not Path(paths[0]).is_absolute():
        raise PreparationError("Could not determine the effective NuGet global-packages directory")
    return Path(paths[0]).resolve()


def invalidate_stale_private_packages(cache: Path, feed: Path, version: str) -> list[Path]:
    """Remove only mismatching current private package directories before restore.

    Matching archives and every other package/version remain untouched. This is
    necessary because NuGet reuses cached identities without consulting a newly
    rebuilt local feed. Call only after the complete source build succeeds and
    before starting a restore; concurrent restores in this cache are unsupported.
    """
    if version != "12.1.6.1":
        raise PreparationError("Refusing cache invalidation for an unreviewed package version")
    cache = cache.resolve()
    stale = []
    for identity in sorted(CUSTOM_IDS):
        filename = f"{identity}.{version}.nupkg"
        built = feed / filename
        if built.is_symlink() or not built.is_file():
            raise PreparationError(f"Reduced package was not produced: {filename}")
        directory = cache / identity / version
        if directory.is_symlink() or directory.resolve() != directory:
            raise PreparationError(f"Refusing linked private package cache path: {directory}")
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise PreparationError(f"Private package cache entry is not a directory: {directory}")
        cached = directory / filename
        if cached.is_symlink():
            raise PreparationError(f"Refusing linked private package archive: {cached}")
        matches = False
        if cached.is_file():
            with cached.open("rb") as old, built.open("rb") as new:
                matches = hashlib.file_digest(old, "sha512").digest() == hashlib.file_digest(new, "sha512").digest()
        if not matches:
            stale.append(directory)
    # Validate both candidates before making any bounded deletions.
    for directory in stale:
        shutil.rmtree(directory)
        print(f"Removed stale private NuGet cache entry: {directory}")
    return stale


def prepare(source_root: Path, work_dir: Path, output: Path, dotnet: str = "dotnet") -> dict:
    """Verify source inputs, build the two local packages, and return their lock."""
    source_root, work_dir, output = source_root.resolve(), work_dir.resolve(), output.resolve()
    lock = read_lock(source_root)
    dotnet_path = shutil.which(dotnet)
    if dotnet_path is None:
        raise PreparationError("Pinned .NET SDK executable is not available")
    inputs = work_dir / "inputs"
    archive = inputs / lock["source"]["filename"]
    download_verified(lock["source"]["url"], lock["source"]["sha512"], archive)
    for item in official_sources(lock):
        download_verified(item["url"], item["sha512"], inputs / item["dest-filename"])
    with tempfile.TemporaryDirectory(prefix="build-", dir=work_dir) as temporary:
        result = subprocess.run([
            sys.executable, str(source_root / "tools/build_reduced_avalonia.py"),
            "--source-archive", str(archive), "--upstream-packages", str(inputs),
            "--output", str(output), "--work-dir", temporary, "--dotnet", str(Path(dotnet_path).resolve()),
        ], cwd=source_root)
    if result.returncode:
        raise PreparationError(f"Reduced Avalonia source build failed (exit code {result.returncode})")
    for identity in CUSTOM_IDS:
        package = output / f"{identity}.{lock['packageVersion']}.nupkg"
        if package.is_symlink() or not package.is_file():
            raise PreparationError(f"Reduced package was not produced: {package.name}")
    return lock


def recipe_fingerprint(source_root: Path) -> str:
    """Invalidate readiness when any executable recipe or locked input changes."""
    files = [LOCK_PATH, Path("packaging/avalonia-reduced/removals.json"),
             *(Path(f"tools/{name}_reduced_avalonia.py")
               for name in ("prepare", "build", "verify", "audit"))]
    checksum = hashlib.sha256()
    for relative in files:
        checksum.update(str(relative).replace("\\", "/").encode())
        checksum.update(b"\0")
        checksum.update((source_root / relative).read_text(encoding="utf-8").encode())
        checksum.update(b"\0")
    return checksum.hexdigest()


def ready(source_root: Path, output: Path, lock: dict) -> bool:
    """Accept only a complete feed built by the current source recipe."""
    try:
        stamp = output / "ready.json"
        if stamp.is_symlink():
            return False
        record = json.loads(stamp.read_text(encoding="utf-8"))
        if record.get("recipeSha256") != recipe_fingerprint(source_root):
            return False
        expected_names = {f"{name}.{lock['packageVersion']}.nupkg" for name in CUSTOM_IDS}
        if set(record.get("packages", {})) != expected_names:
            return False
        for filename in expected_names:
            path = output / filename
            if path.is_symlink():
                return False
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha512").hexdigest() != record["packages"][filename]:
                    return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def mark_ready(source_root: Path, output: Path, lock: dict) -> None:
    """Publish readiness only after both packages passed source/binary checks."""
    packages = {}
    for identity in sorted(CUSTOM_IDS):
        path = output / f"{identity}.{lock['packageVersion']}.nupkg"
        with path.open("rb") as stream:
            packages[path.name] = hashlib.file_digest(stream, "sha512").hexdigest()
    record = {"recipeSha256": recipe_fingerprint(source_root), "packages": packages}
    temporary = output / "ready.json.tmp"
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "ready.json")


@contextmanager
def preparation_lock(work_dir: Path):
    """Serialize restores sharing this work directory; OS releases locks on exit."""
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / ".prepare.lock"
    if path.is_symlink():
        raise PreparationError("Preparation lock must not be a symbolic link")
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + 1200
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PreparationError("Timed out waiting for another framework preparation")
                time.sleep(0.2)
            except OSError as exc:
                if os.name != "nt" or exc.errno not in (13, 36):
                    raise
                if time.monotonic() >= deadline:
                    raise PreparationError("Timed out waiting for another framework preparation") from exc
                time.sleep(0.2)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--if-needed", action="store_true", help="Reuse only a complete feed matching the current recipe and archive hashes")
    args = parser.parse_args()
    root = args.source_root.resolve()
    try:
        output = args.output or root / "artifacts/reduced-avalonia/feed"
        work_dir = args.work_dir or root / "artifacts/reduced-avalonia"
        with preparation_lock(work_dir):
            lock = read_lock(root)
            if not args.if_needed or not ready(root, output, lock):
                (output / "ready.json").unlink(missing_ok=True)
                lock = prepare(root, work_dir, output, args.dotnet)
                mark_ready(root, output, lock)
            invalidate_stale_private_packages(global_package_cache(root, args.dotnet), output, lock["packageVersion"])
    except (PreparationError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Reduced Avalonia preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
