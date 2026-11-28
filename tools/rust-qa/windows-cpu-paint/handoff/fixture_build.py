"""Build one extra Cargo example against the actual native CPU renderer's compiled library graph."""
from collections import Counter
from hashlib import sha256
import json
import re
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cpu_build

gdi, prepare, sha = cpu_build.gdi, cpu_build.prepare, cpu_build.sha
NAME = "texture_handoff"


def read(path):
    return json.loads(path.read_bytes())


def example_main(original):
    # Retain byte-for-byte replay for captures made with the original pipe reader.
    current_open = b"                Ok(b'O') => Command::Open,"
    previous_open = b"                Ok(()) if next[0] == b'O' => Command::Open,"
    if original.count(current_open) + original.count(previous_open) != 1:
        raise ValueError("The private example requires one Open command in its input loop")
    if current_open in original:
        open_case = current_open
        advance = (b"                Ok(byte @ (b'1' | b'2')) if !observe_ime => {\n"
                   b"                    handoff_scene::advance(byte - b'0');\n")
    else:
        open_case = previous_open
        advance = (b"                Ok(()) if matches!(next[0], b'1' | b'2') => {\n"
                   b"                    handoff_scene::advance(next[0] - b'0');\n")
    original, painted = re.subn(rb"^( +)let language = ui\.add\(button\);$",
                                rb"\g<0>\n\1handoff_scene::paint(ui);", original, flags=re.MULTILINE)
    if painted != 1:
        raise ValueError("The private example requires one language button for its scene")
    insertions = (
        (b"mod fonts;", b"mod fonts;\nmod handoff_scene;"),
        (open_case, advance + b"                    continue;\n                }\n" + open_case),
    )
    for old, new in insertions:
        if original.count(old) != 1:
            raise ValueError("The private example no longer has a unique reviewed insertion point")
        original = original.replace(old, new)
    return original


def stage(gui, source_hashes):
    src = gui / "src"
    if gdi.inventory(src) != source_hashes:
        raise ValueError("The retained application's actual sources changed after compilation")
    folder = gui / "examples" / NAME
    shutil.copytree(src, folder)
    original = (src / "main.rs").read_bytes()
    main, scene = example_main(original), (HERE / "scene.rs").read_bytes()
    (folder / "main.rs").write_bytes(main)
    (folder / "handoff_scene.rs").write_bytes(scene)
    expected = dict(source_hashes, **{"main.rs": sha256(main).hexdigest(), "handoff_scene.rs": sha256(scene).hexdigest()})
    if gdi.inventory(folder) != expected:
        raise ValueError("Unexpected change to the example's sources")
    return {"ordinary-main.rs": original, "main.rs": main, "handoff_scene.rs": scene}


def gui_library(gui, release, units, package):
    """Recognize Cargo's promoted application rlib and its specific compilation-unit outputs."""
    library, = [u for u in units if u["package_id"] == package and u["target"]["name"] == "native_gui_assessment"
                and u["target"]["kind"] == ["lib"]]
    files = [PureWindowsPath(p) for p in library["filenames"]]
    metadata, = [p for p in files if p.suffix == ".rmeta"]
    original, = [p for p in files if p.suffix == ".rlib"]
    fingerprint = re.fullmatch(r"libnative_gui_assessment-([0-9a-f]{16})", metadata.stem)
    promoted = release / "libnative_gui_assessment.rlib"
    if (not fingerprint or metadata.parent not in (release / "deps", release / "build/native-gui-assessment" / fingerprint[1] / "out")
            or len(files) != 2 or original not in (promoted, metadata.with_suffix(".rlib"))
            or PureWindowsPath(library["target"]["src_path"]) != gui / "src/lib.rs"
            or PureWindowsPath(library["manifest_path"]) != gui / "Cargo.toml"):
        raise ValueError("Unexpected native application library, metadata or Cargo promotion")
    paths = dict(original=original, compiled=metadata.with_suffix(".rlib"), metadata=metadata)
    return library, {role: path.relative_to(release).as_posix() for role, path in paths.items()}


def native_outputs(cpu, base):
    gui, exe, units, _ = gdi.compilation(cpu / "compiler.jsonl", gdi=True, extra_local=cpu_build.LOCAL)
    app, = [u for u in units if u["target"]["name"] == "native-gui-assessment" and u["target"]["kind"] == ["bin"]]
    _, paths = gui_library(gui, exe.parent, units, app["package_id"])
    presenter = gui / gdi.PRESENTER
    unit, = [u for u in units if PureWindowsPath(u["manifest_path"]) == presenter / "Cargo.toml"]
    outputs = [PureWindowsPath(p) for p in unit["filenames"]]
    linked, = [p for p in outputs if p.suffix == ".rlib"]
    fingerprint = re.fullmatch(r"libegui_wgpu-([0-9a-f]{16})", linked.stem)
    metadata = linked.with_suffix(".rmeta")
    if (unit["target"]["name"] != "egui_wgpu" or unit["target"]["kind"] != ["lib"]
            or PureWindowsPath(unit["target"]["src_path"]) != presenter / "src/lib.rs"
            or not fingerprint or linked.parent not in (exe.parent / "deps", exe.parent / "build/egui-wgpu" / fingerprint[1] / "out")
            or len(outputs) != 2 or set(outputs) != {linked, metadata}):
        raise ValueError("Unexpected outputs for the compiled CPU and wgpu presenter")
    paths.update(presenter=linked.relative_to(exe.parent).as_posix(),
                 presenterMetadata=metadata.relative_to(exe.parent).as_posix())
    compiled = cpu_build.library_units(gui, units, exe)
    renderer = {name: [p.relative_to(exe.parent).as_posix() for p in files] for name, files in compiled.items()}
    if base["libraries"] != renderer or sha(cpu / "cpu-libraries.zip") != base["libraryArchive"]:
        raise ValueError("The original compiled renderer libraries differ from the native Cargo receipt")
    return paths, sorted(path for files in renderer.values() for path in files)


def archived_renderer(cpu, members, *, compare_live=False):
    hashes = {}
    with ZipFile(cpu / "cpu-libraries.zip") as archive:
        if sorted(archive.namelist()) != members:
            raise ValueError("The original renderer library archive has unexpected members")
        for name in members:
            data = archive.read(name)
            if compare_live and (cpu / "build/release" / name).read_bytes() != data:
                raise ValueError(f"The example build used different native library bytes: {name}")
            hashes[name] = sha256(data).hexdigest()
    return hashes


def library_hashes(members, paths):
    if set(members) != set(paths.values()):
        raise ValueError("The native application library byte records are incomplete")
    original = members[paths["original"]]
    if (not original.startswith(b"!<arch>\n") or original != members[paths["compiled"]]
            or not members[paths["metadata"]] or not members[paths["presenter"]].startswith(b"!<arch>\n")
            or not members[paths["presenterMetadata"]]):
        raise ValueError("Cargo's promoted and compilation-unit application libraries differ")
    return {name: sha256(data).hexdigest() for name, data in members.items()}


def compiler_examples(cpu_stream, example_stream):
    gui, cpu_exe, units, _ = gdi.compilation(cpu_stream, gdi=True, extra_local=cpu_build.LOCAL)
    messages = [json.loads(line) for line in example_stream.read_bytes().splitlines()]
    if [u for u in messages if u["reason"] == "build-finished"] != [{"reason": "build-finished", "success": True}] or messages[-1]["reason"] != "build-finished":
        raise ValueError("Incomplete example compiler evidence")
    artifacts = [u for u in messages if u["reason"] == "compiler-artifact"]
    example, = [u for u in artifacts if u["target"]["kind"] == ["example"]]
    exe = cpu_exe.parent / "examples" / (NAME + ".exe")
    app, = [u for u in units if u["target"]["kind"] == ["bin"] and u["target"]["name"] == "native-gui-assessment"]
    if (example["target"]["name"] != NAME or example["package_id"] != app["package_id"]
            or example["target"]["crate_types"] != ["bin"] or example["fresh"] is not False
            or example["profile"] != app["profile"] or example["features"] != app["features"]
            or PureWindowsPath(example["manifest_path"]) != gui / "Cargo.toml"
            or PureWindowsPath(example["target"]["src_path"]) != gui / "examples" / NAME / "main.rs"
            or PureWindowsPath(example["executable"]) != exe or [PureWindowsPath(p) for p in example["filenames"]].count(exe) != 1):
        raise ValueError("The compiler selected another example or output file")

    library, paths = gui_library(gui, cpu_exe.parent, units, app["package_id"])
    linked_library, = [u for u in artifacts if u["package_id"] == app["package_id"]
                       and u["target"]["name"] == "native_gui_assessment" and u["target"]["kind"] == ["lib"]]
    linked_files = [PureWindowsPath(p) for p in linked_library["filenames"]]
    metadata = cpu_exe.parent / paths["metadata"]
    if (len(linked_files) != 2 or set(linked_files) not in
            ({cpu_exe.parent / paths["compiled"], metadata}, {cpu_exe.parent / paths["original"], metadata})):
        raise ValueError("The example did not link the native application rlib beside its original rmeta")

    def signature(unit):
        components = {k: unit[k] for k in ("package_id", "manifest_path", "target", "features", "filenames", "profile")}
        if unit is linked_library:
            components["filenames"] = library["filenames"]
        return json.dumps(components, sort_keys=True)

    linked = [u for u in artifacts if u is not example]
    if (any(u["fresh"] is not True for u in linked) or
            Counter(signature(u) for u in units if u is not app) != Counter(signature(u) for u in linked)):
        raise ValueError("The example did not link the original CPU build's exact library outputs")
    return len(units) - 1


def verify_staging(gui, base):
    sources = base["sources"]
    dependencies = {"egui-wgpu": gdi.PRESENTER, **cpu_build.LOCAL}
    for name, directory in dependencies.items():
        if gdi.inventory(gui / directory) != sources["trees"][name]:
            raise ValueError(f"Staged {name} sources changed after the native CPU build")
    for member, digest in sources["members"].items():
        if member.startswith("compiled/") and sha(gui / member.removeprefix("compiled/")) != digest:
            raise ValueError(f"Staged compiler input changed after the native CPU build: {member}")


def build(cpu, out):
    base = read(cpu / "cpu-build.json")
    gui = cpu / "project/tools/rust-qa/gui"
    verify_staging(gui, base)
    paths, renderer = native_outputs(cpu, base)
    renderer_hashes = archived_renderer(cpu, renderer, compare_live=True)
    release = cpu / "build/release"
    original = {name: (release / name).read_bytes() for name in paths.values()}
    before = library_hashes(original, paths)
    archive = cpu_build.warm.eframe_source.write_archive(out / "gui-library.zip", original)
    files = stage(gui, base["sources"]["ordinaryApp"])
    source = cpu_build.warm.eframe_source.write_archive(out / "source.zip", files)
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--frozen", "--release", "--example", NAME,
                        "--message-format=json-render-diagnostics"], cwd=gui, env=prepare.environment(cpu), stdout=log, check=True)
    compiled = cpu / "build/release/examples" / (NAME + ".exe")
    shared = compiler_examples(cpu / "compiler.jsonl", stream)
    after = library_hashes({name: (release / name).read_bytes() for name in paths.values()}, paths)
    if after != before or renderer_hashes != archived_renderer(cpu, renderer, compare_live=True):
        raise ValueError("Native library output changed across the example link")
    library = dict(paths=paths, before=before, after=after, archive=archive, renderer=renderer_hashes)
    verify_staging(gui, base)
    binary = out / "handoff.exe"
    shutil.copyfile(compiled, binary)
    return dict(cpuBuild=sha(cpu / "cpu-build.json"), source=source, compiler=sha(stream), binary=sha(binary),
                sharedUnits=shared, library=library)


def verify(cpu, record):
    out = cpu / "handoff"
    base = read(cpu / "cpu-build.json")
    from inputs import recorder
    expected = record["build"]
    if (any(record[k] != base[k] for k in ("run", "revision", "attempt", "target"))
            or record["target"] != prepare.TARGET or sha(cpu / "compiler.jsonl") != base["compiler"]
            or sha(cpu / "cpu.exe") != base["application"]["sha256"]
            or sha(cpu / "cpu-build.json") != expected["cpuBuild"] or sha(out / "source.zip") != expected["source"]
            or sha(out / "compiler.jsonl") != expected["compiler"] or sha(out / "handoff.exe") != expected["binary"]
            or expected["binary"] == base["application"]["sha256"] or recorder.pe_machine(out / "handoff.exe") != 0x8664
            or compiler_examples(cpu / "compiler.jsonl", out / "compiler.jsonl") != expected["sharedUnits"]):
        raise ValueError("The native compiler, binary, original build or test sources do not match")
    paths, renderer = native_outputs(cpu, base)
    evidence = expected["library"]
    with ZipFile(out / "gui-library.zip") as archive:
        if sorted(archive.namelist()) != sorted(set(paths.values())):
            raise ValueError("Unexpected native application library archive members")
        digests = library_hashes({name: archive.read(name) for name in paths.values()}, paths)
    if (paths != evidence["paths"] or sha(out / "gui-library.zip") != evidence["archive"]
            or not digests == evidence["before"] == evidence["after"]
            or archived_renderer(cpu, renderer) != evidence["renderer"]):
        raise ValueError("The native promoted library, unit outputs or renderer byte evidence differs")
    with ZipFile(out / "source.zip") as archive:
        if sorted(archive.namelist()) != ["handoff_scene.rs", "main.rs", "ordinary-main.rs"]:
            raise ValueError("Unexpected source archive contents")
        original = archive.read("ordinary-main.rs")
        if (sha256(original).hexdigest() != base["sources"]["ordinaryApp"]["main.rs"]
                or example_main(original) != archive.read("main.rs") or archive.read("handoff_scene.rs") != (HERE / "scene.rs").read_bytes()):
            raise ValueError("The native example differs from the reviewed scene and retained application")


def observer_sources(revision):
    sources = [HERE / n for n in ("fixture_build.py", "readback.py", "run.py", "evidence.py", "scene.rs", "pixels.py")]
    sources.extend(prepare.QA / n for n in (
        "windows-cpu-paint/cpu_build.py", "windows-cpu-paint/measure.py", "windows-gdi-present/gdi_case.py",
        "windows-warm-window/inputs.py", "windows-warm-window/window_lifetime.py", "windows-performance/run.py",
        "windows-performance/native.py", "windows-performance/present.cpp", "windows-performance/etw-owned.h",
        "observe-windows-gui.py"))
    observed = {}
    for path in sources:
        name = path.relative_to(prepare.ROOT).as_posix()
        data = subprocess.check_output(["git", "show", revision + ":" + name], cwd=prepare.ROOT)
        if data != path.read_bytes():
            raise ValueError(f"Native handoff input differs from revision {revision}: {name}")
        observed[name] = sha256(data).hexdigest()
    return observed
