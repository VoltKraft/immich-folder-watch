"""Compile the source-pinned launcher variant against the ordinary retained GUI graph."""
import json
import os
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from common import BEFORE, QA, ROOT, launcher_variant, module, read, sha, write


def stage(work, wpf_primary=False):
    patch, expected = launcher_variant(wpf_primary)
    warm = module("ifw_installed_warm_build", QA / "windows-warm-window/build.py")
    gui = warm.stage(work / "project")
    path = gui / "src/windows_launcher.rs"
    if sha(path) != BEFORE:
        raise ValueError("The ordinary launcher differs from its reviewed source")
    original = path.read_bytes()
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(work.resolve()))
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--whitespace=error", "-"],
                   cwd=gui, input=patch.read_bytes(), env=env, check=True)
    if sha(path) != expected:
        raise ValueError("The private launcher does not match its reviewed patch")
    return warm, gui, original


def build(target, work, out, base, ordinary_gui, inventory, *, wpf_primary=False):
    patch, expected = launcher_variant(wpf_primary)
    warm, gui, original = stage(work, wpf_primary)
    paired = base["pairedBuild"]
    compiled = {p.name: sha(p) for p in (gui / "src").iterdir() if p.is_file()}
    if (compiled != {**paired["compilerInputs"], "windows_launcher.rs": expected}
            or sha(gui / "Cargo.lock") != paired["lock"] or sha(ordinary_gui) != paired["binary"]):
        raise ValueError("The private subject changed outside the reviewed launcher")
    env = dict(os.environ, CARGO_HOME=str(ROOT / "artifacts/rust/assessment-cache"),
               CARGO_TARGET_DIR=str(work / "target"), CARGO_NET_OFFLINE="true",
               IFW_QA_FONT_DIR=str(ROOT / "rust/assets/fonts"), IFW_QA_FALLBACK_DIR=str(warm.source_profile.FONTS))
    version = subprocess.check_output([sys.executable, str(QA / "check-toolchain.py"), target], env=env, text=True).strip()
    normal = ROOT / "artifacts/rust/windows-warm-window" / target
    standard = read(normal / "build.json")
    approved = warm.source_profile.prepare(fetch=False, registry=ROOT / "artifacts/rust/assessment-cache/registry")
    if (any(warm.source_profile.tree_info(gui / "artifacts/text" / name) != details for name, details in approved["trees"].items())
            or standard["baseFonts"] != {p.name: sha(p) for p in sorted((ROOT / "rust/assets/fonts").glob("*.ttf"))}
            or standard["fallbackFonts"] != {name: data["sha256"] for name, data in approved["fonts"].items()}):
        raise ValueError("The compiled text sources or licensed fonts differ from the ordinary retained GUI")
    rows = warm.feature_rows(gui / "Cargo.toml", target, env)
    if (standard["nativeCompiler"] != version or rows != warm.feature_rows(warm.GUI / "Cargo.toml", target, env)
            or len(rows) != standard["selectedFeatureRows"]):
        raise ValueError("The native compiler or normal/build feature selections differ from the ordinary GUI")
    with (out / "compiler.jsonl").open("xb") as log:
        subprocess.run(["cargo", "build", "--release", "--frozen", "--message-format=json-render-diagnostics"],
                       cwd=gui, env=env, stdout=log, check=True)
    messages = [json.loads(line) for line in (out / "compiler.jsonl").read_bytes().splitlines()]
    units = warm.compiler_graph(messages, gui, rows)
    archive = warm.eframe_source.source_bundle(gui, work / "private-eframe-source.zip")
    if archive["archiveSha256"] != standard["eframeSource"]["archiveSha256"]:
        raise ValueError("The compiled eframe/winit sources or notices differ from the ordinary retained GUI")
    libs = {}
    for package in (warm.eframe_source.PACKAGE, warm.eframe_source.WINIT_PACKAGE):
        features, = [f for n, _, f in rows if n == package.name]
        libs[package.name] = warm.compiled_library(messages, gui, work / "target", package, features)
    subject = work / "subject"
    subject.mkdir()
    name = "native-gui-assessment.exe"
    private = work / "target/release" / name
    app = warm.application_artifact(messages, gui, private)
    observer = ordinary_gui.parent.parent / "inventory-build/file-observer.exe"
    worker = ordinary_gui.with_name("ifw-performance-worker.exe")
    assets = {name: app["sha256"], worker.name: inventory["worker"], observer.name: inventory["fileObserver"]}
    if app["sha256"] == paired["binary"] or not assets[observer.name]:
        raise ValueError("Expected distinct compiled launcher and original native file observer")
    for src in (private, worker, observer):
        for folder in (subject, out):
            dst = folder / src.name
            shutil.copyfile(src, dst)
            if sha(dst) != assets[src.name]:
                raise ValueError("A native image changed while staging")
    with ZipFile(out / "sources.zip", "x", ZIP_DEFLATED) as z:
        z.writestr("before/windows_launcher.rs", original)
        z.write(gui / "src/windows_launcher.rs", "after/windows_launcher.rs")
        z.write(patch, "launcher.patch")
        z.write(gui / "Cargo.lock", "Cargo.lock")
        z.write(gui / "Cargo.toml", "Cargo.toml")
        for n in ("build.json", "compiler.jsonl", "eframe-source.zip"):
            z.write(normal / n, "ordinary/" + n)
        for n in ("build.json", "graph.json"):
            z.write(ROOT / "artifacts/rust/gui-native" / target / n, "canonical/" + n)
    receipt = dict(target=target, source=base["revision"], nativeCompiler=version, sourceArchive=sha(out / "sources.zip"),
                   compiler=sha(out / "compiler.jsonl"), rows=rows, units=units, application=app, libraries=libs,
                   assets=assets, base=base, sources=compiled)
    write(out / "build.json", receipt)
