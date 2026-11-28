"""Build the one-shot frame-ready experiment against the same host's ordinary native GUI."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import prepare
from deferred_build import compiler_sources
from readback import compiler_receipt, inputs

HERE = prepare.HERE
GATE = "artifacts/cost/ifw-frame-timing/src/frame_ready.rs"
FILES = ("frame-ready.patch", "frame-ready-pins.json", "frame_ready.rs", "frame_ready_build.py", "frame_ready_case.py",
         "frame_ready_trace.py")
LIBRARIES = {"eframe", "egui-wgpu", "winit", "ifw-frame-timing"}


def read(path):
    return json.loads(path.read_bytes())


def expected_sources(base, pins):
    if set(pins["libraries"]) != LIBRARIES:
        raise ValueError("Unexpected frame-ready library set")
    application = dict(base["application"])
    for name, (before, after) in pins["files"].items():
        if name.startswith("src/"):
            leaf = Path(name).name
            if name != "src/" + leaf or application[leaf] != before:
                raise ValueError("A frame-ready application patch differs from its original source")
            application[leaf] = after
    return dict(application=application, libraries={**base["trees"], **pins["libraries"]})


def profile_pins(sources):
    pins = read(HERE / "frame-ready-pins.json")
    original = sources["application"]["main.rs"]
    if original != pins["files"]["src/main.rs"][0]:
        language_main = prepare.warm.language_profile()["frameReadyMain"]
        if original != language_main[0]:
            raise ValueError("Unreviewed retained main source for frame readiness")
        pins["files"]["src/main.rs"] = language_main
    return pins


def stage(out, *, canonical=None):
    gui, rows, sources = prepare.stage(out, canonical=canonical)
    pins = profile_pins(sources)
    for name, (before, _) in pins["files"].items():
        prepare.checked(gui / name, before)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.resolve()))
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero", "--whitespace=error", "-"],
                   cwd=gui, input=(HERE / "frame-ready.patch").read_bytes(), env=env, check=True)
    with (gui / GATE).open("xb") as new:
        new.write((HERE / "frame_ready.rs").read_bytes())
    for name, (_, after) in pins["files"].items():
        prepare.checked(gui / name, after)
    if compiler_sources(gui) != expected_sources(sources, pins):
        raise ValueError("Unexpected one-shot private compiler sources")
    return gui, rows, sources, pins


def build(out, base, record):
    if record["target"] != prepare.TARGET:
        raise ValueError("Frame readiness requires the original native Windows x64 host")
    gui, rows, sources, pins = stage(out)
    paired = prepare.paired_inputs(base, gui, sources)
    env = prepare.environment(out)
    native = subprocess.check_output([sys.executable, str(prepare.QA / "check-toolchain.py"), prepare.TARGET],
                                     env=env, text=True).strip()
    if paired["nativeCompiler"] != native or paired["binary"] != record["binary"]:
        raise ValueError("The native compiler or ordinary executable differs from the measured baseline")
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--release", "--frozen", "--message-format=json-render-diagnostics"],
                       cwd=gui, env=env, stdout=log, check=True)
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    libraries = prepare.compiler_units(messages, gui, rows, out / "build")
    exe = out / "build/release/native-gui-assessment.exe"
    app = prepare.warm.application_artifact(messages, gui, exe)
    compiled = compiler_sources(gui)
    if app["sha256"] == paired["binary"] or compiled != expected_sources(sources, pins):
        raise ValueError("Expected a distinct executable and unchanged compiler inputs")
    bundle = {n: (HERE / n).read_bytes() for n in FILES}
    bundle.update({"compiled/" + n: (gui / n).read_bytes() for n in [*pins["files"], GATE]})
    supplement = prepare.warm.eframe_source.write_archive(out / "frame-ready-source.zip", bundle)
    binary = out / "frame-ready.exe"
    shutil.copyfile(exe, binary)
    receipt = dict(source=sources, compilerSha256=prepare.sha(stream), application=app, libraries=libraries,
                   nativeCompiler=native, pairedBuildSha256=prepare.sha(base / "build.json"), pairedBinary=paired["binary"],
                   pairedCompiler=paired["compilerEvidence"]["sha256"], compilerSources=compiled, supplement=supplement,
                   sources={n: sha256(data).hexdigest() for n, data in bundle.items()})
    (out / "frame-ready-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    record.update(pairedBinary=paired["binary"], binary=prepare.sha(binary), diagnosticInputs=inputs(),
                  frameReadyBuild=prepare.sha(out / "frame-ready-build.json"))
    return binary


def verify(out, record):
    if record["diagnosticInputs"] != inputs():
        raise ValueError("Different base frame observer or reconstruction sources")
    compiler_receipt(out, record, prefix="frame-ready", receipt_key="frameReadyBuild")
    receipt = read(out / "frame-ready-build.json")
    if receipt["supplement"] != prepare.sha(out / "frame-ready-source.zip"):
        raise ValueError("The one-shot source archive changed")
    pins = profile_pins(receipt["source"])
    with ZipFile(out / "frame-ready-source.zip") as archive:
        expected = set(FILES) | {"compiled/" + n for n in [*pins["files"], GATE]}
        if (set(archive.namelist()) != expected or len(archive.namelist()) != len(expected)
                or any(archive.read(n) != (HERE / n).read_bytes() for n in FILES)
                or any(sha256(archive.read("compiled/" + n)).hexdigest() != after for n, (_, after) in pins["files"].items())
                or archive.read("compiled/" + GATE) != archive.read("frame_ready.rs")
                or receipt["sources"] != {n: sha256(archive.read(n)).hexdigest() for n in expected}
                or receipt["compilerSources"] != expected_sources(receipt["source"], pins)):
            raise ValueError("The captured compiler sources differ from the one-shot frame-ready input")
