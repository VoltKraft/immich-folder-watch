"""Prepare private Cargo directory sources from the existing, versioned spike inputs."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
SCOPE = ROOT / "artifacts/rust/combined-profile"
FIRST_PARTY = ("desktop-lifecycle", "desktop-platform-log", "ifw-immich", "ifw-legacy", "safe-fs")
SPIKES = ("gui", "linux-services", "portal-dialog", "windows-services", "storage", "yaml", "realtime",
          "performance/worker")
sys.path.insert(0, str(QA))
from gui import source_profile
from realtime import hyper_util_source
from storage.evidence import sha256
spec = importlib.util.spec_from_file_location("rw02_yaml_prepare", QA / "yaml/prepare.py")
yaml_prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yaml_prepare)
HYPER_KEY = ("hyper-util", "0.1.21")
HYPER_ROOT = hyper_util_source.SOURCE


def hyper_tree(receipt):
    return {"originalSha256": receipt["archiveSha256"], "compilerTreeSha256": receipt["treeSha256"],
            "files": receipt["fileCount"], "transformations": [
                {"path": path, **change} for path, change in sorted(receipt["changes"].items())]}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def locked(directory):
    rows = tomllib.loads((directory / "Cargo.lock").read_text(encoding="utf-8"))["package"]
    result = {}
    for row in rows:
        if "source" in row:
            if row["source"] != "registry+https://github.com/rust-lang/crates.io-index" or not row.get("checksum"):
                raise ValueError(f"Unknown lock source for {row['name']}")
            result[row["name"], row["version"]] = row["checksum"]
    return result


def catalog():
    result = {}
    for name in SPIKES:
        for key, checksum in locked(QA / name).items():
            if result.setdefault(key, checksum) != checksum:
                raise ValueError(f"Conflicting input hashes for {key}")
    return result


def public_archive(name, archive, expected):
    url = f"https://static.crates.io/crates/{name}/{archive.name}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as source, archive.open("wb") as target:
                while block := source.read(512 * 1024):
                    if target.tell() + len(block) > 64 * 1024 * 1024:
                        raise ValueError(f"Oversize public archive {archive.name}")
                    target.write(block)
            break
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    if sha256(archive) != expected:
        raise ValueError(f"Wrong published bytes for {archive.name}")


def prepare(work, homes, fetch):
    approved_text = source_profile.validate()
    supplements = read(ROOT / "rust/audit/gui-inputs.json")["files"]
    for item in supplements:
        if sha256(ROOT / "rust" / item["path"]) != item["sha256"]:
            raise ValueError(f"Changed GUI notice or font: {item['path']}")
    allowed = catalog()
    hyper = next(p for p in read(QA / "realtime/inputs.json")["packages"] if (p["name"], p["version"]) == HYPER_KEY)
    if hyper["archiveSha256"] != hyper_util_source.ARCHIVE_SHA:
        raise ValueError("The realtime archive review differs from its source reconstruction")
    allowed[HYPER_KEY] = hyper["archiveSha256"]
    vendor, inputs = prepare_registry(work, [home / "registry" for home in homes], fetch, allowed)
    return vendor, inputs, approved_text


def prepare_registry(work, registries, fetch, allowed, *, jobs=4):
    """Authenticate and filter the selected original crates using the combined compiler rules."""
    yaml = {(row["name"], row["version"]): row for row in read(QA / "yaml/inputs.json")["packages"]}
    cache = work / "registry/cache/reviewed"
    vendor = work / "registry/src/reviewed"
    cache.mkdir(parents=True)
    vendor.mkdir(parents=True)
    locations = sorted({location for registry in registries for location in (registry / "cache").glob("*")
                        if location.is_dir()})
    locations.append(HYPER_ROOT.parent)

    def one(item):
        (name, version), checksum = item
        prefix = f"{name}-{version}"
        archive = cache / (prefix + ".crate")
        original = next((directory / archive.name for directory in locations if (directory / archive.name).is_file()), None)
        if original:
            shutil.copyfile(original, archive)
        elif fetch:
            public_archive(name, archive, checksum)
        else:
            raise FileNotFoundError(f"Missing {archive.name} in the private Cargo caches")
        if (name, version) == HYPER_KEY:
            receipt = hyper_util_source.reconstruct(archive, HYPER_ROOT)
            # Keep the authenticated original available to the standalone notice generator.
            hyper_util_source.original(work)
            return prefix, hyper_tree(receipt)
        # This shared filter authenticates the original and rejects links and duplicate members.
        # Only base64-0.23.1 has an approved transformed README and promotional asset removal.
        files, changes = yaml_prepare.source_files(archive, prefix, checksum)
        hashes = {path: yaml_prepare.digest(data) for path, data in files.items()}
        filtered = yaml_prepare.digest(yaml_prepare.canonical(hashes))
        review = yaml.get((name, version))
        if changes and not review:
            raise ValueError(f"Unreviewed transformed input {prefix}")
        if review and (checksum != review["archive_sha256"] or filtered != review["filtered_tree_sha256"]
                       or changes != review["source_filter"]):
            raise ValueError(f"Compiler source differs from the YAML review: {prefix}")
        dest = vendor / prefix
        # Preserve executable bits on archived build tools as cargo vendor does.
        with tarfile.open(archive) as contents:
            executable = {member.name[len(prefix) + 1:] for member in contents
                          if member.isfile() and member.mode & 0o111}
        for relative, data in files.items():
            path = dest / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
            if relative in executable:
                path.chmod(0o755)
        write(dest / ".cargo-checksum.json", {"files": hashes, "package": checksum})
        return prefix, {"originalSha256": checksum, "compilerTreeSha256": filtered, "files": len(files),
                        "transformations": changes}

    with ThreadPoolExecutor(max_workers=jobs) as workers:
        inputs = dict(workers.map(one, sorted(allowed.items())))
    return vendor, inputs


def source_config(vendor):
    # JSON string literals form valid TOML basic strings, including escaped Windows paths.
    return ["--config", 'source.crates-io.replace-with="combined-review"',
            "--config", "source.combined-review.directory=" + json.dumps(str(vendor))]


def local_caches():
    area = ROOT / "artifacts/rust"
    return [area / name for name in ("assessment-cache", "realtime-assessment/cargo-home",
                                     "storage-assessment/cargo-home", "realtime-cargo", "storage-cargo-home",
                                     "yaml-assessment/private-cache")]
