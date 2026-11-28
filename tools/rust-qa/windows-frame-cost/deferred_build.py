"""Build the isolated one-frame Windows x64 comparison from the same-host frame diagnostic."""
from hashlib import sha256
import json
import os
import sys
from pathlib import Path
import shutil
import subprocess

import prepare

HERE = Path(__file__).resolve().parent
FILES = ("deferred.patch", "deferred_gate.rs", "deferred-pins.json", "deferred_build.py", "deferred_case.py")
GATE = "artifacts/cost/egui-wgpu/src/deferred_gate.rs"


def stage(out):
    gui, rows, sources = prepare.stage(out)
    pins = json.loads((HERE / "deferred-pins.json").read_bytes())["files"]
    for name, (before, _) in pins.items():
        prepare.checked(gui / name, before)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.resolve()))
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(key, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero", "--whitespace=error", "-"],
                   cwd=gui, input=(HERE / "deferred.patch").read_bytes(), env=env, check=True)
    shutil.copyfile(HERE / "deferred_gate.rs", gui / GATE)
    for name, (_, after) in pins.items():
        prepare.checked(gui / name, after)
    return gui, rows, sources


def compiler_sources(gui):
    return dict(libraries={name: prepare.warm.source_profile.tree_info(gui / path) for name, path in prepare.LIBS.items()},
                application={f.name: prepare.sha(f) for f in (gui / "src").iterdir() if f.is_file()})


def build(out, base, record):
    ordinary = json.loads((base / "build.json").read_bytes())
    framed = base / "frame-cost"
    original = json.loads((framed / "result.json").read_bytes())
    compiler = json.loads((framed / "diagnostic-build.json").read_bytes())
    if (original["status"] != "frame-cost-observed" or original["revision"] != ordinary["revision"]
            or original["target"] != prepare.TARGET or original["run"] != record["run"]
            or original["attempt"] != record["attempt"] or original["buildReceipt"] != record["buildReceipt"]
            or original["diagBuildSha256"] != prepare.sha(framed / "diagnostic-build.json")
            or original["pairedBinary"] != ordinary["binary"]
            or original["referenceBudgetSha256"] != record["referenceBudgetSha256"]):
        raise ValueError("The completed native stage diagnosis differs from this host or its frozen limits")
    gui, rows, sources = stage(out)
    if (sources != compiler["source"] or sources["archive"] != prepare.sha(framed / "source.zip")
            or (out / "source.zip").read_bytes() != (framed / "source.zip").read_bytes()):
        raise ValueError("The complete original diagnostic input could not be reconstructed")
    compiled = compiler_sources(gui)
    modified = json.loads((HERE / "deferred-pins.json").read_bytes())["libraries"]
    if compiled["libraries"] != {**sources["trees"], **modified}:
        raise ValueError("Unexpected deferred renderer source tree")
    env = prepare.environment(out)
    native = subprocess.check_output([sys.executable, str(prepare.QA / "check-toolchain.py"), prepare.TARGET],
                                     env=env, text=True).strip()
    if native != compiler["nativeCompiler"] or native != ordinary["nativeCompiler"]:
        raise ValueError("Different native x64 compiler")
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--release", "--frozen", "--message-format=json-render-diagnostics"],
                       cwd=gui, env=env, stdout=log, check=True)
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    libs = prepare.compiler_units(messages, gui, rows, out / "build")
    exe = out / "build/release/native-gui-assessment.exe"
    app = prepare.warm.application_artifact(messages, gui, exe)
    if app["sha256"] in (original["binary"], ordinary["binary"]) or compiler_sources(gui) != compiled:
        raise ValueError("Expected a distinct executable and unchanged private compiler inputs")
    files = {n:(HERE / n).read_bytes() for n in FILES}
    pins = json.loads(files["deferred-pins.json"])["files"]
    for n in [*pins, GATE]:
        files["compiled/" + n] = (gui / n).read_bytes()
    supplement = prepare.warm.eframe_source.write_archive(out / "deferred-source.zip", files)
    binary = out / "deferred.exe"
    shutil.copyfile(exe, binary)
    receipt = dict(target=prepare.TARGET, nativeCompiler=native, compiler=prepare.sha(stream), libraries=libs,
                   application=app, compilerSources=compiled, baselineBuild=record["buildReceipt"], ordinaryBinary=ordinary["binary"],
                   diagnosticBuild=original["diagBuildSha256"], sourceArchive=sources["archive"],
                   originalFrameResult=prepare.sha(framed / "result.json"), supplement=supplement,
                   sources={n:sha256(data).hexdigest() for n,data in files.items()})
    (out / "deferred-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    record.update(pairedBinary=record["binary"], binary=prepare.sha(binary),
                  deferredBuild=prepare.sha(out / "deferred-build.json"))
    return binary
