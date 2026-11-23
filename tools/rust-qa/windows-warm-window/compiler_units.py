"""Authenticate a reconstructed library from the Cargo stream and its actual build outputs."""
import hashlib
from pathlib import Path


def compiled_library(messages, gui, build, package, features):
    name = package.name
    manifest = package / "Cargo.toml"
    crate_root = package / "src/lib.rs"
    finished = {"reason": "build-finished", "success": True}
    units = [item for item in messages if item.get("reason") == "compiler-artifact"
             and item["target"]["name"] == name and item["target"]["kind"] == ["lib"]]
    if (len(units) != 1 or not messages or messages[-1] != finished
            or sum(item["reason"] == "build-finished" for item in messages) != 1
            or Path(units[0]["manifest_path"]).resolve() != (gui / manifest).resolve()
            or Path(units[0]["target"]["src_path"]).resolve() != (gui / crate_root).resolve()
            or sorted(units[0]["features"]) != sorted(features)):
        raise ValueError(f"The release compiler did not build the selected retained {name} source and features")
    build = build.resolve()
    files = [Path(filename).resolve() for filename in units[0]["filenames"]]
    libraries = [f for f in files if f.suffix == ".rlib" and (f.stem == "lib" + name or f.stem.startswith("lib" + name + "-"))]
    if len(libraries) != 1 or len(set(files)) != len(files) or any(not f.is_relative_to(build) or not f.is_file() for f in files):
        raise ValueError(f"Missing or ambiguous retained {name} compiler outputs")
    outputs = {}
    for path in files:
        with path.open("rb") as stream:
            outputs[path.relative_to(build).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"manifest": manifest.as_posix(), "crateRoot": crate_root.as_posix(), "features": sorted(features), "outputs": outputs}
