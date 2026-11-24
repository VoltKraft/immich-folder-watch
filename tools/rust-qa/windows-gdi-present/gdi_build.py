"""Rebuild the retained egui application with the isolated Windows x64 GDI output."""
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows-frame-cost"))
import prepare

warm = prepare.warm
sha = prepare.sha
PRESENTER = Path("artifacts/gdi/egui-wgpu")


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*") if p.is_file()}


def stage(out):
    gui = warm.stage(out / "project")
    original = warm.eframe_source.source_bundle(gui, out / "ordinary-source.zip")
    members = {"ordinary-source.zip": (out / "ordinary-source.zip").read_bytes()}
    lock = gui / "Cargo.lock"
    retained_lock = tomllib.loads(lock.read_text(encoding="utf-8"))
    renderer, = [row for row in retained_lock["package"] if row["name"] == "egui-wgpu"]
    prepare.extract(gui, "egui-wgpu", renderer, members, destination=PRESENTER)
    for name, notice in original["pins"]["notices"].items():
        if name.startswith("eframe/"):
            members["notices/egui-wgpu/" + Path(name).name] = prepare.checked(prepare.ROOT / notice["path"], notice["sha256"])
    members["notices/gdi-present/LICENSE"] = (prepare.ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")

    package = gui / PRESENTER
    env = prepare.environment(out)
    manifest = gui / "Cargo.toml"
    selected = warm.feature_rows(manifest, prepare.TARGET, env)
    ordinary_app = inventory(gui / "src")
    expected = inventory(package)
    pins = json.loads((HERE / "renderer-inputs.json").read_bytes())
    for name, (before, after) in pins["files"].items():
        relative = Path(name).relative_to(PRESENTER).as_posix()
        if expected.get(relative) != before:
            raise ValueError(f"Different original renderer input: {relative}")
        expected[relative] = after
    patch = prepare.checked(HERE / "offscreen.patch", pins["patchSha256"])
    git_env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    git_env["GIT_CEILING_DIRECTORIES"] = str(out.resolve())
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero", "--whitespace=error", "-"],
                   cwd=gui, env=git_env, input=patch, check=True)
    for name, item in pins["copies"].items():
        relative = Path(name).relative_to(PRESENTER).as_posix()
        if relative in expected or (gui / name).exists():
            raise ValueError("The GDI module would replace an existing renderer input")
        data = prepare.checked(HERE / item["source"], item["sha256"])
        (gui / name).write_bytes(data)
        members[item["source"]] = data
        expected[relative] = item["sha256"]
    if inventory(package) != expected or inventory(gui / "src") != ordinary_app:
        raise ValueError("Unexpected change to the retained application or renderer source")
    for path, pins_key in ((warm.eframe_source.PACKAGE, "pins"), (warm.eframe_source.WINIT_PACKAGE, "winitPins")):
        if warm.source_profile.tree_info(gui / path) != original[pins_key]["compilerTree"]:
            raise ValueError("The GDI presenter changed a paired window or input library")
    with manifest.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write('\n[patch.crates-io.egui-wgpu]\npath = "artifacts/gdi/egui-wgpu"\n')
    subprocess.run(["cargo", "update", "--offline", "-p", "egui-wgpu@" + renderer["version"]], env=env, cwd=gui, check=True)
    if (renderer.pop("source") != "registry+https://github.com/rust-lang/crates.io-index"
            or renderer.pop("checksum") != prepare.PINS["packages"]["egui-wgpu"]["archiveSha256"]
            or tomllib.loads(lock.read_text(encoding="utf-8")) != retained_lock
            or warm.feature_rows(manifest, prepare.TARGET, env) != selected):
        raise ValueError("The GDI presenter changed the reviewed Cargo graph")
    members.update({"renderer-inputs.json": (HERE / "renderer-inputs.json").read_bytes(),
                    "gdi_build.py": Path(__file__).read_bytes(), "offscreen.patch": patch,
                    "compiled/Cargo.toml": manifest.read_bytes(), "compiled/Cargo.lock": lock.read_bytes()})
    for name in (*pins["files"], *pins["copies"]):
        members["compiled/" + name] = (gui / name).read_bytes()
    sources = dict(ordinarySource=original["archiveSha256"], ordinaryApp=ordinary_app, rendererTree=warm.source_profile.tree_info(package),
                   originalPackage=prepare.PINS["packages"]["egui-wgpu"], lock=sha(lock),
                   members={name: sha256(data).hexdigest() for name, data in members.items()},
                   archive=warm.eframe_source.write_archive(out / "source.zip", members))
    return gui, selected, sources


def compilation(stream, *, gdi):
    """Read original native Cargo messages on either OS, independent of the hosted build path."""
    from collections import Counter

    rows = [json.loads(line) for line in stream.read_bytes().splitlines()]
    finished = {"reason": "build-finished", "success": True}
    if not rows or rows[-1] != finished or rows.count(finished) != 1:
        raise ValueError("Incomplete native GUI compiler stream")
    units = [item for item in rows if item["reason"] == "compiler-artifact"]
    app, = [item for item in units if item["target"]["name"] == "native-gui-assessment" and item["target"]["kind"] == ["bin"]]
    gui = PureWindowsPath(app["manifest_path"]).parent
    exe = PureWindowsPath(app["executable"])
    if (gui.name != "gui" or gui.parts[-3:] != ("tools", "rust-qa", "gui")
            or PureWindowsPath(app["target"]["src_path"]) != gui / "src/main.rs" or not app["package_id"].startswith("path+file:")
            or exe.name != "native-gui-assessment.exe" or exe.parent.name != "release"
            or [PureWindowsPath(f) for f in app["filenames"]].count(exe) != 1):
        raise ValueError("Unexpected linked GUI in the original Windows build")
    local = {"native-gui-assessment": gui, "desktop-lifecycle": gui.parents[2] / "rust/crates/desktop-lifecycle",
             "eframe": gui / warm.eframe_source.PACKAGE, "winit": gui / warm.eframe_source.WINIT_PACKAGE,
             **{n: gui / "artifacts/text" / n for n in ("egui", "epaint", "unicode-bidi")}}
    if gdi:
        local["egui-wgpu"] = gui / PRESENTER
    signatures = Counter()
    for unit in units:
        origin, suffix = unit["package_id"].rsplit("#", 1)
        name, version = suffix.split("@", 1) if "@" in suffix else (PurePosixPath(unquote(origin)).name, suffix)
        if name in local:
            if not origin.startswith("path+file:") or PureWindowsPath(unit["manifest_path"]) != local[name] / "Cargo.toml":
                raise ValueError(f"The Windows compiler selected another source for {name}")
        elif origin != "registry+https://github.com/rust-lang/crates.io-index":
            raise ValueError(f"Unexpected compiler package origin for {name}")
        target = unit["target"]
        signatures[name, version, target["name"], tuple(target["kind"]), tuple(sorted(unit["features"]))] += 1
    return gui, exe, units, signatures


def verify(out, record):
    from inputs import recorder
    from readback import release_outputs

    base = out.parent
    receipt = json.loads((out / "gdi-build.json").read_bytes())
    ordinary = json.loads((base / "build.json").read_bytes())
    if record["target"] != prepare.TARGET or any(record[key] != receipt[key] for key in ("target", "revision", "run", "attempt")):
        raise ValueError("Mismatched GDI build source or target")
    if (receipt["target"] != ordinary["target"] or receipt["revision"] != ordinary["revision"]
            or receipt["ordinaryBuild"] != sha(base / "build.json") or receipt["ordinaryBuild"] != record["buildReceipt"]
            or receipt["ordinaryBinary"] != ordinary["binary"] or receipt["ordinaryBinary"] != record["pairedBinary"]
            or receipt["nativeCompiler"] != ordinary["nativeCompiler"] or sha(out / "gdi-build.json") != record["gdiBuild"]
            or sha(out / "compiler.jsonl") != receipt["compiler"] or sha(base / "compiler.jsonl") != ordinary["compilerEvidence"]["sha256"]
            or record["binary"] != receipt["application"]["sha256"] or record["binary"] != sha(out / "gdi.exe")
            or record["binary"] == record["pairedBinary"] or recorder.pe_machine(out / "gdi.exe") != 0x8664
            or receipt["sources"]["ordinarySource"] != sha(base / "eframe-source.zip")
            or receipt["sources"]["ordinaryApp"] != ordinary["compilerInputs"]):
        raise ValueError("Different native PE, compiler inputs or ordinary build")
    with tempfile.TemporaryDirectory(prefix="ifwgdi-") as work:
        _, _, sources = stage(Path(work))
    if sources != receipt["sources"] or sources["archive"] != sha(out / "source.zip"):
        raise ValueError("The archived GDI source failed offline reconstruction")
    _, _, _, base_units = compilation(base / "compiler.jsonl", gdi=False)
    gui, exe, units, observed = compilation(out / "compiler.jsonl", gdi=True)
    if observed != base_units:
        raise ValueError("The two native GUI builds selected different compiler units or features")
    for path in (PRESENTER, warm.eframe_source.PACKAGE, warm.eframe_source.WINIT_PACKAGE):
        crate_name = path.name.replace("-", "_")
        library = receipt["libraries"][path.name]
        unit, = [u for u in units if u["target"]["name"] == crate_name and u["target"]["kind"] == ["lib"]]
        if (PureWindowsPath(unit["target"]["src_path"]) != gui / path / "src/lib.rs"
                or sorted(unit["features"]) != sorted(library["features"])
                or not release_outputs([PureWindowsPath(f) for f in unit["filenames"]], library["outputs"], exe, crate_name)):
            raise ValueError(f"Native GDI compiler did not select the archived {crate_name} library")
    return dict(archive=sources["archive"], binary=record["binary"], compilerUnits=len(units), pairedBinary=record["pairedBinary"])


def build(out, base, record):
    if record["target"] != prepare.TARGET:
        raise ValueError("The GDI presentation comparison needs the native Windows x64 WARP target")
    ordinary = json.loads((base / "build.json").read_bytes())
    gui, selected, sources = stage(out)
    if (ordinary["revision"] != record["revision"] or sha(base / "build.json") != record["buildReceipt"]
            or ordinary["binary"] != record["binary"] or ordinary["compilerInputs"] != sources["ordinaryApp"]
            or sha(base / "compiler.jsonl") != ordinary["compilerEvidence"]["sha256"]
            or ordinary["eframeSource"]["archiveSha256"] != sources["ordinarySource"]
            or sha(base / "eframe-source.zip") != sources["ordinarySource"]):
        raise ValueError("The GDI subject differs from its paired ordinary native build")
    env = prepare.environment(out)
    approved = warm.source_profile.prepare(fetch=False, registry=prepare.ROOT / "artifacts/rust/assessment-cache/registry")
    if (any(warm.source_profile.tree_info(gui / "artifacts/text" / name) != info for name, info in approved["trees"].items())
            or {p.name: sha(p) for p in (prepare.ROOT / "rust/assets/fonts").glob("*.ttf")} != ordinary["baseFonts"]
            or {name: item["sha256"] for name, item in approved["fonts"].items()} != ordinary["fallbackFonts"]):
        raise ValueError("Different font assets or text engine in the native GDI subject")
    native = subprocess.check_output([sys.executable, str(prepare.QA / "check-toolchain.py"), prepare.TARGET],
                                     env=env, text=True).strip()
    if native != ordinary["nativeCompiler"]:
        raise ValueError("The two native GUI builds use different compilers")
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--release", "--frozen", "--message-format=json-render-diagnostics"],
                       env=env, cwd=gui, stdout=log, check=True)
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    graph = warm.compiler_graph(messages, gui, selected, extra_local={"egui-wgpu": gui / PRESENTER})
    libraries = {}
    for path in (PRESENTER, warm.eframe_source.PACKAGE, warm.eframe_source.WINIT_PACKAGE):
        flags, = [flags for name, _, flags in selected if name == path.name]
        libraries[path.name] = warm.compiled_library(messages, gui, out / "build", path, flags)
    binary = out / "build/release/native-gui-assessment.exe"
    application = warm.application_artifact(messages, gui, binary)
    if (application["sha256"] == ordinary["binary"] or inventory(gui / "src") != sources["ordinaryApp"]
            or warm.source_profile.tree_info(gui / PRESENTER) != sources["rendererTree"]):
        raise ValueError("The native build did not produce the selected distinct GUI")
    shutil.copyfile(binary, out / "gdi.exe")
    receipt = dict(revision=record["revision"], run=record["run"], attempt=record["attempt"], target=prepare.TARGET,
                   nativeCompiler=native, ordinaryBuild=record["buildReceipt"], ordinaryBinary=record["binary"],
                   graph=graph, sources=sources, compiler=sha(stream), libraries=libraries, application=application)
    (out / "gdi-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    record.update(gdiBuild=sha(out / "gdi-build.json"), pairedBinary=record["binary"], binary=application["sha256"])
    return out / "gdi.exe"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reconstruct the offscreen renderer from the local reviewed Cargo cache")
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    output.mkdir()
    _, _, source = stage(output)
    print(source["archive"])
