"""Bind the modified AccessKit Unix registry input to the native Cargo library and rustc dependency file."""
import json
from pathlib import PurePosixPath
import re
import shutil

from sources import ROOT, accesskit_source, read, sha256


CRATE = "-".join(accesskit_source.KEY)
PACKAGE = "registry+https://github.com/rust-lang/crates.io-index#accesskit_unix@0.24.1"
SOURCE = PurePosixPath("/vendor") / CRATE


def reconstruction_inputs():
    return (accesskit_source.REVIEW, accesskit_source.PATCH, accesskit_source.HERE / "accesskit_source.py")


def correction(tree, notices):
    review = read(accesskit_source.REVIEW)
    changes = [{"path": path, **row} for path, row in sorted(review["files"].items())]
    if (tree["transformations"] != changes or tree["originalSha256"] != review["archiveSha256"]
            or tree["files"] != review["compilerTree"]["files"] or sha256(accesskit_source.PATCH) != review["patchSha256"]
            or {path.rsplit("/", 1)[1]: digest for path, digest in notices.items()} != review["notices"]):
        raise ValueError("The corrected AccessKit Unix compiler inputs differ from the review")
    return {"upstreamRevision": review["sourceRevision"], "inputs": {
        path.relative_to(ROOT).as_posix(): sha256(path) for path in reconstruction_inputs()}}


def compiled_library(log, target):
    rows = [json.loads(line) for line in log.splitlines() if line.startswith("{")]
    candidates = [row for row in rows if row["reason"] == "compiler-artifact" and row["package_id"] == PACKAGE]
    if len(candidates) != 1:
        raise ValueError("Expected one native AccessKit Unix compiler unit")
    row, = candidates
    if (row["manifest_path"] != str(SOURCE / "Cargo.toml") or row["target"]["src_path"] != str(SOURCE / "src/lib.rs")
            or row["target"]["kind"] != ["lib"] or row["features"] != ["async-io"]):
        raise ValueError("Unexpected AccessKit Unix compiler source or features")
    libraries = [p for p in row["filenames"] if p.endswith(".rlib")]
    if len(libraries) != 1 or not re.fullmatch(
            r"/build/" + re.escape(target) + r"/release/build/accesskit_unix/([a-f0-9]{16})/out/libaccesskit_unix-\1\.rlib",
            libraries[0]):
        raise ValueError("Expected the native release library for the observed AccessKit Unix unit")
    return PurePosixPath(libraries[0])


def check_depfile(data, library, changes):
    rows = [line.removeprefix(str(library) + ": ").split() for line in data.splitlines()
            if line.startswith(str(library) + ": ")]
    if len(rows) != 1:
        raise ValueError("Missing the native AccessKit Unix library dependency rule")
    names = rows[0]
    if (any(not PurePosixPath(p).is_relative_to(SOURCE) or ".." in PurePosixPath(p).parts for p in names)
            or not {str(SOURCE / p) for p in ["src/lib.rs", *changes]} <= set(names)):
        raise ValueError("The native library did not consume both corrected AccessKit Unix modules")


def retain(output, build, target, vendor):
    library = compiled_library((output / "build.log").read_text(encoding="utf-8"), target)
    path = build / library.relative_to("/build")
    depfile = path.with_name(path.stem.removeprefix("lib") + ".d")
    changes = read(accesskit_source.REVIEW)["files"]
    check_depfile(depfile.read_text(encoding="utf-8"), library, changes)
    for name, change in changes.items():
        if sha256(vendor / CRATE / name) != change["after"]:
            raise ValueError(f"Wrong compiler source bytes for {name}")
    shutil.copyfile(depfile, output / "accesskit-unix.d")
    shutil.copyfile(path, output / "accesskit-unix.rlib")
    return {"library": str(library), "rlibSha256": sha256(path), "depfileSha256": sha256(depfile),
            "modules": {name: row["after"] for name, row in changes.items()}}
