"""Reconstruct the retained HWND variant from the published eframe archive and its reviewed change."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib

HERE = Path(__file__).resolve().parent
QA = HERE.parent
sys.path.insert(0, str(QA))
from gui import source_profile
sys.path.append(str(QA / "combined-profile"))
from notices import write_archive

ROOT = source_profile.ROOT
CANONICAL = source_profile.HERE
PINS = HERE / "eframe-source.json"
PATCH = HERE / "eframe-hidden-input.patch"
APPLICATION_PATCH = HERE / "retained-hidden-input.patch"
PACKAGE = Path("artifacts/retained/eframe")
STANZA = b'\n[patch.crates-io.eframe]\npath = "artifacts/retained/eframe"\n'


def checked_bytes(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Changed source input: {path.name}")
    return data


def original_archive(pins):
    filename = pins["crate"] + ".crate"
    registry = ROOT / "artifacts/rust/assessment-cache/registry/cache"
    matches = sorted(registry.glob("*/" + filename))
    if not matches:
        raise FileNotFoundError(f"The reviewed native GUI cache is missing {filename}")
    return checked_bytes(matches[0], pins["archiveSha256"])


def reconstruct(source, pins, archive, patch):
    if sha256(archive).hexdigest() != pins["archiveSha256"] or sha256(patch).hexdigest() != pins["patchSha256"]:
        raise ValueError("The published eframe archive or retained source patch differs")
    source.mkdir(parents=True)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as package:
        prefix = pins["crate"] + "/"
        names = []
        for member in package:
            if not member.isfile() or not member.name.startswith(prefix):
                raise ValueError("Unexpected eframe source archive member")
            names.append(member.name.removeprefix(prefix))
        source_profile.take_files(package, pins["crate"], names, source)
    original = {name: source_profile.sha(source / name) for name in names}
    vcs = json.loads((source / ".cargo_vcs_info.json").read_bytes())
    metadata = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    if (source_profile.tree_info(source) != pins["originalTree"] or vcs["git"]["sha1"] != pins["upstreamRevision"]
            or vcs["path_in_vcs"] != "crates/eframe" or metadata["license"] != pins["license"]):
        raise ValueError("Unexpected published eframe source tree, revision or license")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(source.parent))
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(name, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "apply", "--no-index", "--whitespace=error", "-"],
                   input=patch, cwd=source, env=env, check=True)
    compiled = {name: source_profile.sha(source / name) for name in names}
    changed = {name: {"original": original[name], "compiled": compiled[name]} for name in names if original[name] != compiled[name]}
    if changed != pins["modified"] or source_profile.tree_info(source) != pins["compilerTree"]:
        raise ValueError("Unexpected modified eframe compiler sources")


def verify_lock(gui, pins):
    original = tomllib.loads(checked_bytes(CANONICAL / "Cargo.lock", pins["canonicalLockSha256"]).decode("utf-8"))
    compiled = tomllib.loads(checked_bytes(gui / "Cargo.lock", pins["retainedLockSha256"]).decode("utf-8"))
    candidates = [row for row in original["package"] if row["name"] == "eframe" and row["version"] == "0.37.0"]
    if len(candidates) != 1:
        raise ValueError("The canonical Cargo.lock must select one eframe package")
    eframe = candidates[0]
    if (eframe.pop("source") != "registry+https://github.com/rust-lang/crates.io-index"
            or eframe.pop("checksum") != pins["archiveSha256"] or compiled != original):
        raise ValueError("The retained Cargo.lock must replace only eframe's registry identity")
    manifest = checked_bytes(CANONICAL / "Cargo.toml", pins["canonicalManifestSha256"])
    if checked_bytes(gui / "Cargo.toml", pins["retainedManifestSha256"]) != manifest + STANZA:
        raise ValueError("The retained Cargo.toml must add only the eframe source override")


def prepare(gui):
    pins = json.loads(PINS.read_bytes())
    reconstruct(gui / PACKAGE, pins, original_archive(pins), checked_bytes(PATCH, pins["patchSha256"]))
    with (gui / "Cargo.toml").open("ab") as manifest:
        manifest.write(STANZA)
    toolchain = ROOT / "artifacts/rust/toolchain/bin"
    env = dict(os.environ, CARGO_HOME=str(ROOT / "artifacts/rust/assessment-cache"),
               PATH=str(toolchain) + os.pathsep + os.environ["PATH"])
    subprocess.run([str(toolchain / ("cargo.exe" if os.name == "nt" else "cargo")), "update", "--offline",
                    "--manifest-path", str(gui / "Cargo.toml"), "-p", "eframe@0.37.0", "--precise", "0.37.0"],
                   env=env, cwd=gui, check=True)
    verify_lock(gui, pins)


def source_bundle(gui, destination):
    pins = json.loads(PINS.read_bytes())
    verify_lock(gui, pins)
    if source_profile.tree_info(gui / PACKAGE) != pins["compilerTree"]:
        raise ValueError("The reconstructed eframe source changed during compilation")
    members = {"pins.json": PINS.read_bytes(), pins["crate"] + ".crate": original_archive(pins),
               PATCH.name: checked_bytes(PATCH, pins["patchSha256"]),
               APPLICATION_PATCH.name: checked_bytes(APPLICATION_PATCH, pins["applicationPatchSha256"])}
    for family, folder in (("canonical", CANONICAL), ("retained", gui)):
        for name in ("Cargo.lock", "Cargo.toml"):
            members[family + "/" + name] = (folder / name).read_bytes()
    for name, entry in pins["notices"].items():
        members["notices/" + name] = checked_bytes(ROOT / entry["path"], entry["sha256"])
    return {"pins": pins, "archive": destination.name, "archiveSha256": write_archive(destination, members)}


def compiled_eframe(messages, gui, build, features):
    manifest = PACKAGE / "Cargo.toml"
    crate_root = PACKAGE / "src/lib.rs"
    units = [item for item in messages if item.get("reason") == "compiler-artifact"
             and item["target"]["name"] == "eframe"]
    if (len(units) != 1 or messages[-1] != {"reason": "build-finished", "success": True}
            or Path(units[0]["manifest_path"]).resolve() != (gui / manifest).resolve()
            or Path(units[0]["target"]["src_path"]).resolve() != (gui / crate_root).resolve()
            or sorted(units[0]["features"]) != sorted(features)):
        raise ValueError("The release compiler did not build the selected retained eframe source and features")
    files = [Path(name).resolve() for name in units[0]["filenames"]]
    if not files or not any(f.suffix == ".rlib" for f in files) or any(not f.is_relative_to(build.resolve()) for f in files):
        raise ValueError("Missing retained eframe compiler outputs")
    return {"manifest": manifest.as_posix(), "crateRoot": crate_root.as_posix(), "features": sorted(features),
            "outputs": {f.relative_to(build.resolve()).as_posix(): source_profile.sha(f) for f in files}}
