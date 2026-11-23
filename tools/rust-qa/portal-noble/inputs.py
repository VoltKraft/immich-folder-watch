"""Acquire the fixed Ubuntu source package and authenticate the native distro control."""
import concurrent.futures
import hashlib
from http.client import RemoteDisconnected
import os
from pathlib import Path
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust"
BASE = ART / "portal-noble"
VERSION = "1.18.4-1ubuntu2.24.04.3"
SOURCE = "xdg-desktop-portal"
POOL = "pool/main/x/xdg-desktop-portal/"
UBUNTU = "https://archive.ubuntu.com/ubuntu/"
PORTS = "https://ports.ubuntu.com/ubuntu-ports/"
PATCH = HERE.parent / "portal-reference/flock-upstream.patch"
PATCH_SHA = "5d7a386866288358b46621e85cbb68e9f008a19f669acc18859cd82f82f7fc5b"
ORIGINALS = {
    SOURCE + "_1.18.4.orig.tar.xz": "b858aa1e74e80c862790dbb912906e6eab8b1e4db9339cd759473af62b461e65",
    SOURCE + "_1.18.4.orig-libglnx.tar.gz": "93c3faf43e1952b95a8e3fbd3228de6f8b690749e16e6bfb80410b39196cffe5",
    SOURCE + "_" + VERSION + ".debian.tar.xz": "9a646551b1be31a3a839cc11ecb1ace8eaa849a28aae377874b5a1dd97e48175",
    SOURCE + "_" + VERSION + ".dsc": "4e30107a2658217129bcb0db8d88bab9a8f07b4c5339c7b7852b709f13eb7049",
}
KEYRING = "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31"
SIGNER = "F6ECB3762474EDA9D21B7022871920D1991BC93C"
CONNECTION_ATTEMPTS = 3


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def fetch(url, path, digest, download, max_bytes=16_000_000):
    if path.is_file() and not path.is_symlink() and sha(path) == digest:
        return path
    if path.exists() or path.is_symlink() or not download:
        raise ValueError(f"Missing or changed checked input {path.name}")
    for attempt in range(1, CONNECTION_ATTEMPTS + 1):
        try:
            response = urllib.request.urlopen(url, timeout=60)
            break
        except RemoteDisconnected as error:
            if attempt == CONNECTION_ATTEMPTS:
                raise RemoteDisconnected(
                    f"Ubuntu closed the connection before sending headers for {path.name} on all {attempt} attempts"
                ) from error
            time.sleep(attempt)
    with response as data, tempfile.NamedTemporaryFile(dir=path.parent) as temp:
        if urlsplit(data.geturl()).hostname != urlsplit(url).hostname:
            raise ValueError("Unexpected Ubuntu archive redirect")
        while chunk := data.read(262144):
            if temp.tell() + len(chunk) > max_bytes:
                raise ValueError("Oversize archive file")
            temp.write(chunk)
        temp.flush()
        if sha(Path(temp.name)) != digest:
            raise ValueError(f"Unexpected Ubuntu input {path.name}")
        os.link(temp.name, path)
    return path


def source_inputs(download):
    cache = BASE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda entry: fetch(UBUNTU + POOL + entry[0], cache / entry[0], entry[1], download),
                      ORIGINALS.items()))
    if sha(PATCH) != PATCH_SHA:
        raise ValueError("Changed upstream flock implementation")
    return cache
