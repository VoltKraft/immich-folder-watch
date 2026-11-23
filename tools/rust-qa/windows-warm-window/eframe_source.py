"""Reconstruct the retained HWND variant from its published eframe and winit sources."""
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
WINIT_PINS = HERE / "winit-source.json"
WINIT_PATCH = HERE / "winit-retained-visibility.patch"
WINIT_PACKAGE = Path("artifacts/retained/winit")
STANZA = (b'\n[patch.crates-io.eframe]\npath = "artifacts/retained/eframe"\n'
          b'\n[patch.crates-io.winit]\npath = "artifacts/retained/winit"\n')


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
    name, version = pins["crate"].rsplit("-", 1)
    if sha256(archive).hexdigest() != pins["archiveSha256"] or sha256(patch).hexdigest() != pins["patchSha256"]:
        raise ValueError(f"The published {name} archive or retained source patch differs")
    source.mkdir(parents=True)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as package:
        prefix = pins["crate"] + "/"
        names = []
        for member in package:
            if not member.isfile() or not member.name.startswith(prefix):
                raise ValueError(f"Unexpected {name} source archive member")
            names.append(member.name.removeprefix(prefix))
        source_profile.take_files(package, pins["crate"], names, source)
    original = {name: source_profile.sha(source / name) for name in names}
    vcs = json.loads((source / ".cargo_vcs_info.json").read_bytes())
    metadata = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    if (source_profile.tree_info(source) != pins["originalTree"] or vcs["git"]["sha1"] != pins["upstreamRevision"]
            or vcs["path_in_vcs"] != pins["pathInVcs"] or (metadata["name"], metadata["version"]) != (name, version)
            or metadata["license"] != pins["license"]):
        raise ValueError(f"Unexpected published {name} source tree, revision or license")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(source.parent))
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "apply", "--no-index", "--whitespace=error", "-"],
                   input=patch, cwd=source, env=env, check=True)
    compiled = {name: source_profile.sha(source / name) for name in names}
    changed = {name: {"original": original[name], "compiled": compiled[name]} for name in names if original[name] != compiled[name]}
    if changed != pins["modified"] or source_profile.tree_info(source) != pins["compilerTree"]:
        raise ValueError(f"Unexpected modified {name} compiler sources")


def verify_lock(gui, pins):
    original = tomllib.loads(checked_bytes(CANONICAL / "Cargo.lock", pins["canonicalLockSha256"]).decode("utf-8"))
    compiled = tomllib.loads(checked_bytes(gui / "Cargo.lock", pins["retainedLockSha256"]).decode("utf-8"))
    for package in (pins, json.loads(WINIT_PINS.read_bytes())):
        name, version = package["crate"].rsplit("-", 1)
        row, = [r for r in original["package"] if (r["name"], r["version"]) == (name, version)]
        if (row.pop("source") != "registry+https://github.com/rust-lang/crates.io-index"
                or row.pop("checksum") != package["archiveSha256"]):
            raise ValueError(f"The original {name} registry identity differs from its reviewed archive")
    if compiled != original:
        raise ValueError("The retained lock must change only the registry identity of eframe and winit")
    manifest = checked_bytes(CANONICAL / "Cargo.toml", pins["canonicalManifestSha256"])
    if checked_bytes(gui / "Cargo.toml", pins["retainedManifestSha256"]) != manifest + STANZA:
        raise ValueError("The retained Cargo.toml must add only the eframe and winit source overrides")


def prepare(gui):
    pins = json.loads(PINS.read_bytes())
    reconstruct(gui / PACKAGE, pins, original_archive(pins), checked_bytes(PATCH, pins["patchSha256"]))
    winit = json.loads(WINIT_PINS.read_bytes())
    reconstruct(gui / WINIT_PACKAGE, winit, original_archive(winit), checked_bytes(WINIT_PATCH, winit["patchSha256"]))
    with (gui / "Cargo.toml").open("ab") as manifest:
        manifest.write(STANZA)
    toolchain = ROOT / "artifacts/rust/toolchain/bin"
    env = dict(os.environ, CARGO_HOME=str(ROOT / "artifacts/rust/assessment-cache"),
               PATH=str(toolchain) + os.pathsep + os.environ["PATH"])
    subprocess.run([str(toolchain / ("cargo.exe" if os.name == "nt" else "cargo")), "update", "--offline",
                    "--manifest-path", str(gui / "Cargo.toml"), "-p", "eframe@0.37.0", "-p", "winit@0.30.13"],
                   env=env, cwd=gui, check=True)
    verify_lock(gui, pins)


def source_bundle(gui, destination):
    pins = json.loads(PINS.read_bytes())
    winit = json.loads(WINIT_PINS.read_bytes())
    verify_lock(gui, pins)
    if source_profile.tree_info(gui / PACKAGE) != pins["compilerTree"]:
        raise ValueError("The reconstructed eframe source changed during compilation")
    if source_profile.tree_info(gui / WINIT_PACKAGE) != winit["compilerTree"]:
        raise ValueError("The reconstructed winit source changed during compilation")
    members = {"pins.json": PINS.read_bytes(), pins["crate"] + ".crate": original_archive(pins),
               PATCH.name: checked_bytes(PATCH, pins["patchSha256"]),
               APPLICATION_PATCH.name: checked_bytes(APPLICATION_PATCH, pins["applicationPatchSha256"])}
    members.update({"winit-pins.json": WINIT_PINS.read_bytes(), winit["crate"] + ".crate": original_archive(winit),
                    WINIT_PATCH.name: checked_bytes(WINIT_PATCH, winit["patchSha256"]),
                    "notices/winit/LICENSE": checked_bytes(gui / WINIT_PACKAGE / winit["licenseFile"], winit["licenseSha256"])})
    for family, folder in (("canonical", CANONICAL), ("retained", gui)):
        for name in ("Cargo.lock", "Cargo.toml"):
            members[family + "/" + name] = (folder / name).read_bytes()
    for name, entry in pins["notices"].items():
        members["notices/" + name] = checked_bytes(ROOT / entry["path"], entry["sha256"])
    return {"pins": pins, "winitPins": winit, "archive": destination.name, "archiveSha256": write_archive(destination, members)}
