"""Verify and isolate the upstream sources used by the Windows import assessment."""

import hashlib
import io
import json
import re
import shutil
import tarfile
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from formats import AMD64, ARM64

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / "artifacts/rust/windows-imports"
REVISION = "db06b51c2ebb743efb544d40e3064efa49f28d38"
TARBALL = f"https://codeload.github.com/microsoft/windows-rs/tar.gz/{REVISION}"
SOURCE_DIGEST = "e5ad2f84779a3f1ca490d9658093fb677c24bd6208e26765096d719f83799087"
SOURCE_TAR = "cfb0c1357c9b3bc7cb0b746ffce50d23a25b78aeeeaccb1c4e6ad1fa280d979b"
LIBRARY = "windows.0.52.0.lib"
METADATA = Path("crates/libs/bindgen/default")
BASELINES = Path("crates/targets/baseline")


@dataclass(frozen=True)
class Target:
    triple: str
    vs_arch: str
    machine: int
    crate: str
    library_sha256: str


WINDOWS_ARM64 = Target("aarch64-pc-windows-msvc", "arm64", ARM64, "windows_aarch64_msvc",
                       "ca85dd7757f338ba00d0bc19229f176ee426a707425ee4fcf205ec491a95bd5a")
WINDOWS_X64 = Target("x86_64-pc-windows-msvc", "x64", AMD64, "windows_x86_64_msvc",
                     "24d8cbc445955b0d48041948a3c71ce2cddb948c089b25ec7106fadd9f3efde0")
PINNED = {
    "license-mit", "license-apache-2.0", "crates/libs/metadata/Cargo.toml",
    "crates/tools/msvc/Cargo.toml", "crates/tools/msvc/src/main.rs",
    "crates/tools/lib/Cargo.toml", "crates/tools/lib/src/lib.rs",
    *((METADATA / name).as_posix() for name in
      ("Windows.winmd", "Windows.Win32.winmd", "Windows.Wdk.winmd", "readme.md")),
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(hashes):
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())).encode("ascii")


def download(path, url):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as dst:
        temp = Path(dst.name)
    try:
        with urllib.request.urlopen(url, timeout=60) as src, temp.open("wb") as dst:
            total = 0
            while block := src.read(1024 * 1024):
                total += len(block)
                if total > 80 * 1024 * 1024:
                    raise ValueError("Upstream download exceeded its byte budget")
                dst.write(block)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def target_std(target, work, selected, acquire):
    name = f"rust-std-1.100.0-{target}"
    pin = json.loads((ROOT / "rust/toolchain-inputs.json").read_bytes())["targets"][target]["rust-std"]
    archive = selected or (BASE.parent / "windows-services/target-inputs" / (name + ".tar.xz"))
    if not archive.exists() and not selected:
        archive = BASE / "input" / (name + ".tar.xz")
        if not archive.exists() and acquire:
            download(archive, pin["url"])
    if sha(archive) != pin["sha256"]:
        raise ValueError("Cross-target standard library archive differs from the Rust toolchain pin")
    prefix = f"{name}/rust-std-{target}/lib/rustlib/{target}/lib/"
    dest = work / "sysroot/lib/rustlib" / target / "lib"
    dest.mkdir(parents=True)
    count = 0
    with tarfile.open(archive, "r|xz") as tar:
        for member in tar:
            if not member.name.startswith(prefix):
                continue
            filename = member.name[len(prefix):]
            if filename == "self-contained" and member.isdir():
                (dest / filename).mkdir()
                continue
            if not member.isfile() or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
                raise ValueError("Unexpected member in the pinned cross-target std library")
            with (dest / filename).open("xb") as dst:
                shutil.copyfileobj(tar.extractfile(member), dst)
            count += 1
    return work / "sysroot", {"archiveSha256": pin["sha256"], "files": count}


def upstream(root, acquire, filtered):
    package = filtered or (BASE / "input/windows-rs-db06b51.tar.gz")
    if filtered is not None and sha(filtered) != SOURCE_TAR:
        raise ValueError("Filtered source archive does not match the reviewed tar identity")
    if filtered is None and not package.exists() and acquire:
        download(package, TARBALL)
    digests = {}
    prefix = "" if filtered else f"windows-rs-{REVISION}/"
    with tarfile.open(package, "r|*") as archive:
        for item in archive:
            if not item.name.startswith(prefix):
                continue
            name = item.name[len(prefix):]
            if name not in PINNED and not re.fullmatch(
                r"crates/(?:targets/baseline/[\w.-]+\.c|libs/metadata/src/[\w]+\.rs)", name,
                re.ASCII,
            ):
                continue
            if not item.isfile() or name in digests or item.size > 32 * 1024 * 1024:
                raise ValueError(f"Unexpected upstream member {name!r}")
            data = archive.extractfile(item).read()
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            digests[name] = hashlib.sha256(data).hexdigest()
    record = manifest(digests)
    if len(digests) != 396 or hashlib.sha256(record).hexdigest() != SOURCE_DIGEST:
        raise ValueError("Upstream metadata, reader, generator, baselines or notices changed")
    (root / "source-sha256.txt").write_bytes(record)
    return {"revision": REVISION, "sourceFiles": len(digests), "sourceManifestSha256": SOURCE_DIGEST,
            "inputType": "filtered-tar" if filtered else "upstream-tarball", "inputSha256": sha(package)}


def source_bundle(root, output):
    """Write only the reviewed corresponding sources and original Microsoft notices."""
    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as tar:
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if not path.is_file():
                continue
            data = path.read_bytes()
            entry = tarfile.TarInfo(path.relative_to(root).as_posix())
            entry.size = len(data)
            entry.mode = 0o644
            tar.addfile(entry, io.BytesIO(data))


def crates(root, acquire, target):
    profile = json.loads((HERE.parent / "realtime/inputs.json").read_bytes())
    combined = tomllib.loads((HERE.parent / "combined-profile/Cargo.lock").read_text("utf-8"))
    records = {}
    for name, version in ((target.crate, "0.52.6"), ("windows-sys", "0.52.0"), ("windows-targets", "0.52.6")):
        row, = (p for p in combined["package"] if (p["name"], p["version"]) == (name, version))
        # The target packages carry the same original Microsoft license files.
        license_package = WINDOWS_ARM64.crate if name == WINDOWS_X64.crate else name
        review, = (p for p in profile["packages"] if (p["name"], p["version"]) == (license_package, version))
        if row["source"] != "registry+https://github.com/rust-lang/crates.io-index" or (
                name == license_package and row["checksum"] != review["archiveSha256"]):
            raise ValueError(f"Unexpected registry input for {name}")
        slug = f"{name}-{version}"
        filename = f"{slug}.crate"
        path = BASE / "input" / filename
        for cache in ("realtime-cargo", "assessment-cache", "realtime-assessment/cargo-home"):
            matches = sorted((BASE.parent / cache / "registry/cache").glob(f"*/{filename}"))
            if matches:
                path = matches[0]
                break
        if not path.exists() and acquire:
            download(path, f"https://static.crates.io/crates/{name}/{filename}")
        if sha(path) != row["checksum"]:
            raise ValueError(f"Original archive differs from the combined lock: {slug}")
        records[name] = {"version": version, "archiveSha256": row["checksum"],
                         "notices": review["notices"], "selectedLicense": review["selected"]}
        with tarfile.open(path) as tar:
            for item in tar:
                prefix = f"{slug}/"
                if not item.name.startswith(prefix):
                    raise ValueError(f"Unexpected archive root in {slug}")
                part = item.name[len(prefix):]
                if (name != target.crate and part not in review["notices"] and
                        part != "lib/" + LIBRARY and not part.startswith("src/")):
                    continue
                pieces = PurePosixPath(part)
                if (not item.isfile() or pieces.is_absolute() or ".." in pieces.parts or
                        not re.fullmatch(r"[a-zA-Z0-9_.\-/]+", part)):
                    raise ValueError(f"Unexpected member in {slug}: {part}")
                dest = root / name / part
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as out:
                    out.write(tar.extractfile(item).read())
        for notice, digest in review["notices"].items():
            if sha(root / name / notice) != digest:
                raise ValueError(f"Notice mismatch for {slug}: {notice}")
    package = root / target.crate
    vcs = json.loads((package / ".cargo_vcs_info.json").read_bytes())
    if vcs != {"git": {"sha1": REVISION}, "path_in_vcs": "crates/targets/" + target.crate.removeprefix("windows_")}:
        raise ValueError(f"Wrong Microsoft source revision for {target.crate}")
    manifest = tomllib.loads((package / "Cargo.toml").read_text("utf-8"))["package"]
    if manifest["license"] != "MIT OR Apache-2.0" or manifest["name"] != target.crate or manifest["version"] != "0.52.6":
        raise ValueError(f"Wrong target crate declaration for {target.triple}")
    original = package / "lib" / LIBRARY
    if sha(original) != target.library_sha256:
        raise ValueError(f"Original {target.vs_arch} import library mismatch")
    return records, original
