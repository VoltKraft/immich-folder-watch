"""Prepare the unchanged Cargo sources and original notices for the private CPU painter."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import NamedTuple
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = HERE / "upstream.json"
spec = importlib.util.spec_from_file_location("cpu_paint_crate_reader", HERE.parent / "yaml/prepare.py")
crate_reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crate_reader)


class Prepared(NamedTuple):
    sources: dict[str, Path]
    notices: Path
    receipt: Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected, size=None):
    if path.is_symlink() or not path.is_file() or (size is not None and path.stat().st_size != size):
        raise ValueError(f"Missing or unexpected input: {path}")
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return data


class OriginOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Original crate downloads must not redirect")


ARCHIVES = urllib.request.build_opener(OriginOnly)


def fetch_archive(path, name, row):
    size = row["bytes"]
    url = f"https://static.crates.io/crates/{name}/{path.name}"
    with ARCHIVES.open(url, timeout=45) as response:
        if response.geturl() != url:
            raise ValueError(f"Unexpected archive redirect for {name}")
        data = response.read(size + 1)
    if len(data) != size or digest(data) != row["sha256"]:
        raise ValueError(f"Unexpected public archive for {name}")
    # Close the temporary file before publishing on Windows. Every publisher
    # writes identical verified bytes, and readers never see a partial seed.
    tmp = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            tmp = Path(handle.name)
            handle.write(data)
        tmp.replace(path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def source_inputs(cache, pins, fetch):
    archives = cache / "archives"
    archives.mkdir(exist_ok=True, parents=True)
    files, roots = {}, {}
    for name, row in pins["packages"].items():
        stem = name + "-" + row["version"]
        path = archives / (stem + ".crate")
        if not path.exists() and not path.is_symlink():
            if not fetch:
                raise FileNotFoundError(f"Missing offline input {path}. Seed it with --fetch.")
            fetch_archive(path, name, row)
        checked(path, row["sha256"], row["bytes"])
        members, changes = crate_reader.source_files(path, stem, row["sha256"])
        if (changes or len(members) != row["files"] or sum(map(len, members.values())) != row["unpackedBytes"]
                or json.loads(members[".cargo_vcs_info.json"])["git"]["sha1"] != row["vcsCommit"]):
            raise ValueError(f"Unexpected archive contents for {name}")
        roots[name] = Path("sources") / stem
        files.update({roots[name] / member: data for member, data in members.items()})
    return roots, files


def verified_tree(destination, expected):
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError(f"Unexpected prepared directory: {destination}")
    found = set()
    directories = {parent for path in expected for parent in path.parents}
    for path in destination.rglob("*"):
        relative = path.relative_to(destination)
        if path.is_symlink() or (path.is_dir() and relative not in directories):
            raise ValueError(f"Unexpected prepared path: {path}")
        if not path.is_dir():
            if relative not in expected:
                raise ValueError(f"Unexpected prepared file: {path}")
            checked(path, digest(expected[relative]), len(expected[relative]))
            found.add(relative)
    if found != set(expected):
        raise ValueError(f"Prepared tree is incomplete: {destination}")


def prepare(cache: Path, *, fetch: bool = False) -> Prepared:
    """Return verified crate roots, original notice files and a deterministic receipt."""
    cache = Path(cache).resolve()
    manifest = PINS.read_bytes()
    pins = json.loads(manifest)
    roots, files = source_inputs(cache, pins, fetch)
    for name, row in pins["notices"].items():
        if "archiveMember" in row:
            package, member = row["archiveMember"]
            data = files[roots[package] / member]
            if digest(data) != row["sha256"]:
                raise ValueError(f"Unexpected archived notice: {name}")
        else:
            data = checked(ROOT / row["repositoryFile"], row["sha256"])
        files[Path("notices") / name] = data
    receipt = {"manifestSha256": digest(manifest), "archiveSha256": {
        name: row["sha256"] for name, row in pins["packages"].items()},
        "files": {path.as_posix(): digest(data) for path, data in files.items()}}
    files[Path("upstream-receipt.json")] = crate_reader.canonical(receipt)
    destination = cache / ("prepared-" + digest(manifest))
    if not destination.exists() and not destination.is_symlink():
        with TemporaryDirectory(dir=cache) as tmp:
            stage = Path(tmp) / "prepared"
            for relative, data in files.items():
                path = stage / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            try:
                os.rename(stage, destination)
            except OSError:
                if not destination.exists():
                    raise
                # A concurrent preparation may have published its complete tree.
    verified_tree(destination, files)
    return Prepared({name: destination / root for name, root in roots.items()},
                    destination / "notices", destination / "upstream-receipt.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--fetch", action="store_true", help="Download missing original archives")
    args = parser.parse_args()
    print(prepare(args.cache, fetch=args.fetch).receipt)
