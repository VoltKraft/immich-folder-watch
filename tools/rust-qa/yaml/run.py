"""Acquire audited private inputs, then build/run only filtered offline YAML sources.

Upload only --output, never the sibling private-cache/private-work directories.
The output contains a filtered source bundle; it never contains original .crate
archives, including the base64 archive that carries the excluded promotional logo.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback
import uuid

from prepare import ROOT, HERE, bundle, file_digest, graph, prepare, write_json


SCOPE = ROOT / "artifacts/rust/yaml-assessment"


def isolated(path: Path, scope: Path = SCOPE) -> Path:
    path = path.resolve()
    if not path.is_relative_to(scope.resolve()) or path == scope.resolve():
        raise ValueError("path must be strictly below the synthetic assessment scope")
    return path


def record_sources(output: Path, fixtures: Path) -> None:
    paths = [ROOT / name for name in ["global.json", "Directory.Build.props", "NuGet.Config",
                                      "rust/toolchain-inputs.json", "tools/rust-qa/check-toolchain.py"]]
    for root in (HERE, ROOT / "src/ImmichFolderWatch.Core", fixtures):
        paths += [path for path in root.rglob("*") if path.is_file()
                  and not {"bin", "obj", "target", "__pycache__"}.intersection(path.relative_to(root).parts)]
    hashes = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        destination = output / "first-party-sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        hashes[relative.as_posix()] = file_digest(path)
    write_json(output / "first-party-source-hashes.json", hashes)


def main() -> int:
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["target_graphs"]))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cargo-home", type=Path, default=SCOPE / "private-cache")
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    output = isolated(args.output or SCOPE / "runs" / f"{args.target}-{identity}")
    acquisition = isolated(args.cargo_home, ROOT / "artifacts/rust")
    if output.is_relative_to(acquisition) or acquisition.is_relative_to(output):
        raise ValueError("private acquisition cache and uploadable evidence must be separate")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = SCOPE / "private-work" / identity
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    dotnet = str(Path(args.dotnet).resolve()) if Path(args.dotnet).is_file() else args.dotnet
    native = "windows" if sys.platform == "win32" else "linux"
    fixtures = ROOT / "rust/tests/fixtures/legacy" / native
    env = os.environ.copy()
    removed = []
    for key in list(env):
        if key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"} or key.endswith("_RUSTFLAGS"):
            removed.append(key)
            del env[key]
    env.update({"CARGO_HOME": str(acquisition), "CARGO_TARGET_DIR": str(work / "target"),
                "IFW_ORACLE_EXPECT_ARCH": "arm64" if args.target.startswith("aarch64-") else "x64",
                "DOTNET_CLI_HOME": str(work / "dotnet-cli"), "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false"})
    result = {"format": "ifw-rw02-yaml-native-v1", "status": "running", "target": args.target,
              "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "modifiedSources": subprocess.check_output(["git", "status", "--porcelain", "--", str(HERE),
                  "src/ImmichFolderWatch.Core", "global.json", "Directory.Build.props", "NuGet.Config", "rust/tests/fixtures/legacy"], cwd=ROOT, text=True).splitlines(),
              "workflowRun": os.getenv("GITHUB_RUN_ID"), "operatingSystem": platform.platform(), "offlineAcquisition": args.offline,
              "removedBuildOverrideNames": sorted(removed), "steps": {}}

    def command(name: str, arguments: list[str]) -> None:
        print(f"YAML assessment: {name}", flush=True)
        log = output / f"{name}.log"
        with log.open("wb") as stream:
            try:
                code = subprocess.run(arguments, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200).returncode
            except subprocess.TimeoutExpired:
                code = 124
                stream.write(b"Timed out after 1200 seconds.\n")
        result["steps"][name] = {"exitCode": code, "command": arguments, "log": log.name}
        write_json(output / "result.json", result)
        print(log.read_text(encoding="utf-8", errors="replace")[-4500:], end="", flush=True)
        if code:
            raise RuntimeError(f"{name} failed with exit code {code}")

    try:
        command("native-compiler", [sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"), args.target])
        command("filter-tests", [sys.executable, str(HERE / "test_prepare.py")])
        if file_digest(HERE / "Cargo.lock") != inputs["lock_sha256"]:
            raise ValueError("generated YAML lockfile differs from reviewed inputs")
        manifest = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
        if manifest["SyntheticOnly"] is not True or manifest["Platform"] != native:
            raise ValueError("not the reviewed native synthetic corpus")
        for name, expected in manifest["Fixtures"].items():
            path = (fixtures / name).resolve()
            if not path.is_relative_to(fixtures.resolve()) or file_digest(path) != expected:
                raise ValueError("reviewed fixture checksum or path mismatch")
        record_sources(output, fixtures)
        cargo_manifest = ["--manifest-path", str(HERE / "Cargo.toml")]
        redirect = "import subprocess,sys; p=subprocess.run(sys.argv[2:],stdout=subprocess.PIPE); open(sys.argv[1],'wb').write(p.stdout); sys.exit(p.returncode)"
        acquisition_arguments = ["cargo", "metadata", *cargo_manifest, "--locked", "--format-version", "1"]
        if args.offline: acquisition_arguments.append("--offline")
        command("private-acquisition", [sys.executable, "-c", redirect, str(work / "private-metadata.json"), *acquisition_arguments])
        vendor = work / "vendor"
        filtered = prepare(acquisition, vendor, inputs)
        write_json(output / "source-filter.json", filtered)
        bundle(vendor, filtered, output / "filtered-sources.tar.gz")
        if file_digest(output / "filtered-sources.tar.gz") != inputs["filtered_bundle_sha256"]:
            raise ValueError("filtered source bundle is not byte reproducible")
        result["filteredBundleSha256"] = inputs["filtered_bundle_sha256"]
        result["originalArchiveCount"] = len(filtered["packages"])
        result["filteredSourceFiles"] = sum(len(package["files"]) for package in filtered["packages"])
        result["noticeFiles"] = sum(len(package["notices"]) for package in inputs["packages"])
        # This new empty Cargo home has neither original archives nor registry
        # sources. Every subsequent Cargo operation is frozen and directory-only.
        env["CARGO_HOME"] = str(work / "empty-offline-cargo")
        config = ["--config", 'source.crates-io.replace-with="ifw-reviewed"', "--config",
                  "source.ifw-reviewed.directory=" + json.dumps(str(vendor), ensure_ascii=False)]
        metadata_path = output / "offline-native-metadata.json"
        command("offline-native-graph", [sys.executable, "-c", redirect, str(metadata_path), "cargo", "metadata",
                *cargo_manifest, *config, "--frozen", "--format-version", "1", "--filter-platform", args.target])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if graph(metadata) != inputs["target_graphs"][args.target]:
            raise ValueError("native YAML graph differs from reviewed inputs")
        for package in metadata["packages"]:
            if package["source"] and not Path(package["manifest_path"]).resolve().is_relative_to(vendor.resolve()):
                raise ValueError("offline build resolved an unfiltered source")
        result["nativeGraphPackages"] = len(graph(metadata))
        command("format", ["cargo", "fmt", *cargo_manifest, "--", "--check"])
        common = [*cargo_manifest, *config, "--frozen", "--target", args.target]
        command("clippy", ["cargo", "clippy", *common, "--all-targets", "--", "-D", "warnings"])
        command("tests", ["cargo", "test", *common, "--", "--show-output"])
        command("release", ["cargo", "build", *common, "--release"])
        binary = work / "target" / args.target / "release" / ("ifw-yaml-assessment.exe" if os.name == "nt" else "ifw-yaml-assessment")
        result["rustExecutableSha256"] = file_digest(binary)
        project = HERE / "dotnet/YamlOracle.csproj"
        dotnet_common = [str(project), "--artifacts-path", str(work / "dotnet"), "-p:EnableWindowsTargeting=false"]
        restore = [dotnet, "restore", *dotnet_common]
        if args.offline: restore += ["--ignore-failed-sources", "-p:NuGetAudit=false"]
        command("csharp-restore", restore)
        command("csharp-build", [dotnet, "build", *dotnet_common, "--no-restore", "--configuration", "Release"])
        assembly = work / "dotnet/bin/YamlOracle/release/YamlOracle.dll"
        result["csharpAssemblySha256"] = file_digest(assembly)
        reference = output / "reference"
        command("csharp-reference", [dotnet, str(assembly), "export", str(fixtures), str(reference)])
        exported = json.loads((reference / "reference.json").read_text(encoding="utf-8"))
        if file_digest(reference / "casing.json") != exported["casingSha256"]:
            raise ValueError("native string reference checksum mismatch")
        command("rust-roundtrip", [str(binary), str(reference), str(output / "rust-output")])
        command("csharp-readback", [dotnet, str(assembly), "verify", str(reference), str(output / "rust-output")])
        result["rust"] = json.loads((output / "rust-output/result.json").read_text(encoding="utf-8"))
        result["csharp"] = json.loads((output / "rust-output/csharp-readback.json").read_text(encoding="utf-8"))
        expected_readback = 4 * sum(case["accepted"] for case in exported["cases"])
        if (result["rust"]["platform"] != native or result["rust"]["architecture"] != args.target.split("-")[0]
                or result["csharp"]["assertions"] != expected_readback or exported["corpusAssertions"] != 10):
            raise ValueError("incomplete native YAML results")
        result["status"] = "passed"
        print(f"YAML assessment passed; upload only: {output}", flush=True)
    except Exception as error:
        result["status"] = "failed"
        result["error"] = str(error)
        traceback.print_exc()
    finally:
        write_json(output / "result.json", result)
        write_json(output / "evidence-hashes.json", {path.relative_to(output).as_posix(): file_digest(path)
            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "evidence-hashes.json"})
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
