"""Reconstruct the isolated Windows x64 CPU painter and bind its executable to native Cargo output."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows-gdi-present"))
import gdi_build as gdi

import upstream

prepare, warm, sha = gdi.prepare, gdi.warm, gdi.sha
CACHE = prepare.ROOT / "artifacts/rust/cpu-paint-cache"
PINS = json.loads(upstream.PINS.read_bytes())["packages"]
LOCAL = {name: Path("artifacts/cpu") / name for name in PINS}
LIBS = {"hdrshot-egui-backend": ("egui_software_backend", "lib", ("default", "std")),
        "constify": ("constify", "proc-macro", ()), "strength_reduce": ("strength_reduce", "lib", ())}
DEPENDENCIES = {"hdrshot-egui-backend": ["ahash", "constify", "egui", "strength_reduce"],
                "constify": ["proc-macro2", "quote", "syn 2.0.119"]}
SYN = ("syn", "2.0.119")


def check_lock(before, after):
    renderer, = [p for p in before["package"] if p["name"] == "egui-wgpu"]
    if (renderer.pop("checksum") != prepare.PINS["packages"]["egui-wgpu"]["archiveSha256"]
            or renderer.pop("source") != "registry+https://github.com/rust-lang/crates.io-index"):
        raise ValueError("The paired renderer is not the reviewed registry source")
    renderer["dependencies"] = sorted([*renderer["dependencies"], "hdrshot-egui-backend"])
    for name, pin in PINS.items():
        row = {"name": name, "version": pin["version"]}
        if name in DEPENDENCIES:
            row["dependencies"] = DEPENDENCIES[name]
        before["package"].append(row)
    before["package"].sort(key=lambda p: (p["name"], p["version"]))
    after["package"].sort(key=lambda p: (p["name"], p["version"]))
    if before != after:
        raise ValueError("Unreviewed change in the CPU painter lockfile")


def check_features(before, after):
    # constify uses syn's syntax-tree Debug implementations.
    def equivalent(rows):
        return {(n, v, tuple(f for f in flags if (n, v, f) != (*SYN, "extra-traits")))
                for n, v, flags in rows if n not in LOCAL}
    added = {(n, v, flags) for n, v, flags in after if n in LOCAL}
    if (equivalent(before) != equivalent(after)
            or added != {(name, PINS[name]["version"], lib[2]) for name, lib in LIBS.items()}
            or not any((n, v) == SYN and "extra-traits" in flags for n, v, flags in after)):
        raise ValueError("The CPU painter selected an unreviewed native crate feature set")


def stage(out, cache=CACHE):
    inputs = upstream.prepare(cache)
    gui = warm.stage(out / "project")
    original = warm.eframe_source.source_bundle(gui, out / "ordinary-source.zip")
    members = {"ordinary-source.zip": (out / "ordinary-source.zip").read_bytes(),
               "upstream-receipt.json": inputs.receipt.read_bytes()}
    manifest, lock = gui / "Cargo.toml", gui / "Cargo.lock"
    before = tomllib.loads(lock.read_text(encoding="utf-8"))
    env = prepare.environment(out)
    previous = warm.feature_rows(manifest, prepare.TARGET, env)
    renderer, = [p for p in before["package"] if p["name"] == "egui-wgpu"]
    package = gui / gdi.PRESENTER
    prepare.extract(gui, "egui-wgpu", renderer, members, destination=gdi.PRESENTER)
    for key, notice in original["pins"]["notices"].items():
        if key.startswith("eframe/"):
            members["notices/egui-wgpu/" + Path(key).name] = prepare.checked(prepare.ROOT / notice["path"], notice["sha256"])
    pins = json.loads((HERE / "renderer-inputs.json").read_bytes())
    ordinary_app, patch = gdi.apply_renderer(gui, out, package, members, pins, HERE / "cpu-paint.patch")
    for name, source in inputs.sources.items():
        shutil.copytree(source, gui / LOCAL[name])
        pin = PINS[name]
        archive = f"{name}-{pin['version']}.crate"
        members["archives/" + archive] = upstream.checked(cache / "archives" / archive, pin["sha256"], pin["bytes"])
    for notice in inputs.notices.iterdir():
        members["notices/cpu/" + notice.name] = notice.read_bytes()
    members["notices/first-party/LICENSE"] = (prepare.ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    with (package / "Cargo.toml").open("a", encoding="utf-8", newline="\n") as file:
        file.write('\n[target.\'cfg(all(target_os = "windows", target_arch = "x86_64"))\'.dependencies.cpu_painter]\n'
                   'package = "hdrshot-egui-backend"\nversion = "=0.2.0"\npath = "../../cpu/hdrshot-egui-backend"\n')
    with manifest.open("a", encoding="utf-8", newline="\n") as file:
        for name, path in (("egui-wgpu", gdi.PRESENTER), ("constify", LOCAL["constify"]), ("strength_reduce", LOCAL["strength_reduce"])):
            file.write(f'\n[patch.crates-io.{name}]\npath = "{path.as_posix()}"\n')
    subprocess.run(["cargo", "update", "--offline", "-p", "egui-wgpu@" + renderer["version"]], cwd=gui, env=env, check=True)
    check_lock(before, tomllib.loads(lock.read_text(encoding="utf-8")))
    selected = warm.feature_rows(manifest, prepare.TARGET, env)
    check_features(previous, selected)
    for path in (lock, manifest, package / "Cargo.toml", *(gui / n for n in (*pins["files"], *pins["copies"]))):
        members["compiled/" + path.relative_to(gui).as_posix()] = path.read_bytes()
    for path in (HERE / "renderer-inputs.json", HERE / "upstream.json", HERE / "upstream.py", Path(__file__),
                 Path(gdi.__file__), Path(prepare.__file__), HERE.parent / "yaml/prepare.py"):
        members["tools/" + path.relative_to(HERE.parent).as_posix()] = path.read_bytes()
    members["cpu-paint.patch"] = patch
    sources = dict(ordinarySource=original["archiveSha256"], ordinaryApp=ordinary_app, upstream=sha(inputs.receipt),
                   lock=sha(lock), trees={n: gdi.inventory(gui / p) for n, p in {"egui-wgpu": gdi.PRESENTER, **LOCAL}.items()},
                   members={name: sha256(data).hexdigest() for name, data in members.items()},
                   archive=warm.eframe_source.write_archive(out / "source.zip", members))
    return gui, selected, sources


def library_units(gui, units, exe):
    """Use original Windows paths for the procedural macro and for both linked CPU libraries."""
    result = {}
    for name, (crate, kind, flags) in LIBS.items():
        directory = gui / LOCAL[name]
        unit, = [u for u in units if PureWindowsPath(u["manifest_path"]) == directory / "Cargo.toml"]
        files = [PureWindowsPath(f) for f in unit["filenames"]]
        suffix = ".dll" if kind == "proc-macro" else ".rlib"
        primary = [p for p in files if p.suffix == suffix]
        if (unit["target"]["name"] != crate or unit["target"]["kind"] != [kind] or tuple(sorted(unit["features"])) != flags
                or PureWindowsPath(unit["target"]["src_path"]) != directory / "src/lib.rs" or len(primary) != 1):
            raise ValueError(f"Unexpected native {name} compiler outputs")
        artifact, = primary
        prefix = crate if kind == "proc-macro" else "lib" + crate
        match = re.fullmatch(re.escape(prefix) + r"-([a-f0-9]{16})", artifact.stem)
        extensions = (".dll", ".dll.lib", ".dll.exp", ".pdb") if kind == "proc-macro" else (".rlib", ".rmeta")
        if (not match or artifact.parent not in (exe.parent / "deps", exe.parent / "build" / name / match[1] / "out")
                or len(set(files)) != len(files) or any(p.parent != artifact.parent for p in files)
                or not {p.name for p in files} <= {artifact.stem + ext for ext in extensions}):
            raise ValueError(f"Unexpected native {name} compiler output location")
        result[name] = files
    return result


def compare_units(ordinary, candidate):
    def common(units):
        rows = Counter()
        for (name, version, target, kind, features), count in units.items():
            if name not in LOCAL:
                flags = tuple(f for f in features if (name, version, f) != (*SYN, "extra-traits"))
                rows[name, version, target, kind, flags] += count
        return rows
    added = {key: n for key, n in candidate.items() if key[0] in LOCAL}
    expected = {(name, PINS[name]["version"], crate, (kind,), flags): 1 for name, (crate, kind, flags) in LIBS.items()}
    if common(ordinary) != common(candidate) or added != expected:
        raise ValueError("Native Cargo builds differ outside the three audited libraries and syn feature")


def build(out, base, record):
    if record["target"] != prepare.TARGET:
        raise ValueError("CPU painting is scoped to native Windows x64")
    ordinary = json.loads((base / "build.json").read_bytes())
    gui, selected, sources = stage(out)
    env, native = gdi.native_build_inputs(out, base, record, ordinary, gui, sources)
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--frozen", "--release", "--message-format=json-render-diagnostics"],
                       env=env, cwd=gui, stdout=log, check=True)
    messages = [json.loads(line) for line in stream.read_bytes().splitlines()]
    paths = {"egui-wgpu": gdi.PRESENTER, **LOCAL}
    graph = warm.compiler_graph(messages, gui, selected, extra_local={name: gui / path for name, path in paths.items()})
    binary = out / "build/release/native-gui-assessment.exe"
    app = warm.application_artifact(messages, gui, binary)
    native_gui, exe, units, signatures = gdi.compilation(stream, gdi=True, extra_local=LOCAL)
    compare_units(gdi.compilation(base / "compiler.jsonl", gdi=False)[3], signatures)
    lib_outputs = library_units(native_gui, units, exe)
    members = {p.relative_to(exe.parent).as_posix(): Path(p).read_bytes() for files in lib_outputs.values() for p in files}
    libs = {name: [p.relative_to(exe.parent).as_posix() for p in files] for name, files in lib_outputs.items()}
    evidence = warm.eframe_source.write_archive(out / "cpu-libraries.zip", members)
    if (sources["ordinaryApp"] != gdi.inventory(gui / "src") or app["sha256"] == ordinary["binary"]
            or any(gdi.inventory(gui / p) != sources["trees"][n] for n, p in paths.items())):
        raise ValueError("Native build changed the staged GUI or renderer sources")
    shutil.copyfile(binary, out / "cpu.exe")
    receipt = {k: record[k] for k in ("revision", "run", "attempt", "target")}
    receipt.update(nativeCompiler=native, ordinaryBuild=record["buildReceipt"], ordinaryBinary=record["binary"],
                   compiler=sha(stream), graph=graph, libraries=libs, libraryArchive=evidence, application=app, sources=sources)
    (out / "cpu-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    record.update(cpuBuild=sha(out / "cpu-build.json"), pairedBinary=record["binary"], binary=app["sha256"])
    return out / "cpu.exe"


def verify(out, record):
    from inputs import recorder
    base = out.parent
    receipt = json.loads((out / "cpu-build.json").read_bytes())
    ordinary = json.loads((base / "build.json").read_bytes())
    if (record["target"] != prepare.TARGET or any(receipt[k] != record[k] for k in ("revision", "run", "attempt", "target"))
            or any(ordinary[k] != record[k] for k in ("revision", "target"))
            or sha(out / "cpu-build.json") != record["cpuBuild"] or sha(out / "compiler.jsonl") != receipt["compiler"]
            or sha(base / "compiler.jsonl") != ordinary["compilerEvidence"]["sha256"]
            or sha(base / "build.json") != receipt["ordinaryBuild"] or receipt["ordinaryBuild"] != record["buildReceipt"]
            or ordinary["nativeCompiler"] != receipt["nativeCompiler"]
            or not ordinary["binary"] == record["pairedBinary"] == receipt["ordinaryBinary"]
            or not sha(out / "cpu.exe") == record["binary"] == receipt["application"]["sha256"]
            or record["binary"] == ordinary["binary"] or recorder.pe_machine(out / "cpu.exe") != 0x8664
            or ordinary["compilerInputs"] != receipt["sources"]["ordinaryApp"]
            or sha(base / "eframe-source.zip") != receipt["sources"]["ordinarySource"]
            or sha(out / "source.zip") != receipt["sources"]["archive"]):
        raise ValueError("Mismatched native source archive, executable, compiler, host or paired build")
    with TemporaryDirectory(prefix="ifwcpu-") as tmp:
        root = Path(tmp)
        archives = root / "cache/archives"
        archives.mkdir(parents=True)
        with ZipFile(out / "source.zip") as bundle:
            for name, pin in PINS.items():
                filename = f"{name}-{pin['version']}.crate"
                item = bundle.getinfo("archives/" + filename)
                if item.file_size != pin["bytes"]:
                    raise ValueError("Native source archive contains a different crate")
                (archives / filename).write_bytes(bundle.read(item))
        _, selected, sources = stage(root, archives.parent)
    gui, exe, units, signatures = gdi.compilation(out / "compiler.jsonl", gdi=True, extra_local=LOCAL)
    compare_units(gdi.compilation(base / "compiler.jsonl", gdi=False)[3], signatures)
    observed = {(name, version, features) for name, version, _, _, features in signatures}
    graph = dict(units=len(units), featureSets=len(observed), packages=len({(n, v) for n, v, _ in observed}))
    files = library_units(gui, units, exe)
    paths = {name: [p.relative_to(exe.parent).as_posix() for p in group] for name, group in files.items()}
    archive = out / "cpu-libraries.zip"
    with ZipFile(archive) as bundle:
        if sha(archive) != receipt["libraryArchive"] or sorted(bundle.namelist()) != sorted(p for group in paths.values() for p in group):
            raise ValueError("Different archived native CPU libraries")
    if (sources != receipt["sources"] or paths != receipt["libraries"] or observed != set(selected)
            or receipt["graph"] != graph):
        raise ValueError("Detached compiler or source reconstruction disagrees with the build receipt")
    return dict(binary=record["binary"], pairedBinary=record["pairedBinary"], archive=sources["archive"], compilerUnits=len(units))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir()
    print(stage(destination)[2]["archive"])
