"""Reconstruct and verify the maintained CONNECT error metadata from hyper-util 0.1.21."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
DIRECTORY = HERE.parents[2] / "artifacts/rust/realtime-sources"
SOURCE = DIRECTORY / "hyper-util"
BASENAME = "hyper-util-0.1.21"
ARCHIVE = DIRECTORY / (BASENAME + ".crate")
ARCHIVE_SHA = "ddc03d96684f9226b8a787cdb71488417b53ab5ea8fdb1dac946cb9431cc8bff"
UPSTREAM = "23a868965964c1d6bb1b94f30ba4c420a4bebe7c"
PATCH = HERE / "hyper-util-connect.patch"
PATCH_SHA = "761b075d5fbf1d5c98c478bcc6f443898a1171973d4dcc557380ce45d84f9cd0"
NOTICES = {"LICENSE": "9e0a97848ea543aef745c98e84fde696a9a3e0735538f6daefdd3cb1942effc1"}
CHANGES = {
    "src/client/legacy/connect/proxy/mod.rs": {
        "originalSha256": "2dc7d98c83f3303d9f275fe3517a251ed7b0bc78ff101ab8f641158ee6c98abf",
        "patchedSha256": "b25554aa3e15a684517b4e97ce3ce464f8d1ef8460eea2b97d90620d434166cb",
    },
    "src/client/legacy/connect/proxy/tunnel.rs": {
        "originalSha256": "e584da5d3d91c65740a719a3a60d36d520e93e3a99289f0d80e04e2dff0383bb",
        "patchedSha256": "8c28746d510986a80bc76ac006308be6af1cf0cb48c4137c769ab04d15e7ea5d",
    },
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def original(cargo_home, fetch=False):
    if not ARCHIVE.exists():
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DIRECTORY) as work:
            staged = Path(work) / ARCHIVE.name
            cached = next((cargo_home / "registry/cache").glob("*/" + ARCHIVE.name), None)
            if cached:
                shutil.copyfile(cached, staged)
            elif fetch:
                url = f"https://static.crates.io/crates/hyper-util/{ARCHIVE.name}"
                with urllib.request.urlopen(url, timeout=60) as response:
                    staged.write_bytes(response.read(126821))
            else:
                raise FileNotFoundError(f"Missing pinned offline input {ARCHIVE.name}")
            if sha(staged) != ARCHIVE_SHA:
                raise ValueError("Original hyper-util archive differs")
            os.replace(staged, ARCHIVE)
    if sha(ARCHIVE) != ARCHIVE_SHA:
        raise ValueError("Retained hyper-util archive differs")
    return ARCHIVE


def archive_files(archive):
    if sha(archive) != ARCHIVE_SHA or sha(PATCH) != PATCH_SHA:
        raise ValueError("Wrong hyper-util original or transport patch")
    original_files = {}
    with tarfile.open(archive, "r:gz") as contents:
        for member in contents:
            prefix, *parts = PurePosixPath(member.name).parts
            if prefix != BASENAME or any(p in ("..", ".") or ":" in p or "\\" in p for p in parts):
                raise ValueError("Unexpected hyper-util archive path")
            if member.isdir():
                continue
            name = "/".join(parts)
            if not member.isfile() or not name or name in original_files:
                raise ValueError("Unexpected hyper-util archive entry")
            original_files[name] = contents.extractfile(member).read()
    if json.loads(original_files[".cargo_vcs_info.json"])["git"]["sha1"] != UPSTREAM:
        raise ValueError("Unexpected hyper-util upstream revision")
    return original_files


def verify(archive, destination):
    expected = {k: hashlib.sha256(v).hexdigest() for k, v in archive_files(archive).items()}
    for name, change in CHANGES.items():
        if expected[name] != change["originalSha256"]:
            raise ValueError(f"Unexpected hyper-util preimage: {name}")
        expected[name] = change["patchedSha256"]
    if any(expected[name] != digest for name, digest in NOTICES.items()):
        raise ValueError("Original hyper-util notice differs")
    actual = {}
    if destination.is_symlink():
        raise ValueError("Linked hyper-util source directory")
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise ValueError("Linked hyper-util compiler input")
        if path.is_file():
            actual[path.relative_to(destination).as_posix()] = sha(path)
    if actual != expected:
        raise ValueError("Reconstructed hyper-util tree differs from its reviewed inputs")
    tree = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(archiveSha256=ARCHIVE_SHA, upstreamCommit=UPSTREAM, patchSha256=PATCH_SHA,
                changes=CHANGES, treeSha256=tree, fileCount=len(actual), notices=NOTICES)


def reconstruct(archive, destination):
    if destination.exists():
        return verify(archive, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        stage = Path(work) / "source"
        for name, data in archive_files(archive).items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CEILING_DIRECTORIES=str(Path(work).resolve()), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--whitespace=error-all", str(PATCH)],
                       cwd=stage, env=env, check=True)
        receipt = verify(archive, stage)
        try:
            stage.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
            return verify(archive, destination)
        return receipt
