"""Run the reviewed SQLite/JSON/SHA assessment on one native target.

This separate development workspace never opens an application profile. Output
must be a new directory below artifacts/rust. --offline uses cached Cargo/NuGet
inputs and disables NuGet advisory retrieval for that explicit offline run.
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

from evidence import external_lock, sha256, target_graph, verify_fixture, verify_sources, write_json


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / "artifacts/rust"
MANIFEST = HERE / "Cargo.toml"


def isolated_path(value: Path) -> Path:
    path = value.resolve()
    if not path.is_relative_to(ARTIFACTS.resolve()) or path == ARTIFACTS.resolve():
        raise ValueError("assessment paths must be strictly below repository artifacts/rust")
    return path


def archive_first_party(output: Path, fixtures: Path, extra_inputs: list[Path]) -> dict:
    paths = [ROOT / name for name in
             ("global.json", "NuGet.Config", "Directory.Build.props", "rust/Cargo.toml",
              "rust/toolchain-inputs.json", "tools/rust-qa/check-toolchain.py",
              "tools/rust-qa/legacy/InvariantUppercaseProfile.cs")]
    paths.extend(extra_inputs)
    for directory in (HERE, ROOT / "rust/crates/ifw-legacy", ROOT / "src/ImmichFolderWatch.Core", fixtures):
        paths += [path for path in directory.rglob("*") if path.is_file()
                  and not {"obj", "target", "__pycache__"}.intersection(path.relative_to(directory).parts)
                  and ("bin" not in path.relative_to(directory).parts
                       or path.relative_to(directory).parts[:2] == ("src", "bin"))
                  and path.suffix != ".pyc"]
    hashes = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        destination = output / "first-party-sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        hashes[relative.as_posix()] = sha256(path)
    write_json(output / "first-party-source-hashes.json", hashes)
    return hashes


def run_worker_activities(output, result, probe, test_assembly, dotnet, env, target):
    from worker_activity import SCENARIOS, run as run_activity

    def executable_hashes():
        if shutil.which(dotnet, path=env.get("PATH")) is None:
            raise FileNotFoundError(f"Worker test launcher is unavailable: {dotnet}")
        return {"rustExecutable": sha256(probe), "testAssembly": sha256(test_assembly)}

    originals = executable_hashes()
    activity = result["workerActivity"] = originals.copy()
    for kind in SCENARIOS:
        name = "worker-activity" if kind == "download" else "worker-" + kind + "-activity"
        field = "readback" if kind == "download" else kind + "Readback"
        try:
            activity[field] = run_activity(output / name, probe, test_assembly, dotnet, env,
                                           target, result["source"], kind=kind)
        except Exception as error:
            # Leave the original case directory, worker log, databases and xUnit result intact.
            log = output / (name + "-failure.log")
            log.write_text(traceback.format_exc(), encoding="utf-8")
            activity.setdefault("failures", {})[kind] = {"error": str(error), "log": log.name, "directory": name}
            print(f"Worker {kind} failed: {error}. See {log}", flush=True)
        finally:
            write_json(output / "result.json", result)
        if executable_hashes() != originals:
            raise ValueError("an executable changed during the worker activity trial")
    if "failures" in activity:
        raise RuntimeError("Worker activity failed for " + ", ".join(activity["failures"]))


def main() -> int:
    toolchain = json.loads((ROOT / "rust/toolchain-inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(toolchain["targets"]))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cargo-home", type=Path, default=ARTIFACTS / "storage-cargo-home")
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--compile-for-local-vm", action="store_true",
                        help="Archive the Windows x64 SQLite assessment and C# reader for local execution")
    parser.add_argument("--stored-keys", action="store_true",
                        help="Inspect synthetic C# identities and check concordant inserts through the native rollback writer")
    parser.add_argument("--worker-activity", action="store_true",
                        help="Return native Rust backups to the shipping worker after a synthetic download, upload, deletion and interrupted timestamp repair")
    parser.add_argument("--installed-upload-backup", action="store_true",
                        help="Build and retain the native backup helper for the isolated installed-application upload trial")
    args = parser.parse_args()
    if args.compile_for_local_vm and (
            os.name != "nt" or args.target != "x86_64-pc-windows-msvc"
            or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust" or os.getenv("RUNNER_ARCH") != "X64"
            or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"
            or args.worker_activity or args.stored_keys or args.installed_upload_backup):
        parser.error("Select the dedicated rewrite compiler for the local Windows x64 storage assessment")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    output = isolated_path(args.output or ARTIFACTS / "storage-native" / f"{args.target}-{run_id}")
    cargo_home = isolated_path(args.cargo_home)
    # mkdir(exist_ok=False) refuses even a previous failed evidence directory.
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = ARTIFACTS / "storage-build" / run_id
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    native_os = "windows" if sys.platform == "win32" else "linux" if sys.platform == "linux" else "unsupported"
    fixtures = ROOT / "rust/tests/fixtures/legacy" / native_os
    dotnet = str(Path(args.dotnet).resolve()) if Path(args.dotnet).is_file() else args.dotnet
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    casing_inputs = []
    if args.stored_keys:
        casing_inputs = [HERE.parent / "legacy" / path for path in
                         ("casing/unicode-15.1.0.tsv", "casing/unicode-17.0.0.tsv",
                          "casing_profiles.py", "licenses/Unicode-LICENSE.txt")]
    extra_inputs = list(casing_inputs)
    activity_project = ROOT / "src/ImmichFolderWatch.Tests.Core/ImmichFolderWatch.Tests.Core.csproj"
    if args.worker_activity:
        extra_inputs.extend([activity_project, ROOT / "tools/RustCompatibilityOracle/verify_activity.py",
                             ROOT / "tools/RustCompatibilityOracle/verify_rollback.py",
                             ROOT / "Directory.Build.targets", HERE.parent / "windows-performance/native.py",
                             HERE.parent / "legacy/casing/unicode-15.1.0.tsv",
                             *sorted((activity_project.parent / "Services").glob("FolderWatchWorkerPersistenceTests*.cs"))])
    env = os.environ.copy()
    # Build flag overrides must not silently change the reviewed native input.
    removed = []
    for key in list(env):
        if (key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                    "SQLITE_MAX_VARIABLE_NUMBER", "SQLITE_MAX_EXPR_DEPTH", "SQLITE_MAX_COLUMN", "CRATE_CC_NO_DEFAULTS"}
                or key.startswith(("CFLAGS", "CXXFLAGS", "CPPFLAGS", "ARFLAGS"))
                or key.endswith(("_CFLAGS", "_CXXFLAGS", "_CPPFLAGS", "_ARFLAGS", "_RUSTFLAGS"))):
            removed.append(key)
            del env[key]
    env.update({"CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(work / "rust"),
                "LIBSQLITE3_SYS_USE_PKG_CONFIG": "0", "LIBSQLITE3_FLAGS": inputs["sqlite"]["flags"],
                "CC_ENABLE_DEBUG_OUTPUT": "1",
                "IFW_ORACLE_EXPECT_ARCH": "arm64" if args.target.startswith("aarch64-") else "x64",
                "DOTNET_CLI_HOME": str(work / "dotnet-cli"), "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "DOTNET_NOLOGO": "1"})
    result = {
        "format": "ifw-rw02-storage-native-v1", "status": "running", "target": args.target,
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "modifiedSources": subprocess.check_output([
            "git", "status", "--porcelain", "--", str(HERE), "rust/crates/ifw-legacy", "rust/Cargo.toml",
            "src/ImmichFolderWatch.Core", "Directory.Build.props", "global.json", "NuGet.Config",
            "rust/tests/fixtures/legacy", "tools/rust-qa/check-toolchain.py",
            "tools/rust-qa/legacy/InvariantUppercaseProfile.cs",
            *map(str, extra_inputs), *(["src/ImmichFolderWatch.Immich", "src/ImmichFolderWatch.App.Shared",
                                       "src/ImmichFolderWatch.App.Linux/Platform", str(activity_project.parent)]
                                      if args.worker_activity else [])], cwd=ROOT, text=True).splitlines(),
        "workflowRun": os.getenv("GITHUB_RUN_ID"), "operatingSystem": platform.platform(),
        "offline": args.offline, "removedBuildOverrideNames": sorted(removed),
        "nativeBuild": {"LIBSQLITE3_FLAGS": inputs["sqlite"]["flags"], "LIBSQLITE3_SYS_USE_PKG_CONFIG": "0"},
        "steps": {}, "unproven": ["production storage adapter", "YAML", "old optional schema migration",
                                   "migration of a live legacy profile", "full disk and process crash recovery",
                                   "cross-environment Unicode identity migration"],
    }
    write_json(output / "result.json", result)

    def command(name: str, arguments: list[str], *, verbose: bool = True) -> bytes:
        log = output / f"{name}.log"
        print(f"Storage assessment: {name}", flush=True)
        with log.open("wb") as stream:
            try:
                code = subprocess.run(arguments, cwd=ROOT, env=env, stdout=stream,
                                      stderr=subprocess.STDOUT, timeout=1200).returncode
            except subprocess.TimeoutExpired:
                code = 124
                stream.write(b"Timed out after 1200 seconds.\n")
        result["steps"][name] = {"exitCode": code, "command": arguments, "log": log.name}
        write_json(output / "result.json", result)
        data = log.read_bytes()
        if verbose or code:
            print(data.decode("utf-8", errors="replace")[-5000:], end="", flush=True)
        if code:
            raise RuntimeError(f"{name} failed with exit code {code}; see {log}")
        return data

    try:
        if args.worker_activity and result["modifiedSources"]:
            raise ValueError("the worker handoff requires committed test, compiler and worker sources")
        command("native-compiler", [sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"), args.target])
        if not args.compile_for_local_vm:
            command("evidence-tests", [sys.executable, str(HERE / "test_evidence.py")])
        expected_lock = {(entry["name"], entry["version"]): entry["archive_sha256"] for entry in inputs["packages"]}
        if sha256(HERE / "Cargo.lock") != inputs["lock_sha256"] or external_lock(HERE / "Cargo.lock") != expected_lock:
            raise ValueError("generated Cargo.lock differs from the reviewed 31-package input")
        result["lockSha256"] = sha256(HERE / "Cargo.lock")
        verify_fixture(fixtures, native_os)
        result["fixtureManifestSha256"] = sha256(fixtures / "manifest.json")
        result["firstPartySourceCount"] = len(archive_first_party(output, fixtures, extra_inputs))
        cargo = ["cargo", "metadata", "--manifest-path", str(MANIFEST), "--locked", "--format-version", "1"]
        if args.offline:
            cargo.append("--offline")
        # stdout JSON is separated from Cargo's progress/download diagnostics.
        metadata_path = output / "metadata.json"
        script = "import subprocess,sys; p=subprocess.run(sys.argv[2:],stdout=subprocess.PIPE); open(sys.argv[1],'wb').write(p.stdout); sys.exit(p.returncode)"
        command("resolve-inputs", [sys.executable, "-c", script, str(metadata_path), *cargo])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        counts = verify_sources(metadata, inputs, cargo_home, output)
        write_json(output / "verified-source-file-counts.json", counts)
        result["verifiedArchives"] = len(counts)
        result["verifiedSourceFiles"] = sum(counts.values())
        native_metadata = output / "native-metadata.json"
        command("native-graph", [sys.executable, "-c", script, str(native_metadata), *cargo,
                                 "--filter-platform", args.target], verbose=False)
        graph = target_graph(json.loads(native_metadata.read_text(encoding="utf-8")))
        if graph != inputs["target_graphs"][args.target]:
            raise ValueError("native dependency feature graph differs from reviewed inputs")
        write_json(output / "native-graph.json", graph)
        result["nativeGraphPackages"] = len(graph)
        command("features", ["cargo", "tree", "--manifest-path", str(MANIFEST), "--frozen",
                             "--target", args.target, "--edges", "normal,build,features"], verbose=False)
        if not args.compile_for_local_vm:
            command("format", ["cargo", "fmt", "--manifest-path", str(MANIFEST), "--", "--check"])
        if os.name != "nt":
            native_cc = next((env[name] for name in
                              ("CC_" + args.target, "CC_" + args.target.replace("-", "_"), "HOST_CC", "CC")
                              if name in env), "cc")
            # A compiler program path is supported here; shell fragments are not.
            command("c-compiler-version", [native_cc, "--version"])
        command("clippy", ["cargo", "clippy", "--manifest-path", str(MANIFEST), "--frozen", "--all-targets",
                           "--target", args.target, "--", "-D", "warnings"])
        command("build", ["cargo", "build", "--manifest-path", str(MANIFEST), "--frozen", "--release",
                          "--target", args.target])
        # Cargo 1.100 stores build-script stdout under package/hash/run/stdout.
        native_logs = sorted((work / "rust").glob("**/build/libsqlite3-sys/*/run/stdout"))
        if len(native_logs) != 2:
            raise ValueError("missing debug/release native SQLite compiler logs")
        for source in native_logs:
            destination = output / "native-build-logs" / source.relative_to(work / "rust")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            shutil.copyfile(source.with_name("stderr"), destination.with_name("stderr"))
            commands = source.read_text(encoding="utf-8", errors="replace")
            if not all(flag in commands for flag in inputs["sqlite"]["flags"].split()):
                raise ValueError("native compiler log lacks extension-loading restrictions")
        result["nativeBuildLogs"] = len(native_logs)
        executable = work / "rust" / args.target / "release" / ("ifw-sqlite-assessment.exe" if os.name == "nt" else "ifw-sqlite-assessment")
        result["rustExecutableSha256"] = sha256(executable)
        if not args.compile_for_local_vm:
            command("rust-roundtrip", [str(executable), str(fixtures), str(output / "databases")])
        project = HERE / "dotnet/StorageReadback.csproj"
        dotnet_common = [str(project), "--artifacts-path", str(work / "dotnet"), "-p:EnableWindowsTargeting=false"]
        restore = [dotnet, "restore", *dotnet_common]
        if args.offline:
            restore += ["--ignore-failed-sources", "-p:NuGetAudit=false"]
        command("csharp-restore", restore)
        command("csharp-build", [dotnet, "build", *dotnet_common, "--no-restore", "--configuration", "Release"])
        assembly = work / "dotnet/bin/StorageReadback/release/StorageReadback.dll"
        result["csharpAssemblySha256"] = sha256(assembly)
        if args.compile_for_local_vm:
            if result["modifiedSources"] or os.environ["GITHUB_SHA"] != result["source"]:
                raise ValueError("Local VM inputs require the unmodified source revision of the compiler run")
            kit = output / "guest"
            kit.mkdir()
            shutil.copy2(executable, kit / executable.name)
            shutil.copytree(assembly.parent, kit / "dotnet")
            compiler = kit / "compiler"
            compiler.mkdir()
            for name in ("first-party-source-hashes.json", "native-graph.json", "native-compiler.log", "build.log", "csharp-build.log"):
                shutil.copy2(output / name, compiler / name)
            shutil.copytree(output / "native-build-logs", compiler / "native-build-logs")
            write_json(kit / "storage-build.json", {
                "revision": result["source"], "target": args.target, "compilerRun": os.environ["GITHUB_RUN_ID"],
                "fixtureManifestSha256": result["fixtureManifestSha256"], "lockSha256": result["lockSha256"],
                "rustExecutableSha256": result["rustExecutableSha256"], "csharpAssemblySha256": result["csharpAssemblySha256"],
                "files": {p.relative_to(kit).as_posix(): sha256(p) for p in sorted(kit.rglob("*")) if p.is_file()},
            })
            result["status"] = "compiled"
            return 0
        command("csharp-readback", [dotnet, str(assembly), str(output / "databases")])
        rust_result = json.loads((output / "databases/result.json").read_text(encoding="utf-8"))
        csharp_result = json.loads((output / "databases/csharp-readback.json").read_text(encoding="utf-8"))
        if (rust_result["Os"] != native_os or rust_result["Arch"] != args.target.split("-")[0]
                or rust_result["SQLiteSourceId"] != inputs["sqlite"]["source_id"]
                or csharp_result["OperatingSystem"] != native_os or csharp_result["Assertions"] != 40
                or csharp_result["Architecture"].lower() != env["IFW_ORACLE_EXPECT_ARCH"]
                or csharp_result["OSArchitecture"].lower() != env["IFW_ORACLE_EXPECT_ARCH"]):
            raise ValueError("native Rust/C# result identity or assertion count mismatch")
        result["rust"] = rust_result
        result["csharp"] = csharp_result
        expected_wal = {"newer-with-index": 99, "newer-without-index": 99, "supported-without-index": 1}
        if csharp_result["QuiescentWalPreflight"] != [
                {"Case": name, "Version": version, "Value": version} for name, version in expected_wal.items()]:
            raise ValueError("C# did not recover all three quiescent database profiles")
        if args.installed_upload_backup:
            command("installed-backup-build", ["cargo", "build", "--manifest-path", str(MANIFEST), "--frozen", "--release",
                                              "--target", args.target, "--example", "installed_upload_backup"])
            backup = output / ("installed_upload_backup" + executable.suffix)
            shutil.copy2(executable.parent / "examples" / backup.name, backup)
            result["installedUploadBackup"] = sha256(backup)
        if args.stored_keys:
            from native_insert import run_native_insert

            corpus = output / "casing-fixtures"
            observation = output / "stored-keys"
            command("stored-key-build", ["cargo", "build", "--manifest-path", str(MANIFEST), "--frozen",
                                         "--release", "--target", args.target, "--example", "inspect_stored_keys",
                                         "--example", "update_study_copy"])
            example = executable.parent / "examples" / ("inspect_stored_keys" + executable.suffix)
            writer = example.with_name("update_study_copy" + executable.suffix)
            command("stored-key-reference", [dotnet, str(assembly), "--casing-fixtures", str(corpus)])
            command("stored-key-readback", [sys.executable, "-B", str(HERE / "stored_keys.py"), "--probe",
                                            str(example), "--fixture", str(corpus), "--output", str(observation)])
            manifest = json.loads((corpus / "manifest.json").read_bytes())
            if manifest["fixtureAssemblySha256"] != result["csharpAssemblySha256"]:
                raise ValueError("Stored key corpus came from a different C# build")
            result["storedKeys"] = {"inputs": sha256(corpus / "manifest.json"),
                                    "observations": sha256(observation / "result.json"),
                                    "rustExecutable": sha256(example),
                                    "newEntries": run_native_insert(command, corpus, writer, dotnet, assembly)}
        if args.worker_activity:
            command("worker-exchange-tests", [sys.executable, "-B", "-m", "unittest", "discover",
                                              "-s", str(HERE), "-p", "test_worker*.py"])
            command("worker-backup-tests", ["cargo", "test", "--manifest-path", str(MANIFEST), "--frozen",
                                            "--target", args.target, "--example", "worker_activity_backup"])
            command("worker-backup-build", ["cargo", "build", "--manifest-path", str(MANIFEST), "--frozen",
                                            "--release", "--target", args.target, "--example", "worker_activity_backup"])
            example = executable.parent / "examples" / ("worker_activity_backup" + executable.suffix)
            activity_build = work / "activity-dotnet"
            common = [str(activity_project), "--artifacts-path", str(activity_build), "--disable-build-servers"]
            restore = [dotnet, "restore", *common]
            if args.offline:
                empty_feed = work / "empty-feed"
                empty_feed.mkdir()
                restore += ["--source", str(empty_feed), "-p:NuGetAudit=false"]
            command("activity-reference-restore", restore)
            command("activity-reference-build", [dotnet, "build", *common, "--no-restore", "--configuration", "Release"])
            test_assembly = activity_build / "bin/ImmichFolderWatch.Tests.Core/release/ImmichFolderWatch.Tests.Core.dll"
            run_worker_activities(output, result, example, test_assembly, dotnet, env, args.target)
        result["status"] = "passed"
        print(f"Storage assessment passed; evidence: {output}", flush=True)
    except (KeyboardInterrupt, SystemExit):
        result["status"] = "cancelled"
        raise
    except Exception as error:
        result["status"] = "failed"
        result["error"] = str(error)
        traceback.print_exc()
    finally:
        write_json(output / "result.json", result)
        write_json(output / "evidence-hashes.json", {
            path.relative_to(output).as_posix(): sha256(path)
            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "evidence-hashes.json"
        })
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
