"""Run the original combined-profile Windows x64 executable in the local disposable guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

QA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QA / "combined-profile"))
from run import source_witness
from graphs import TARGETS
from native import exercise
import sbom
from sources import ROOT, read, sha256, write
from realtime.guest import verify_host

TARGET = "x86_64-pc-windows-msvc"
EXECUTABLE = "ifw-combined-assessment.exe"


def unpack(kit, output, executable, revision):
    index = json.loads(kit.read("compiler.json"))
    fields = {"build.log", "clippy.log", "profile.json", "source-trees.json", "inventory.json",
              "compiler-units.json", "linked-libraries.txt", EXECUTABLE}
    fields.update(target + suffix for target in TARGETS for suffix in (".json", ".tree"))
    if (index["passed"] is not True or index["revision"] != revision or "native" in index
            or index["compiler"]["target"] != TARGET or f"host: {TARGET}" not in index["rustc"]
            or set(index["outputs"]) != fields or sorted(kit.namelist()) != sorted(fields | {"compiler.json"})):
        raise ValueError("Expected the complete native compiler-only x64 input for this checkout")
    guest_sources = source_witness()
    if index["sources"].keys() != guest_sources.keys():
        raise ValueError("Compiler and guest source sets differ")
    for path, digest in index["sources"].items():
        original = sbom.blob(revision, path)
        sbom.source_matches(original, digest, True, path)
        sbom.source_matches(original, guest_sources[path], True, path)
    if (index["lock"] != sha256(QA / "combined-profile/Cargo.lock")
            or index["compiler"]["binarySha256"] != index["outputs"][EXECUTABLE]):
        raise ValueError("Incorrect profile lock or executable digest")
    for name in sorted(fields | {"compiler.json"}):
        dest = executable if name == EXECUTABLE else output / name
        with kit.open(name) as source, dest.open("xb") as target:
            shutil.copyfileobj(source, target)
        if name in fields and sha256(dest) != index["outputs"][name]:
            raise ValueError(f"Changed compiler output {name}")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("archive_sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") or platform.node().casefold() != "ifw-qa25":
        parser.error("Use the disposable local Windows x64 test VM")
    verify_host()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    output = args.output.resolve()
    with args.archive.open("rb") as original:
        if (not re.fullmatch(r"[0-9a-f]{64}", args.archive_sha256)
                or hashlib.file_digest(original, "sha256").hexdigest() != args.archive_sha256):
            raise ValueError("The supplied archive differs from the Actions digest")
        output.mkdir(parents=True, exist_ok=False)
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            area = Path(scratch)
            executable = area / EXECUTABLE
            with ZipFile(original) as kit:
                index = unpack(kit, output, executable, revision)
            fixture = area / "synthetic-root"
            fixture.mkdir()
            (fixture / "sample.txt").write_bytes(b"combined fixture\n")
            env = {key: value for key, value in os.environ.items() if key.upper() in
                   {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PROCESSOR_ARCHITECTURE"}}
            for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                env[key] = str(area)
            native = {**index.pop("compiler"), "isolation": "disposable local Windows x64 VM",
                      "compilerArchiveSha256": args.archive_sha256}
            checked = exercise(TARGET, [], [str(executable), str(fixture)], fixture, env, output,
                               read(QA / "storage/inputs.json")["sqlite"])
            native.update(checked)
    record = {**index, "native": native, "guest": {"host": platform.node(), "os": platform.platform()},
              "outputs": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}}
    # Check the same Git source, native compiler stream, inventory and feature graph used by SPDX.
    required = {name: (output / name).read_bytes() for name in
                ("profile.json", "inventory.json", "source-trees.json", "compiler-units.json",
                 "smoke.json", "build.log", TARGET + ".json", TARGET + ".tree")}
    sbom.verify(record, required, revision, TARGET)
    write(output / "result.json", record)
    print(output / "result.json")


if __name__ == "__main__":
    main()
