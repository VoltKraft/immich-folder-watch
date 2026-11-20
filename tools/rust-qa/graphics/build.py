"""Build a source-bound graphics experiment on a private copy of the native supervisor."""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from inputs import GUI_SOURCES, WORKER_SOURCES, sha, source_digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust"
BASE = ART / "performance/subjects/native-map-confirmed"
BASE_REVISION = "6c953e32c0b2710bfe06b19805214946653480af"


def instrument_submit(work, subject, receipt):
    original = HERE.parent / "performance/present.rs"
    if sha(original) != receipt["sources"]["tools/rust-qa/performance/present.rs"]:
        raise ValueError("Vulkan observation source differs from the reviewed worker receipt")
    source = work / "driver-src"
    source.mkdir()
    content = original.read_text()
    site = '    let actual = unsafe { resolve(device, name) };'
    if content.count(site) != 1:
        raise ValueError("The approved device dispatch site changed")
    content = content.replace(site, site + '\n    if let Some(proxy) = unsafe { submit_loss::resolve(name, actual) } { return proxy; }')
    (source / "driver.rs").write_text(content + '\nmod submit_loss;\n')
    shutil.copyfile(HERE / "submit_loss.rs", source / "submit_loss.rs")
    output = subject / "submit-observer"
    output.mkdir()
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--dev", "/dev",
               "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/qa-home", "--ro-bind", "/usr", "/usr",
               "--ro-bind", str(ART / "toolchain"), "/toolchain", "--ro-bind", str(source), "/source",
               "--bind", str(output), "/out", "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "HOME", "/qa-home"]
    for name in ("/lib", "/lib64", "/bin"):
        path = Path(name)
        if path.is_symlink():
            command.extend(("--symlink", os.readlink(path), name))
        elif path.is_dir():
            command.extend(("--ro-bind", name, name))
    for name in ("/etc/ld.so.cache", "/etc/alternatives"):
        if Path(name).exists():
            command.extend(("--ro-bind", name, name))
    subprocess.run([*command, "--chdir", "/source", "--", "/toolchain/bin/rustc", "--edition", "2024", "--crate-type", "cdylib",
                    "-O", "-D", "warnings", "-Clink-arg=-Wl,-z,nodelete", "-Clink-arg=-Wl,-soname,libvulkan.so.1",
                    "driver.rs", "-o", "/out/libvulkan.so.1"], check=True)
    return sha(output / "libvulkan.so.1")


def build(label, base):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", label):
        raise ValueError("Use a fresh experiment label")
    base = base.resolve(strict=True)
    if not base.is_relative_to(ART):
        raise ValueError("Select a separately staged native performance subject")
    receipt = base / "native-gui-assessment.inputs.json"
    source = json.loads(receipt.read_text())
    workers = json.loads((base / "worker.inputs.json").read_text())
    if (source_digest(source) != GUI_SOURCES or source_digest(workers) != WORKER_SOURCES
            or sha(base / "native-gui-assessment") != source["binary_sha256"]
            or workers["gui_sha256"] != source["binary_sha256"]):
        raise ValueError("Restore the source-bound native GUI and audited worker profile")
    work = ART / "graphics" / label
    work.mkdir(parents=True, exist_ok=False)
    project = work / "project"
    gui = project / "tools/rust-qa/gui"
    paths = ["rust", "tools/rust-qa/gui/src", "tools/rust-qa/gui/Cargo.toml", "tools/rust-qa/gui/Cargo.lock",
             "tools/rust-qa/gui/build.py", "tools/rust-qa/verify-gui-inputs.py", "tools/rust-qa/check-toolchain.py"]
    archive = subprocess.check_output(["git", "archive", BASE_REVISION, *paths], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as members:
        members.extractall(project, filter="data")
    for name, wanted in source["sources"].items():
        if sha(project / name) != wanted:
            raise ValueError(f"Archived GUI input differs from the frozen source receipt {name}")
    (project / "artifacts/rust").mkdir(parents=True)
    target = ART / "graphics/build-target"
    target.mkdir(exist_ok=True)
    (project / "artifacts/rust/gui-build").symlink_to(target, target_is_directory=True)
    with (HERE / "supervisor.patch").open("rb") as changes:
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"], cwd=gui, stdin=changes, check=True)
    shutil.copyfile(HERE / "graphics.rs", gui / "src/graphics.rs")
    command = [sys.executable, str(gui / "build.py"), "--toolchain", str(ART / "toolchain"),
               "--registry", str(ART / "assessment-cache/registry")]
    subprocess.run([*command, "--clippy"], check=True)
    subprocess.run(command, check=True)
    subject = work / "subject"
    subject.mkdir()
    for name in ("native-gui-assessment", "native-gui-assessment.inputs.json"):
        shutil.copyfile(target / "release" / name, subject / name)
    (subject / "native-gui-assessment").chmod(0o755)
    for name, digest in (("ifw-performance-worker", workers["worker_sha256"]),
                         ("observer/libvulkan.so.1", workers["observer_sha256"])):
        if sha(base / name) != digest:
            raise ValueError(f"Changed source-bound helper {name}")
        (subject / name).parent.mkdir(exist_ok=True)
        shutil.copy2(base / name, subject / name)
    submit = instrument_submit(work, subject, workers)
    provenance = dict(base_receipt=sha(receipt), base_revision=BASE_REVISION, base=source["binary_sha256"],
                      patch=sha(HERE / "supervisor.patch"), graphics=sha(HERE / "graphics.rs"),
                      builder=sha(Path(__file__)), pins=sha(HERE / "inputs.py"),
                      baseline_builder=sha(gui / "build.py"), worker=workers["worker_sha256"],
                      observer=workers["observer_sha256"], gui=sha(subject / "native-gui-assessment"),
                      submit_source=sha(HERE / "submit_loss.rs"), submit_observer=submit)
    (subject / "graphics.inputs.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(subject)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("--base-subject", type=Path, default=BASE)
    args = parser.parse_args()
    build(args.label, args.base_subject)
