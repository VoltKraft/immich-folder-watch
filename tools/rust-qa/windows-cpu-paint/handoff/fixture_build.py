"""Build one extra Cargo example against the actual native CPU renderer's compiled library graph."""
from collections import Counter
from hashlib import sha256
import json
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
    insertions = (
        (b"mod fonts;", b"mod fonts;\nmod handoff_scene;"),
        (b"            let language = ui.add(button);", b"            let language = ui.add(button);\n"
         b"            handoff_scene::paint(ui);"),
        (b"                Ok(()) if next[0] == b'O' => Command::Open,",
         b"                Ok(()) if matches!(next[0], b'1' | b'2') => {\n"
         b"                    handoff_scene::advance(next[0] - b'0');\n"
         b"                    continue;\n                }\n"
         b"                Ok(()) if next[0] == b'O' => Command::Open,"),
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
            or PureWindowsPath(example["manifest_path"]) != gui / "Cargo.toml"
            or PureWindowsPath(example["target"]["src_path"]) != gui / "examples" / NAME / "main.rs"
            or PureWindowsPath(example["executable"]) != exe or [PureWindowsPath(p) for p in example["filenames"]].count(exe) != 1):
        raise ValueError("The compiler selected another example or output file")

    def signature(unit):
        return json.dumps({k: unit[k] for k in ("package_id", "manifest_path", "target", "features", "filenames", "profile")}, sort_keys=True)

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
    files = stage(gui, base["sources"]["ordinaryApp"])
    source = cpu_build.warm.eframe_source.write_archive(out / "source.zip", files)
    stream = out / "compiler.jsonl"
    with stream.open("xb") as log:
        subprocess.run(["cargo", "build", "--frozen", "--release", "--example", NAME,
                        "--message-format=json-render-diagnostics"], cwd=gui, env=prepare.environment(cpu), stdout=log, check=True)
    compiled = cpu / "build/release/examples" / (NAME + ".exe")
    shared = compiler_examples(cpu / "compiler.jsonl", stream)
    verify_staging(gui, base)
    binary = out / "handoff.exe"
    shutil.copyfile(compiled, binary)
    return dict(cpuBuild=sha(cpu / "cpu-build.json"), source=source, compiler=sha(stream), binary=sha(binary), sharedUnits=shared)


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
