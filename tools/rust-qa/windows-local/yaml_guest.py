"""Run the compiler's native YAML tests and both C# passes on the disposable Windows x64 guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

# The guest's private embeddable Python omits the script directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storage import DOTNET, QA, ROOT, relative_member, sha256, verify_fixture, verify_host, verify_sources, write_json
from workspace import test_counts

sys.path.insert(0, str(QA / "yaml"))
from local_vm import DLL, EXE, RECEIPT, TARGET, build_inputs, verify_test_build
from run import exchange


def unpack(archive, expected, revision, fixtures, area):
    inputs = json.loads((QA / "yaml/inputs.json").read_bytes())
    with archive.open("rb") as original:
        if not re.fullmatch("[0-9a-f]{64}", expected) or hashlib.file_digest(original, "sha256").hexdigest() != expected:
            raise ValueError("The YAML ZIP differs from the original Actions artifact digest")
        with ZipFile(original) as kit:
            index = json.loads(kit.read(RECEIPT))
            files = index["files"]
            required = {EXE, DLL, "dotnet/YamlOracle.deps.json", "dotnet/YamlOracle.runtimeconfig.json",
                        "dotnet/ImmichFolderWatch.Core.dll", "dotnet/YamlDotNet.dll", "tests/build.json",
                        "tests/compiler.jsonl", "compiler/filtered-sources.tar", "compiler/source-filter.json",
                        "compiler/native-graph.json", "compiler/first-party-source-hashes.json"}
            members = sorted(z.filename for z in kit.infolist() if not z.is_dir())
            if (index["format"] != "ifw-windows-x64-yaml-build-v1" or index["target"] != TARGET
                    or not re.fullmatch("[0-9a-f]{40}", revision) or index["revision"] != revision
                    or not index["compilerRun"].isdecimal() or not required <= files.keys()
                    or members != sorted([*files, RECEIPT]) or index["lockSha256"] != inputs["lock_sha256"]
                    or index["lockSha256"] != sha256(QA / "yaml/Cargo.lock")
                    or index["filteredBundleSha256"] != inputs["filtered_bundle_sha256"]
                    or files["compiler/filtered-sources.tar"] != index["filteredBundleSha256"]
                    or index["fixtureManifestSha256"] != sha256(fixtures / "manifest.json")
                    or files[EXE] != index["rustExecutableSha256"] or files[DLL] != index["csharpAssemblySha256"]):
                raise ValueError("The YAML compiler, fixture or archive manifest differs")
            for name, checksum in files.items():
                target = area / relative_member(name)
                if (target == area or not target.resolve().is_relative_to(area)
                        or name != EXE and not name.startswith(("compiler/", "dotnet/", "tests/"))):
                    raise ValueError("Unexpected compiler archive member")
                target.parent.mkdir(parents=True, exist_ok=True)
                with kit.open(name) as src, target.open("xb") as dest:
                    shutil.copyfileobj(src, dest)
                if sha256(target) != checksum:
                    raise ValueError("Compiler member digest mismatch: " + name)
    sources = json.loads((area / "compiler/first-party-source-hashes.json").read_bytes())
    if not {p.relative_to(ROOT).as_posix() for p in build_inputs()} <= sources.keys():
        raise ValueError("The compiler did not identify its local YAML adapter inputs")
    verify_sources(ROOT, sources)
    if json.loads((area / "compiler/native-graph.json").read_bytes()) != inputs["target_graphs"][TARGET]:
        raise ValueError("The native YAML compiler graph differs from the reviewed graph")
    return index, verify_test_build(area / "tests", revision)


def run(archive, expected, output, dotnet):
    if os.environ.get("GITHUB_ACTIONS") or platform.node().casefold() != "ifw-qa25":
        raise ValueError("Use the disposable local Windows x64 VM")
    verify_host()
    if output == ROOT / "artifacts/rust" or not output.is_relative_to(ROOT / "artifacts/rust"):
        raise ValueError("Choose a new output below the checkout's artifacts/rust directory")
    machine = runpy.run_path(str(QA / "windows-performance/build.py"))["pe_machine"]
    if dotnet.name.lower() != "dotnet.exe" or sha256(dotnet) != DOTNET or machine(dotnet) != 0x8664:
        raise ValueError("Select the reviewed .NET 10.0.12 Windows x64 host")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    fixtures = ROOT / "rust/tests/fixtures/legacy/windows"
    verify_fixture(fixtures, "windows")
    output.mkdir(parents=True, exist_ok=False)
    steps = {}
    tests = {}
    result = {"format": "ifw-windows-x64-yaml-guest-v1", "status": "failed", "revision": revision,
              "archiveSha256": expected, "target": TARGET, "dotnetSha256": DOTNET, "host": platform.node(),
              "os": platform.platform(), "steps": steps, "tests": tests}
    try:
        with TemporaryDirectory(dir=output) as tmp:
            area = Path(tmp)
            index, harnesses = unpack(archive, expected, revision, fixtures, area)
            result["compilerRun"] = index["compilerRun"]
            if any(machine(path) != 0x8664 for path in [area / EXE, *(area / "tests" / n for n in harnesses)]):
                raise ValueError("The Rust YAML program and each unit harness must be AMD64 PE images")
            env = {k: v for k, v in os.environ.items() if k.upper() in
                   {"SYSTEMROOT", "WINDIR", "COMSPEC", "PROCESSOR_ARCHITECTURE"}}
            env.update(PATH=str(dotnet.parent) + os.pathsep + str(Path(env["SYSTEMROOT"]) / "System32"),
                       TEMP=tmp, TMP=tmp, DOTNET_ROOT=str(dotnet.parent), DOTNET_MULTILEVEL_LOOKUP="0",
                       DOTNET_CLI_HOME=tmp, DOTNET_CLI_TELEMETRY_OPTOUT="1", IFW_ORACLE_EXPECT_ARCH="x64")

            def command(label, args):
                log = output / (label + ".log")
                with log.open("xb") as stream:
                    code = subprocess.run(args, cwd=ROOT, env=env, stdout=stream,
                                          stderr=subprocess.STDOUT, timeout=600).returncode
                steps[label] = {"exitCode": code, "logSha256": sha256(log)}
                if code:
                    raise ValueError("Native YAML step failed: " + label)

            command("filter-tests", [sys.executable, "-B", "-m", "unittest", "discover",
                                     "-s", str(QA / "yaml"), "-p", "test_prepare.py"])
            for name, row in harnesses.items():
                label = "test-" + name
                command(label, [area / "tests" / name, "--test-threads=1"])
                counts = test_counts((output / (label + ".log")).read_bytes())
                if (counts is None or any(counts[k] for k in ("failed", "ignored", "measured", "filtered"))
                        or row["kind"] in (["lib"], ["bin"]) and counts["passed"] == 0):
                    raise ValueError("Native YAML unit tests were omitted or failed: " + name)
                tests[name] = {"target": row["target"], "kind": row["kind"], **counts}
            exported, rust, csharp = exchange(area / EXE, dotnet, area / DLL, fixtures,
                                              area / "ref", output, TARGET, command)
            if any((report["runtime"], report["architecture"], report["osArchitecture"]) != ("10.0.12", "X64", "X64")
                   for report in [exported, csharp]):
                raise ValueError("The reference must run twice with .NET 10.0.12 on native Windows x64")
            result.update(rust=rust, csharp=csharp, originalInputs=len(exported["cases"]))
            verify_fixture(fixtures, "windows")
        result["status"] = "passed"
    finally:
        result["files"] = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
        write_json(output / "guest.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("sha256", help="original compiler ZIP digest from Actions")
    parser.add_argument("output", type=Path)
    parser.add_argument("--dotnet", required=True, type=Path)
    args = parser.parse_args()
    run(args.archive.resolve(strict=True), args.sha256.removeprefix("sha256:"), args.output.resolve(),
        args.dotnet.resolve(strict=True))
