"""Retain and reopen the tested native writer and its development-only identity oracle."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[2]
FILES = ("instance.exe", "InstanceOracle.dll", "InstanceOracle.deps.json", "InstanceOracle.runtimeconfig.json")
LIMIT = 8 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sources():
    """Match instance.build's Windows source receipt, including the pinned shipping coordinator."""
    pinned = json.loads((HERE / "legacy-inputs.json").read_bytes())["windows"]
    files = [HERE / name for name in ("Program.cs", "InstanceOracle.csproj", "legacy-inputs.json",
                                      "main.rs", "unix.rs", "windows.rs", "run.py")]
    files.append(HERE.parent / "gui/src/win32_instance.rs")
    result = {f.relative_to(ROOT).as_posix(): digest(f.read_bytes()) for f in files}
    for name, expected in pinned.items():
        if digest((ROOT / name).read_bytes().replace(b"\r\n", b"\n")) != expected:
            raise ValueError("The legacy coordinator differs from its reference")
    return result | pinned


def validate(receipt, target, blobs):
    if (receipt["native_target"] != target or receipt["passed"] is not True
            or receipt["source_sha256"] != sources()
            or receipt["dotnet_sdk"] != json.loads((ROOT / "global.json").read_bytes())["sdk"]["version"]
            or receipt["legacy_reference"] != json.loads((HERE / "legacy-inputs.json").read_bytes())["reference"]):
        raise ValueError("The tested Windows build does not match the target or the local reference sources")
    hashes = {name: digest(data) for name, data in blobs.items()}
    if (receipt["files"] != hashes or hashes["instance.exe"] != receipt["rust_binary_sha256"]
            or hashes["InstanceOracle.dll"] != receipt["oracle_sha256"]):
        raise ValueError("The retained writer or identity oracle differs from its build receipt")


def retain(directory, exe, dll, result):
    blobs = {name: (exe if name == "instance.exe" else dll.parent / name).read_bytes() for name in FILES}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    receipt = {**result, "revision": revision, "files": {name: digest(data) for name, data in blobs.items()}}
    validate(receipt, result["native_target"], blobs)
    directory.mkdir()
    for name, data in blobs.items():
        (directory / name).write_bytes(data)
    (directory / "build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def stage(archive, expected_digest, directory, target, env):
    # The caller takes this digest from the native Actions artifact record.
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_digest:
            raise ValueError("The native build ZIP differs from its Actions digest")
        source.seek(0)
        with ZipFile(source) as z:
            if (sorted(z.namelist()) != sorted((*FILES, "build.json"))
                    or any(i.file_size > LIMIT for i in z.infolist())):
                raise ValueError("Unexpected native build ZIP contents")
            receipt = json.loads(z.read("build.json"))
            blobs = {name: z.read(name) for name in FILES}
    validate(receipt, target, blobs)
    dotnet = shutil.which("dotnet", path=env["PATH"])
    if not dotnet:
        raise FileNotFoundError("The native .NET 10 runtime is required for the development identity oracle")
    directory.mkdir()
    for name, data in blobs.items():
        (directory / name).write_bytes(data)
    return (directory / "instance.exe", [dotnet, directory / "InstanceOracle.dll"],
            {**receipt, "nativeArchiveSha256": expected_digest})
