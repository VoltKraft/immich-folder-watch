"""Reconstruct the Windows x64 objects in the audited ring 0.17.14 source crate."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import tomllib


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj, directory):
    # All loadable sections, relocations and linker symbols survive --strip-debug.
    # COFF stores the wall-clock build timestamp in bytes 4..8 of its file header.
    dest = directory / "stripped.o"
    subprocess.run(["objcopy", "--strip-debug", str(obj), str(dest)], check=True)
    data = bytearray(dest.read_bytes())
    if data[:2] != b"\x64\x86":
        raise ValueError("Expected a Windows x64 COFF object")
    data[4:8] = bytes(4)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="ring-0.17.14.crate from the locked cache")
    parser.add_argument("--nasm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    nasm = args.nasm.resolve(strict=True)
    version = subprocess.check_output([nasm, "-v"], text=True).strip()
    if not version.startswith("NASM version 2.13.03 "):
        raise ValueError("Use NASM 2.13.03 as identified in each published object's CodeView metadata")
    lock = tomllib.loads(Path(__file__).with_name("Cargo.lock").read_text(encoding="utf-8"))
    package, = [p for p in lock["package"] if p["name"] == "ring" and p["version"] == "0.17.14"]
    crate_sha = digest(args.archive.read_bytes())
    if crate_sha != package["checksum"]:
        raise ValueError("Original ring archive differs from the assessment lockfile")
    report = {"nasm": version, "objcopy": subprocess.check_output(["objcopy", "--version"], text=True).splitlines()[0],
              "ringArchive": crate_sha, "objects": {}}
    with tempfile.TemporaryDirectory(prefix="ifw-ring-") as tmp:
        work = Path(tmp)
        with tarfile.open(args.archive) as archive:
            archive.extractall(work, filter="data")
        src = work / "ring-0.17.14"
        objects = sorted((src / "pregenerated").glob("*-nasm.o"))
        if len(objects) != 12:
            raise ValueError("Expected ring's 12 Windows x64 objects")
        for packaged in objects:
            stem = packaged.stem.removesuffix("-nasm")
            generator_name = ("sha512-x86_64" if stem == "sha256-x86_64" else stem) + ".pl"
            generator, = (src / "crypto").rglob(generator_name)
            asm = work / (packaged.stem + ".asm")
            subprocess.run(["perl", generator, "nasm", asm], check=True, cwd=src)
            # The published archive uses CRLF for some generated assembly;
            # NASM accepts either line ending.
            if asm.read_bytes().splitlines() != packaged.with_suffix(".asm").read_bytes().splitlines():
                raise ValueError(f"Regenerated assembly differs for {stem}")
            built = work / packaged.name
            subprocess.run([nasm, "-o", built, "-f", "win64", "-i", "include/",
                            "-i", str(src / "pregenerated") + os.sep, "-Xgnu", "-gcv8", asm],
                           cwd=src, check=True)
            first, second = canonical(packaged, work), canonical(built, work)
            if first != second:
                raise ValueError(f"Regenerated code, data, relocations or symbols differ for {stem}")
            report["objects"][packaged.name] = {
                "generator": generator.relative_to(src).as_posix(),
                "assemblySha256": digest(asm.read_bytes()),
                "archiveObjectSha256": digest(packaged.read_bytes()),
                "loadableObjectSha256": digest(first),
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Reconstructed {len(objects)} Windows x64 objects")


if __name__ == "__main__":
    main()
