"""Compile and identify the native YAML inputs consumed by the local Windows x64 guest."""
import json
import os
from pathlib import Path
import shutil
import sys

from prepare import HERE, ROOT, file_digest, write_json

QA = HERE.parent
sys.path.insert(0, str(QA / "windows-local"))
sys.path.insert(0, str(QA))
from realtime.guest import verify_sources
from workspace import build_harnesses, harnesses

TARGET = "x86_64-pc-windows-msvc"
EXE = "ifw-yaml-assessment.exe"
DLL = "dotnet/YamlOracle.dll"
RECEIPT = "yaml-build.json"


def require_compiler(target):
    if (sys.platform != "win32" or target != TARGET or os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust" or not os.getenv("GITHUB_RUN_ID", "").isdecimal()):
        raise ValueError("Use the Windows x64 compiler job on rewrite/rust")


def build_inputs():
    return [ROOT / ".gitattributes", ROOT / "Directory.Build.targets",
            ROOT / ".github/workflows/rust-windows-x64-yaml-build.yaml",
            QA / "enter-windows-build.ps1", QA / "install-toolchain.sh", QA / "realtime/guest.py",
            QA / "storage/evidence.py", QA / "windows-local/storage.py", QA / "windows-local/workspace.py",
            QA / "windows-local/yaml_guest.py", QA / "windows-performance/build.py"]


def verify_test_build(directory, revision):
    receipt = json.loads((directory / "build.json").read_bytes())
    stream = directory / "compiler.jsonl"
    rows = harnesses(stream.read_bytes())
    expected = {("ifw_yaml_assessment", ("lib",)), ("ifw-yaml-assessment", ("bin",))}
    expected.update((file.stem, ("example",)) for file in (HERE / "examples").glob("*.rs"))
    expected.update((file.stem, ("test",)) for file in (HERE / "tests").glob("*.rs"))
    if (receipt["revision"] != revision or receipt["suite"] != "yaml" or receipt["target"] != TARGET
            or receipt["compilerSha256"] != file_digest(stream) or receipt["lockSha256"] != file_digest(HERE / "Cargo.lock")
            or set(rows) != set(receipt["binaries"])
            or {(row["target"], tuple(row["kind"])) for row in rows.values()} != expected):
        raise ValueError("The YAML harness targets differ from their native Cargo compiler stream")
    if {file.name for file in directory.iterdir()} != set(rows) | {"compiler.jsonl", "build.json"}:
        raise ValueError("Unexpected member in the native YAML harness directory")
    for name, row in rows.items():
        if receipt["binaries"][name] != dict(row, sha256=file_digest(directory / name)):
            raise ValueError("The YAML test executable differs from its original compiler output")
    return rows


def compile_tests(kit, common, env):
    build_harnesses(kit / "tests", "yaml", ["cargo", "test", *common, "--all-targets"], env)


def finish_kit(output, kit, result, binary, assembly, fixtures, native_graph, inputs):
    revision = result["source"]
    if result["modifiedSources"] or os.environ["GITHUB_SHA"] != revision:
        raise ValueError("The compiler must use the unmodified checked-out Actions revision")
    verify_test_build(kit / "tests", revision)
    source_index = output / "first-party-source-hashes.json"
    verify_sources(ROOT, json.loads(source_index.read_bytes()))
    shutil.copy2(binary, kit / EXE)
    shutil.copytree(assembly.parent, kit / "dotnet")
    compiler = kit / "compiler"
    compiler.mkdir()
    for name in ("first-party-source-hashes.json", "native-compiler.log", "release.log", "csharp-build.log",
                 "clippy.log", "source-filter.json", "filtered-sources.tar"):
        shutil.copy2(output / name, compiler / name)
    write_json(compiler / "native-graph.json", native_graph)
    write_json(kit / RECEIPT, {
        "format": "ifw-windows-x64-yaml-build-v1", "revision": revision, "target": TARGET,
        "compilerRun": os.environ["GITHUB_RUN_ID"], "lockSha256": file_digest(HERE / "Cargo.lock"),
        "fixtureManifestSha256": file_digest(fixtures / "manifest.json"),
        "filteredBundleSha256": inputs["filtered_bundle_sha256"],
        "rustExecutableSha256": result["rustExecutableSha256"], "csharpAssemblySha256": result["csharpAssemblySha256"],
        "files": {p.relative_to(kit).as_posix(): file_digest(p) for p in sorted(kit.rglob("*")) if p.is_file()},
    })
