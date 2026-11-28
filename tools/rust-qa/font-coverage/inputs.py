"""Verify the private originals and their complete notices before embedding any font."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust/font-coverage"
PINS = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def acquire_original(path, url, digest, limit):
    for attempt in range(3):
        try:
            with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
                fresh = Path(temporary) / path.name
                with urllib.request.urlopen(url, timeout=90) as stream, fresh.open("xb") as output:
                    while chunk := stream.read(256 * 1024):
                        if output.tell() + len(chunk) > limit:
                            raise ValueError(f"Oversize input {path.name}")
                        output.write(chunk)
                if sha(fresh) != digest:
                    raise ValueError(f"Unexpected downloaded input {path.name}")
                fresh.replace(path)
            return
        except (urllib.error.URLError, OSError) as error:
            if attempt == 2:
                raise
            if isinstance(error, urllib.error.HTTPError) and error.code < 500 and error.code != 429:
                raise
            time.sleep(2 ** attempt)


def font_names(font):
    data = font.read_bytes()
    tables, = struct.unpack_from(">H", data, 4)
    for index in range(tables):
        tag, _, start, size = struct.unpack_from(">4sIII", data, 12 + 16 * index)
        if tag == b"name":
            break
    else:
        raise ValueError(f"Missing original font notice table in {font.name}")
    block = memoryview(data)[start:start + size]
    _, count, strings = struct.unpack_from(">3H", block)
    values = {}
    for index in range(count):
        platform, _, _, name, length, pos = struct.unpack_from(">6H", block, 6 + index * 12)
        if name not in {0, 1, 5, 7, 13, 14}:
            continue
        codec = "utf-16-be" if platform in (0, 3) else "mac_roman"
        value = bytes(block[strings + pos:strings + pos + length]).decode(codec)
        values.setdefault(name, set()).add(value)
    return {str(k): sorted(v) for k, v in sorted(values.items())}


def verify(download=False):
    directory = ART / "inputs"
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for asset in PINS["assets"]:
        path = directory / asset["name"]
        if not path.exists() and download:
            url = f"https://raw.githubusercontent.com/{asset['repository']}/{asset['revision']}/{asset['path']}"
            acquire_original(path, url, asset["sha256"], 20 * 1024 * 1024)
        if sha(path) != asset["sha256"]:
            raise ValueError(f"Changed pinned input {path.name}")
        row = {"bytes": path.stat().st_size, "sha256": asset["sha256"]}
        if "license" in asset:
            if asset["license"] not in result:
                raise ValueError("Validate the complete matching notice first")
            row.update(license=asset["license"], embeddedNames=font_names(path))
        if "gitBlob" in asset:
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != asset["gitBlob"]:
                raise ValueError("Original Arabic font does not match the independently pinned Git object")
            row["gitBlob"] = blob
        result[path.name] = row
    return result
