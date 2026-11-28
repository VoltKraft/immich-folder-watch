"""Compile a paired retained GUI and inventory worker for the local x64 Explorer trial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
ART = ROOT / "artifacts/rust"
TARGET = "x86_64-pc-windows-msvc"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory_sources(directory):
    yaml = QA / "yaml"
    inputs = json.loads((yaml / "inputs.json").read_bytes())
    if sha(yaml / "Cargo.lock") != inputs["lock_sha256"]:
        raise ValueError("The inventory acquisition lock differs from its review")
    cache = ART / "assessment-cache"
    subprocess.run(["cargo", "metadata", "--manifest-path", str(yaml / "Cargo.toml"), "--locked", "--format-version", "1"],
                   cwd=ROOT, env=dict(os.environ, CARGO_HOME=str(cache)), stdout=subprocess.DEVNULL, check=True)
    prepare = runpy.run_path(str(yaml / "prepare.py"))
    vendor = directory / "vendor-inputs"
    changes = prepare["prepare"](cache, vendor, inputs)
    archive = ART / "yaml-assessment/runs" / TARGET / "filtered-sources.tar"
    archive.parent.mkdir(parents=True, exist_ok=True)
    prepare["bundle"](vendor, changes, archive)
    if sha(archive) != inputs["filtered_bundle_sha256"]:
        raise ValueError("The filtered worker sources differ from the audited archive")


def build(target):
    if (os.name != "nt" or target != TARGET or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.environ.get("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.environ.get("GITHUB_REF") != "refs/heads/rewrite/rust"):
        raise ValueError("Use the branch-bound native Windows x64 compiler")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != os.environ.get("GITHUB_SHA"):
        raise ValueError("The compiler revision differs from the workflow revision")
    out = ART / "local-vm-inputs/tray"
    out.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, "-B", str(QA / "build-gui-probe.py"), target,
                    "--local-x64-inputs", str(ART / "local-vm-inputs/gui")], check=True)
    subprocess.run([sys.executable, "-B", str(QA / "windows-warm-window/build.py"), target, "--compile-only"], check=True)
    canonical = ART / "gui-native" / target
    cold = ART / "gui-build/release/native-gui-assessment.exe"
    warm = ART / "windows-warm-window" / target
    gui = warm / "build/release/native-gui-assessment.exe"
    retained = json.loads((warm / "build.json").read_bytes())
    machine = runpy.run_path(str(QA / "windows-performance/build.py"))["pe_machine"]
    with TemporaryDirectory(prefix="ifw-tray-build-") as name:
        directory = Path(name)
        inventory_sources(directory)
        worker_build = runpy.run_path(str(QA / "windows-inventory/subject.py"))
        subject, _, inventory = worker_build["build_subject"](directory, out, gui, target, machine, compile_only=True)
        shutil.copyfile(subject.with_name("ifw-performance-worker.exe"), out / "ifw-performance-worker.exe")
    files = {"canonical/native-gui-assessment.exe": cold, "canonical/build.json": canonical / "build.json",
             "canonical/graph.json": canonical / "graph.json", "native-gui-assessment.exe": gui,
             "retained/build.json": warm / "build.json", "retained/compiler.jsonl": warm / "compiler.jsonl",
             "retained/eframe-source.zip": warm / "eframe-source.zip"}
    project = warm / "project/tools/rust-qa/gui"
    for source in [project / "Cargo.toml", project / "Cargo.lock", *(project / "src").glob("*.rs"),
                   project / "src/tray-icon.argb"]:
        files["retained/project/" + source.relative_to(project).as_posix()] = source
    for library in ("eframeUnit", "winitUnit"):
        for path, expected in retained[library]["outputs"].items():
            source = warm / "build" / path
            if sha(source) != expected:
                raise ValueError("The original retained library output changed")
            files["retained/build/" + path] = source
    for name, source in files.items():
        destination = out / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    receipt = dict(revision=revision, target=target, run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                   inventory=inventory, files={file.relative_to(out).as_posix(): sha(file)
                                               for file in sorted(out.rglob("*")) if file.is_file()})
    (out / "tray-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=[TARGET])
    build(parser.parse_args().target)
