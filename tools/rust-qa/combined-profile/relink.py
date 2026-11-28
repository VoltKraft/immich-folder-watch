"""Rebuild one LGPL Wayland interface from modified XML and relink the same Linux application."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

from native import linux_namespace, linux_renderer_symbols
from sources import HERE, QA, read, sha256, source_config, write

NAME = "wayland-protocols-plasma"
VERSION = "0.3.12"
XML = Path("plasma-wayland-protocols/src/protocols/blur.xml")
BEFORE = b'<interface name="org_kde_kwin_blur_manager" version="1">'
AFTER = b'<interface name="org_kde_kwin_blur_manager" version="2">'


def packages(lock):
    return {(p["name"], p["version"]): p for p in tomllib.loads(lock.read_text(encoding="utf-8"))["package"]}


def verify_lock(changed):
    original = packages(HERE / "Cargo.lock")
    actual = packages(changed)
    if original.keys() != actual.keys():
        raise ValueError("Relink changed the package set")
    for key, row in original.items():
        expected = row if key != (NAME, VERSION) else {k: v for k, v in row.items() if k not in {"source", "checksum"}}
        if actual[key] != expected:
            raise ValueError(f"Unexpected relink source change for {key}")


def run(tool, vendor, build, output, env, jobs, target, ordinary):
    # This scratch stays outside the receipts uploaded by CI.
    work = Path(tempfile.mkdtemp(prefix="relink-", dir=build.parent))
    crate = vendor / f"{NAME}-{VERSION}"
    original_files = read(crate / ".cargo-checksum.json")["files"]
    changed = work / "replacement"
    changed.mkdir()
    for relative, digest in original_files.items():
        path = changed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(crate / relative, path)
        if sha256(path) != digest:
            raise ValueError(f"Wrong corresponding source {relative}")
    data = (changed / XML).read_bytes()
    if data.count(BEFORE) != 1 or b"SPDX-License-Identifier: LGPL-2.1-or-later" not in data:
        raise ValueError("Unexpected source id or license in the KWin blur protocol")
    (changed / XML).write_bytes(data.replace(BEFORE, AFTER))
    profile = work / "relink-profile"
    profile.mkdir()
    for filename in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(HERE / filename, profile / filename)
    shutil.copytree(HERE / "src", profile / "src")
    prefix = linux_namespace(tool, vendor, build, output / "synthetic-root", read(QA / "storage/inputs.json")["sqlite"]["flags"],
                             alternate_profile=profile, replacement=changed)
    config = [*source_config(Path("/vendor")), "--config", f'patch.crates-io.{NAME}.path="/changed-plasma"']
    with (output / "relink.log").open("wb") as log:
        subprocess.run([*prefix, "/toolchain/bin/cargo", "generate-lockfile", "--offline", *config],
                       check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
        verify_lock(profile / "Cargo.lock")
        subprocess.run([*prefix, "/toolchain/bin/cargo", "build", "--release", "--target", target, "--frozen",
                        "--jobs", str(jobs), *config, "--message-format=json-render-diagnostics"],
                       check=True, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    binary = build / target / "release/ifw-combined-assessment"
    with (output / "relink-smoke.json").open("wb") as log:
        subprocess.run([*prefix, f"/build/{target}/release/ifw-combined-assessment", "/fixture"],
                       env=env, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=90)
    expected = read(output / "smoke.json")
    if expected["platform"]["kdeBlurManagerVersion"] != 1:
        raise ValueError("Unmodified binding missing")
    expected["platform"]["kdeBlurManagerVersion"] = 2
    if read(output / "relink-smoke.json") != expected or sha256(binary) == ordinary["binarySha256"]:
        raise ValueError("Modified bindings did not reach the linked application")
    if sha256(crate / XML) != original_files[XML.as_posix()]:
        raise ValueError("Original directory source was modified")
    record = {"name": NAME, "version": VERSION, "linkedInterface": "org_kde_kwin_blur_manager",
              "sourceXml": XML.as_posix(), "originalXml": sha256(crate / XML), "editedXml": sha256(changed / XML),
              "baselineVersion": 1, "rebuiltVersion": 2, "baselineBinary": ordinary["binarySha256"],
              "relinkedBinary": sha256(binary), "relinkedLock": sha256(profile / "Cargo.lock")}
    # The exact license text is under the bundled protocol source's COPYING.LIB.
    copies = {relative: sha256(changed / relative) for relative in original_files if Path(relative).name == "COPYING.LIB"}
    if not copies:
        raise ValueError("Corresponding sources lack the LGPL text")
    record["licenseFiles"] = copies
    record["nativeRendererSymbols"] = linux_renderer_symbols(binary, output / "relinked-renderer-symbols.txt", env)
    write(output / "relink.json", record)
    return record
