"""Prepare the original archives and the native compiler receipt used by the notice generator."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "combined-profile"))
import notices
import sbom
import sources
from realtime import hyper_util_source


def ensure_archive(name, version, checksum, locations, cache, fetch):
    filename = f"{name}-{version}.crate"
    sbom.require(re.fullmatch(r"[a-zA-Z0-9_.+-]+", filename), "Invalid Cargo archive name")
    existing = next((d / filename for d in locations if (d / filename).is_file()), None)
    if existing is not None:
        sbom.require(not existing.is_symlink() and sources.sha256(existing) == checksum,
                     f"Changed original archive: {filename}")
        return False
    if not fetch:
        raise FileNotFoundError(f"Missing original archive: {filename}")
    with tempfile.TemporaryDirectory(dir=cache) as directory:
        staged = Path(directory) / filename
        sources.public_archive(name, staged, checksum)
        try:
            os.link(staged, cache / filename)
        except FileExistsError:
            winner = cache / filename
            sbom.require(winner.is_file() and not winner.is_symlink() and sources.sha256(winner) == checksum,
                         f"Conflicting archive: {filename}")
    return True


def prepare_cache(fetch: bool) -> None:
    # Both the native compiler and the offline notice reader consult these project-local caches.
    cache = sources.ROOT / "artifacts/rust/assessment-cache/registry/cache/ifw-native-notices"
    cache.mkdir(parents=True, exist_ok=True)
    homes = sources.local_caches()
    locations = sorted({d for home in homes for d in (home / "registry/cache").glob("*")
                        if d.is_dir()})
    catalog = sources.catalog()

    def acquire(item):
        (name, version), checksum = item
        return ensure_archive(name, version, checksum, locations, cache, fetch)

    with ThreadPoolExecutor(max_workers=4) as workers:
        acquired = sum(workers.map(acquire, sorted(catalog.items())))
    # The lock identifies the maintained CONNECT source by path. Retain its upstream
    # archive as well so a fresh compiler or notice process can reconstruct it offline.
    archive_name = hyper_util_source.ARCHIVE.name
    upstream_home = next((home for home in homes if any((home / "registry/cache").glob("*/" + archive_name))), homes[0])
    original = hyper_util_source.original(upstream_home, fetch)
    receipt = hyper_util_source.reconstruct(original, hyper_util_source.SOURCE)
    print(f"Verified {len(catalog)} registry archives, acquired {acquired} missing registry inputs")
    print(f"Reconstructed hyper-util compiler source {receipt['treeSha256']}")


def pack(target: str, revision: str, run: Path, destination: Path) -> str:
    sbom.require(re.fullmatch(r"[0-9a-f]{40}", revision), "Expected a full source revision")
    sbom.require(run.is_dir(), "Expected the completed native run directory")
    receipt, receipt_sha, required = sbom.read_run(run, target, None)
    sbom.verify(receipt, required, revision, target)
    # Pin the bytes again as they enter the ZIP, including the receipt itself.
    prefix = f"combined-profile/runs/{target}/"
    members = {}
    for name, digest in {**receipt["outputs"], "result.json": receipt_sha}.items():
        path = run / name
        sbom.require(path.is_file() and not path.is_symlink(), f"Expected original native file: {name}")
        data = path.read_bytes()
        sbom.require(sbom.sha(data) == digest, f"Native file changed while packaging: {name}")
        members[prefix + name] = data
    return notices.write_archive(destination, members)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cache = commands.add_parser("cache", help="Verify the project-local acquisition caches")
    cache.add_argument("--fetch-missing", action="store_true", help="Acquire a missing checksum-pinned crate")
    archive = commands.add_parser("pack", help="Package the authenticated native receipt and all indexed outputs")
    archive.add_argument("target")
    archive.add_argument("--revision", required=True)
    archive.add_argument("--input", required=True, type=Path)
    archive.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "cache":
        prepare_cache(args.fetch_missing)
    else:
        print(pack(args.target, args.revision, args.input, args.output), args.output)
