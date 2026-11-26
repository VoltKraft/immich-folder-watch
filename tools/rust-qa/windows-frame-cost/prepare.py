"""Build an additional source-bound diagnostic PE after the ordinary retained subject."""
from io import BytesIO
from hashlib import sha256
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
WARM = QA / "windows-warm-window"
sys.path.insert(0, str(WARM))
spec = importlib.util.spec_from_file_location("cost_retained", WARM / "build.py")
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)
TARGET = "x86_64-pc-windows-msvc"
LOCAL = Path("artifacts/cost")
TIMING = "ifw-frame-timing"
LIBS = {"eframe": warm.eframe_source.PACKAGE, "winit": warm.eframe_source.WINIT_PACKAGE,
        **{name: LOCAL / name for name in ("egui-wgpu", "wgpu-hal", TIMING)}}
PINS = json.loads((HERE / "sources.json").read_bytes())
sha = warm.sha
checked = warm.eframe_source.checked_bytes


def environment(out):
    return dict(os.environ, CARGO_HOME=str(ROOT / "artifacts/rust/assessment-cache"), CARGO_NET_OFFLINE="true",
                CARGO_TARGET_DIR=str(out / "build"), IFW_QA_FONT_DIR=str(ROOT / "rust/assets/fonts"),
                IFW_QA_FALLBACK_DIR=str(warm.source_profile.FONTS),
                PATH=str(ROOT / "artifacts/rust/toolchain/bin") + os.pathsep + os.environ["PATH"])


def extract(gui, name, row, bundle, *, destination=None):
    expected = PINS["packages"][name]
    stem = name + "-" + expected["version"]
    archive = warm.eframe_source.original_archive(dict(crate=stem, archiveSha256=expected["archiveSha256"]))
    if (row["version"], row["checksum"]) != (expected["version"], expected["archiveSha256"]):
        raise ValueError("Diagnostic package differs from the retained lock")
    bundle[stem + ".crate"] = archive
    package = gui / (LIBS[name] if destination is None else destination)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as source:
        names = [m.name.removeprefix(stem + "/") for m in source if m.isfile() and m.name.startswith(stem + "/")]
        if any(not m.isfile() or not m.name.startswith(stem + "/") for m in source) or len(names) != len(set(names)):
            raise ValueError("Unexpected source archive member")
        warm.source_profile.take_files(source, stem, names, package)
    metadata = tomllib.loads((package / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    vcs = package / ".cargo_vcs_info.json"
    if (metadata["name"], metadata["version"], metadata["license"], metadata["repository"]) != (
            name, expected["version"], expected["license"], expected["repository"]) or (
            json.loads(vcs.read_bytes()) if vcs.exists() else None) != expected["vcs"]:
        raise ValueError("Unreviewed package identity or license")
    for notice, digest in expected["noticeSha256"].items():
        bundle[f"notices/{name}/{notice}"] = checked(package / notice, digest)


def verify_compiler_sources(read, trees, *, pins=PINS):
    files = {"Cargo.lock", *(f"manifests/{name}/Cargo.toml" for name in (*LIBS, "native-gui-assessment"))}
    if (set(pins["compilerFiles"]) != files or trees != pins["compilerTrees"]
            or any(sha256(read(name)).hexdigest() != pins["compilerFiles"][name] for name in files)):
        raise ValueError("The reconstructed compiler manifests, lock or library trees differ")


def stage(out):
    gui = warm.stage(out / "project")
    ordinary_bundle = out / "ordinary-source.zip"
    ordinary = warm.eframe_source.source_bundle(gui, ordinary_bundle)
    pre = {p.name: sha(p) for p in [*sorted((gui / "src").glob("*.rs")), gui / "src/tray-icon.argb"]}
    original_lock = tomllib.loads((gui / "Cargo.lock").read_text(encoding="utf-8"))
    selected = warm.feature_rows(gui / "Cargo.toml", TARGET, environment(out))
    patch = checked(HERE / "probes.patch", PINS["sourcePatchSha256"])
    bundle = {"sources.json": (HERE / "sources.json").read_bytes(), "probes.patch": patch,
              "prepare.py": Path(__file__).read_bytes(), "trace.rs": (HERE / "trace.rs").read_bytes(),
              "window_messages.rs": (HERE / "window_messages.rs").read_bytes(),
              "ordinary-source.zip": ordinary_bundle.read_bytes(),
              "notices/ifw-frame-timing/LICENSE": (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")}
    for name in PINS["packages"]:
        row, = [r for r in original_lock["package"] if r["name"] == name and r["version"] == PINS["packages"][name]["version"]]
        extract(gui, name, row, bundle)
    # The egui-wgpu archive omits notices. Use the two qualified upstream license files.
    ef = json.loads(warm.eframe_source.PINS.read_bytes())
    for path, item in ef["notices"].items():
        if path.startswith("eframe/"):
            bundle["notices/egui-wgpu/" + Path(path).name] = checked(ROOT / item["path"], item["sha256"])
    trace = gui / LIBS[TIMING]
    (trace / "src").mkdir(parents=True)
    shutil.copyfile(HERE / "trace.rs", trace / "src/lib.rs")
    shutil.copyfile(HERE / "window_messages.rs", trace / "src/window_messages.rs")
    (trace / "Cargo.toml").write_text(
        '[package]\nname = "ifw-frame-timing"\nversion = "0.0.0"\nedition = "2024"\nlicense = "AGPL-3.0-only"\n',
        encoding="ascii", newline="\n")
    manifests = {**{name: gui / path for name, path in LIBS.items() if name != TIMING},
                 "native-gui-assessment": gui}
    manifest = gui / "Cargo.toml"
    text = manifest.read_text(encoding="utf-8")
    if text.count("[workspace]\n") != 1:
        raise ValueError("Unexpected diagnostic workspace")
    manifest.write_text(text.replace("[workspace]\n", '[workspace]\nexclude = ["artifacts/cost/ifw-frame-timing"]\n'),
                        encoding="utf-8", newline="\n")
    for name, folder in manifests.items():
        relative = os.path.relpath(trace, folder).replace(os.sep, "/")
        with (folder / "Cargo.toml").open("a", encoding="utf-8", newline="\n") as f:
            f.write(f'\n# Modified for the isolated Windows dispatch diagnosis.\n[dependencies.{TIMING}]\npath = "{relative}"\n')
            if name == "native-gui-assessment":
                for package in PINS["packages"]:
                    f.write(f'\n[patch.crates-io.{package}]\npath = "{LIBS[package].as_posix()}"\n')
    for path, row in PINS["patchSources"].items():
        checked(gui / path, row["before"])
    git_env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.resolve()))
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        git_env.pop(key, None)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--whitespace=error", "-"],
                   input=patch, cwd=gui, check=True, env=git_env)
    for path, row in PINS["patchSources"].items():
        checked(gui / path, row["after"])
    subprocess.run(["cargo", "update", "--offline", "-p", "egui-wgpu@0.37.0", "-p", "wgpu-hal@30.0.2"],
                   cwd=gui, env=environment(out), check=True)
    rows = warm.feature_rows(gui / "Cargo.toml", TARGET, environment(out))
    if set(rows) != set(selected) | {(TIMING, "0.0.0", ())}:
        raise ValueError("A reviewed external package or feature changed")
    expected_lock = {r["name"] + "@" + r["version"]: r for r in original_lock["package"]}
    for name in manifests:
        row, = [r for r in original_lock["package"] if r["name"] == name]
        row["dependencies"] = sorted([*row["dependencies"], TIMING])
        if name in PINS["packages"]:
            del row["source"], row["checksum"]
    expected_lock[TIMING + "@0.0.0"] = dict(name=TIMING, version="0.0.0")
    final_lock = tomllib.loads((gui / "Cargo.lock").read_text(encoding="utf-8"))
    if {r["name"] + "@" + r["version"]:r for r in final_lock["package"]} != expected_lock:
        raise ValueError("The diagnostic lock changed outside the measured packages")
    for name, folder in {**manifests, TIMING:trace}.items():
        bundle[f"manifests/{name}/Cargo.toml"] = (folder / "Cargo.toml").read_bytes()
    bundle["Cargo.lock"] = (gui / "Cargo.lock").read_bytes()
    trees = {name: warm.source_profile.tree_info(gui / path) for name, path in LIBS.items()}
    verify_compiler_sources(bundle.__getitem__, trees)
    sources = dict(ordinarySource=ordinary["archiveSha256"], ordinaryInputs=pre,
                   archive=warm.eframe_source.write_archive(out / "source.zip", bundle),
                   trees=trees,
                   application={p.name:sha(p) for p in (gui / "src").iterdir() if p.is_file()})
    return gui, rows, sources


def compiler_units(messages, gui, rows, build):
    if not messages or messages[-1] != {"reason":"build-finished", "success":True} or sum(
            m["reason"] == "build-finished" for m in messages) != 1:
        raise ValueError("Incomplete diagnostic compiler stream")
    units = [m for m in messages if m["reason"] == "compiler-artifact"]
    metadata = json.loads(subprocess.check_output(["cargo", "metadata", "--frozen", "--format-version", "1",
                                                 "--filter-platform", TARGET], cwd=gui, env=environment(gui)))
    packages = {p["id"]:p for p in metadata["packages"]}
    observed = set()
    for m in units:
        p = packages[m["package_id"]]
        if Path(p["manifest_path"]).resolve() != Path(m["manifest_path"]).resolve():
            raise ValueError("Compiler manifest differs from the frozen package")
        observed.add((p["name"], p["version"], tuple(sorted(m["features"]))))
    if observed != set(rows):
        raise ValueError("The compiled features differ from the reviewed normal/build graph")
    build = build.resolve()
    libraries = {}
    for name, path in LIBS.items():
        m, = [m for m in units if m["target"]["kind"] == ["lib"] and m["target"]["name"] == name.replace("-", "_")]
        if (Path(m["manifest_path"]).resolve() != (gui / path / "Cargo.toml").resolve()
                or Path(m["target"]["src_path"]).resolve() != (gui / path / "src/lib.rs").resolve()
                or not m["package_id"].startswith("path+file:")):
            raise ValueError("The compiler selected a different measured crate")
        files = [Path(f).resolve() for f in m["filenames"]]
        if not files or len(set(files)) != len(files) or any(not f.is_relative_to(build) or not f.is_file() for f in files):
            raise ValueError("A measured compiler output falls outside the private target directory")
        libraries[name] = dict(manifest=(path / "Cargo.toml").as_posix(), crateRoot=(path / "src/lib.rs").as_posix(),
                               features=sorted(m["features"]), outputs={f.relative_to(build).as_posix(): sha(f) for f in files})

    return libraries


def paired_inputs(base, gui, sources):
    paired = json.loads((base / "build.json").read_bytes())
    if (paired["compilerInputs"] != sources["ordinaryInputs"] or paired["eframeSource"]["archiveSha256"] != sources["ordinarySource"]
            or sha(base / "eframe-source.zip") != sources["ordinarySource"] or sha(base / "compiler.jsonl") != paired["compilerEvidence"]["sha256"]):
        raise ValueError("The measured source does not reconstruct the paired ordinary build")
    approved = warm.source_profile.prepare(fetch=False, registry=ROOT / "artifacts/rust/assessment-cache/registry")
    if (any(warm.source_profile.tree_info(gui / "artifacts/text" / name) != info for name, info in approved["trees"].items())
            or paired["baseFonts"] != {p.name:sha(p) for p in sorted((ROOT / "rust/assets/fonts").glob("*.ttf"))}
            or paired["fallbackFonts"] != {name:asset["sha256"] for name, asset in approved["fonts"].items()}):
        raise ValueError("The original text sources or fonts differ from the paired native build")
    return paired


def build(out, base, metadata):
    if metadata["target"] != TARGET:
        raise ValueError("The measured regression concerns the native x64 WARP subject")
    gui, rows, sources = stage(out)
    paired = paired_inputs(base, gui, sources)
    native = subprocess.check_output([sys.executable, str(QA / "check-toolchain.py"), TARGET], env=environment(out), text=True)
    if native.strip() != paired["nativeCompiler"]:
        raise ValueError("Different native compiler")
    stream = out / "compiler.jsonl"
    with stream.open("wb") as log:
        subprocess.run(["cargo", "build", "--release", "--frozen", "--message-format=json-render-diagnostics"],
                       cwd=gui, env=environment(out), stdout=log, check=True)
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    libs = compiler_units(messages, gui, rows, out / "build")
    exe = out / "build/release/native-gui-assessment.exe"
    application = warm.application_artifact(messages, gui, exe)
    if application["sha256"] == paired["binary"] or any(
            warm.source_profile.tree_info(gui / path) != sources["trees"][n] for n, path in LIBS.items()):
        raise ValueError("The diagnostic PE or its compiler inputs are unexpected")
    receipt = dict(source=sources, compilerSha256=sha(stream), application=application, libraries=libs,
                 pairedBuildSha256=sha(base / "build.json"), pairedBinary=paired["binary"],
                 pairedCompiler=paired["compilerEvidence"]["sha256"], nativeCompiler=native.strip())
    (out / "diagnostic-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return exe


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reconstruct the frame diagnosis from the checked-out sources and offline cache")
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    output = options.output.resolve()
    output.mkdir()
    _, _, evidence = stage(output)
    print(json.dumps(evidence, indent=2))
