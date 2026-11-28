#!/usr/bin/env python3
"""Run bounded native SQLite faults against the unchanged reviewed C# corpus."""

from __future__ import annotations

import argparse
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / "artifacts/rust/storage-faults"
STORAGE = HERE.parent / "storage"
sys.dont_write_bytecode = True
sys.path.insert(0, str(STORAGE))
from evidence import external_lock, sha256, target_graph, verify_fixture, verify_sources, write_json
import windows_vhd

PROVIDER_FILES = tuple(HERE / name for name in ("fat_provider.rs", "windows_provider.py", "test_windows_provider.py"))


def evidence_inventory(output: Path) -> dict:
    """Exclude only the top-level scratch tree, retaining copied build evidence."""
    return {path.relative_to(output).as_posix(): sha256(path)
            for path in sorted(output.rglob("*")) if path.is_file()
            and path.relative_to(output).parts[0] != "build" and path.name != "evidence-hashes.json"}


def archive_reviewed_storage(build: Path, output: Path) -> None:
    originals = output / "first-party-sources/tools/rust-qa/storage/src"
    main = (originals / "main.rs").read_bytes()
    modules = {name: (originals / name).read_bytes() for name in
               ("preflight.rs", "wal_preflight_cases.rs")}
    shims = sorted(build.glob("**/out/reviewed-storage.rs"))
    if not shims:
        raise ValueError("no compiled review shim found")
    for shim in shims:
        destination = output / "generated-source" / shim.relative_to(build)
        destination.parent.mkdir(parents=True, exist_ok=True)
        reviewed = shim.read_bytes()
        if not reviewed.startswith(main):
            raise ValueError("compiled review shim differs from archived original source")
        destination.write_bytes(reviewed)
        for name, original in modules.items():
            compiled = shim.with_name(name).read_bytes()
            if compiled != original:
                raise ValueError(f"compiled module differs from archived original: {name}")
            destination.with_name(name).write_bytes(compiled)


def isolated(value: Path) -> Path:
    path = value.resolve()
    if not path.is_relative_to(ARTIFACTS.resolve()) or path == ARTIFACTS.resolve():
        raise ValueError("output must be a new directory below artifacts/rust/storage-faults")
    return path


def durable_json(path: Path, value: dict) -> None:
    """Flush and close an exclusive receipt before starting the next phase."""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def logged_command(output: Path, env: dict, result: dict, name: str, arguments: list[str],
                   expected_code: int = 0) -> bytes:
    log = output / (name + ".log")
    print("Storage faults:", name, flush=True)
    with log.open("wb") as stream:
        code = subprocess.run(arguments, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600).returncode
    result["steps"][name] = {"command": arguments, "exit_code": code, "expected_exit_code": expected_code, "log": log.name}
    write_json(output / "result.json", result)
    if code != expected_code:
        raise RuntimeError(f"{name} failed ({code}): {log.read_text(errors='replace')[-4000:]}")
    return log.read_bytes()


def recovery_sources(fixtures: Path) -> list[Path]:
    sources = []
    for directory in (HERE, STORAGE, ROOT / "rust/crates/ifw-legacy", ROOT / "src/ImmichFolderWatch.Core", fixtures):
        sources += [p for p in directory.rglob("*") if p not in PROVIDER_FILES and p.is_file()
                    and not {"obj", "target", "__pycache__"}.intersection(p.relative_to(directory).parts)
                    and ("bin" not in p.relative_to(directory).parts or p.relative_to(directory).parts[:2] == ("src", "bin"))
                    and p.suffix != ".pyc"]
    return sources + [ROOT / name for name in ("LICENSE", "global.json", "Directory.Build.props", "Directory.Build.targets",
                      "NuGet.Config", "rust/Cargo.toml", "rust/toolchain-inputs.json", "tools/rust-qa/check-toolchain.py")]


def provider_sources() -> list[Path]:
    crate = ROOT / "rust/crates/safe-fs"
    return [*PROVIDER_FILES, ROOT / "rust/Cargo.toml", crate / "Cargo.toml", *sorted((crate / "src").glob("*.rs"))]


def provider_followup(output: Path, checkpoint: dict, env: dict, api, volume: str,
                      directory: Path, validate_volume) -> dict:
    """Keep optional preparation, execution and reporting failures local to the provider."""
    recovery = output / "recovery-before-provider.json"
    observed = {"format": "ifw-owned-fat-provider-v1", "status": "failed"}
    preparation = {"steps": {}}
    try:
        durable_json(recovery, checkpoint)
        observed["recovery_receipt_sha256"] = sha256(recovery)
        area = output / "provider-preparation"
        area.mkdir()
        files = provider_sources()
        hashes = export_source_snapshot(ROOT, area, files)
        preparation["source_index_sha256"] = sha256(area / "first-party-source-hashes.json")
        import windows_provider
        if windows_provider.require_recovery(recovery) != observed["recovery_receipt_sha256"]:
            raise ValueError("recovery receipt changed before provider preparation")
        command = partial(logged_command, area, env, preparation)
        command("format", ["rustfmt", "--edition", "2024", "--check", str(HERE / "fat_provider.rs")])
        command("controls", [sys.executable, str(HERE / "test_windows_provider.py"), "-v"])
        build = output / "build/provider"
        build.mkdir(parents=True)
        library, executable = build / "libsafe_fs.rlib", build / "ifw-fat-provider.exe"
        compiler = ["rustc", "--edition=2024", "--target", checkpoint["target"], "-Dwarnings"]
        command("library-build", [*compiler, "--crate-name", "safe_fs", "--crate-type=rlib",
                                  str(ROOT / "rust/crates/safe-fs/src/lib.rs"), "-o", str(library)])
        command("build", [*compiler, str(HERE / "fat_provider.rs"), "--extern", "safe_fs=" + str(library),
                          "-o", str(executable)])
        preparation["library_sha256"] = sha256(library)
        preparation["binary_sha256"] = sha256(executable)
        windows_provider.require_native_pe(executable, checkpoint["target"])
        for path in files:
            if sha256(path) != hashes[path.relative_to(ROOT).as_posix()]:
                raise ValueError("provider source changed during compilation")
        if sha256(executable) != preparation["binary_sha256"]:
            raise ValueError("provider executable changed after compilation")
        observed.update(windows_provider.run(executable, env, api, volume, directory, validate_volume, recovery))
    except Exception as error:
        observed["status"] = "failed"
        observed["error"] = f"{type(error).__name__}: {error}"
    observed["preparation"] = preparation
    try:
        durable_json(output / "windows-provider.json", observed)
    except Exception as error:
        observed["status"] = "failed"
        observed["receipt_error"] = f"{type(error).__name__}: {error}"
    return observed


def export_source_snapshot(repository: Path, output: Path, sources: list[Path]) -> dict:
    """Export only inventoried sources with visible paths and exact logical names.

    Artifact uploads omit dotfiles by default. Hidden logical paths therefore
    have a visible storage name derived from their UTF-8 logical path, with an
    explicit lookup table. Ordinary source paths and the logical hash index keep
    their existing format. Source bytes and notices are never transformed.
    """
    inventory = {source.relative_to(repository).as_posix(): source for source in sources}
    hashes, locations = {}, {}
    for logical in sorted(inventory):
        relative = Path(logical)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source must be inside the explicit repository inventory")
        if any(part.startswith(".") for part in relative.parts):
            key = hashlib.sha256(logical.encode("utf-8")).hexdigest()
            archived = Path("first-party-hidden-sources") / (key + ".source")
        else:
            archived = Path("first-party-sources") / relative
        destination = output / archived
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = sha256(inventory[logical])
        with inventory[logical].open("rb") as original, destination.open("xb") as copy:
            shutil.copyfileobj(original, copy)
        if sha256(destination) != expected:
            raise ValueError(f"exported source bytes differ: {logical}")
        hashes[logical] = expected
        locations[logical] = archived.as_posix()
    write_json(output / "first-party-source-hashes.json", hashes)
    write_json(output / "first-party-source-paths.json", locations)
    return hashes


def snapshot_check(output: Path, expected: str, phase: str) -> dict:
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError("invalid producer SHA-256")
    actual = sha256(output / "snapshot.db")
    if actual != expected:
        raise ValueError(f"SNAPSHOT_SHA256_MISMATCH at {phase}: retained backup differs from producer")
    return {"phase": phase, "sha256": actual}


def producer_anchor(events: list[dict]) -> str:
    """Require the earliest closed backup event, before its later confirmation."""
    sealed = [event for event in events if event["phase"] == "backup-completed" and event["file"] == "snapshot.db"]
    confirmed = [event for event in events if event["phase"] == "confirmed"]
    if (len(sealed) != 1 or len(confirmed) != 1 or events.index(sealed[0]) >= events.index(confirmed[0])
            or confirmed[0]["snapshot_sha256"] != sealed[0]["sha256"]):
        raise ValueError("missing or inconsistent original backup completion event")
    return sealed[0]["sha256"]


def capture_crash_files(output: Path, destination: str, *, include_shm: bool) -> dict:
    """Copy required DB/WAL bytes and optionally the transient WAL index."""
    raw = output / destination
    raw.mkdir()
    names = ["state.db", "state.db-wal"]
    if include_shm and (output / "state.db-shm").exists():
        names.append("state.db-shm")
    captured = {}
    for name in names:
        copy = raw / name
        shutil.copyfile(output / name, copy)
        captured[name] = {"bytes": copy.stat().st_size, "sha256": sha256(copy)}
    return captured


def compare_crash_files(before: dict, after: dict) -> list[str]:
    """Require exact byte continuity for every file captured before the kill."""
    for name, expected in before.items():
        if after.get(name) != expected:
            raise RuntimeError(f"hard kill unexpectedly changed quiescent SQLite file bytes: {name}")
    return sorted(before)


def kill_case(executable: Path, seed: Path, output: Path, mode: str, fault: str, env: dict) -> dict:
    """Kill only the owned child after its explicit native transaction barrier."""
    process = subprocess.Popen([str(executable), "worker", str(seed), str(output), mode, fault],
                               cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    lines: queue.Queue[str | None] = queue.Queue()
    events = []
    snapshot_checks = []
    anchor = None
    stderr = []

    def receive() -> None:
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    reader = threading.Thread(target=receive, daemon=True)
    errors = threading.Thread(target=lambda: stderr.append(process.stderr.read()), daemon=True)
    reader.start()
    errors.start()
    started = time.monotonic()
    try:
        confirmed = False
        while True:
            line = lines.get(timeout=max(0.01, 30 - (time.monotonic() - started)))
            if line is None:
                raise RuntimeError("worker exited before the requested crash barrier")
            event = json.loads(line)
            events.append(event)
            if event["phase"] == "backup-completed" and event["file"] == "snapshot.db":
                if anchor is not None:
                    raise RuntimeError("repeated snapshot producer event")
                anchor = event["sha256"]
                snapshot_checks.append(snapshot_check(output, anchor, "backup-completed"))
            if event["phase"] == "confirmed":
                confirmed = event["commit_returned"] is True
                if event["snapshot_sha256"] != anchor:
                    raise RuntimeError("confirmation changed the original snapshot digest")
            if event["phase"] == "kill-ready":
                if not confirmed or event["wal_bytes"] <= 32 or event["snapshot_sha256"] != anchor:
                    raise RuntimeError("missing confirmed transaction or actual WAL")
                snapshot_checks.append(snapshot_check(output, anchor, "before-hard-kill"))
                # Windows WAL-index byte locks prevent ordinary SHM reads while
                # the worker lives. Preserve DB/WAL now and SHM after termination,
                # always before recovery opens SQLite (sqlite.org/walformat.html).
                before = capture_crash_files(output, "before-kill", include_shm=os.name != "nt")
                process.kill()
                break
        code = process.wait(timeout=10)
        expected = -signal.SIGKILL if os.name != "nt" else 1
        if code != expected:
            raise RuntimeError(f"unexpected hard-kill exit status {code}")
        after = capture_crash_files(output, "after-kill-before-reopen", include_shm=True)
        compared = compare_crash_files(before, after)
        reader.join(timeout=5)
        errors.join(timeout=5)
        if producer_anchor(events) != anchor:
            raise RuntimeError("process event order changed the original snapshot digest")
        snapshot_checks.append(snapshot_check(output, anchor, "after-hard-kill-before-reopen"))
        return {"mechanism": "TerminateProcess" if os.name == "nt" else "SIGKILL",
                "exit_code": code, "events": events, "stderr": "".join(stderr),
                "snapshot_sha256": anchor, "snapshot_checks": snapshot_checks,
                "graceful_cleanup_ran": False,
                "pre_kill_shm_policy": "omitted-windows-mandatory-locks" if os.name == "nt" else "capture-if-present",
                "before_kill_files": before, "after_kill_files": after,
                "file_comparison": {"files": compared, "all_unchanged": True}}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    pins = json.loads((ROOT / "rust/toolchain-inputs.json").read_text())
    parser.add_argument("target", choices=sorted(pins["targets"]))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, default=ROOT / "artifacts/rust/storage-assessment/cargo-home")
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--tmpfs", action="store_true", help="Also run actual ENOSPC in private Linux 8-MiB tmpfs namespaces")
    parser.add_argument("--windows-vhd", action="store_true", help="Also exhaust an owned 16-MiB FAT16 VHD on disposable Windows")
    parser.add_argument("--local-qa-vm", action="store_true", help="Select the provisioned local Windows x64 guest for the VHD trial")
    parser.add_argument("--windows-provider", action="store_true", help="After all VHD recovery checks, observe ordinary safe-fs access through one private NTFS directory mount")
    args = parser.parse_args()
    if args.tmpfs and sys.platform != "linux":
        parser.error("--tmpfs is a native Linux experiment")
    if args.windows_vhd and os.name != "nt":
        parser.error("--windows-vhd requires a disposable native Windows candidate runner")
    if args.local_qa_vm and (not args.windows_vhd or args.target != "x86_64-pc-windows-msvc"):
        parser.error("--local-qa-vm requires the Windows x64 target and --windows-vhd")
    if args.windows_provider and not args.windows_vhd:
        parser.error("--windows-provider requires the existing --windows-vhd recovery")
    output = isolated(args.output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    build = output / "build"
    cargo_home = args.cargo_home.resolve()
    if not cargo_home.is_relative_to((ROOT / "artifacts/rust").resolve()):
        raise ValueError("Cargo cache must be in repository artifacts/rust")
    native_os = "windows" if os.name == "nt" else "linux"
    fixtures = ROOT / "rust/tests/fixtures/legacy" / native_os
    inputs = json.loads((STORAGE / "inputs.json").read_text())
    env = os.environ.copy()
    removed = []
    for key in list(env):
        if (key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "SQLITE_MAX_VARIABLE_NUMBER", "SQLITE_MAX_EXPR_DEPTH", "SQLITE_MAX_COLUMN", "CRATE_CC_NO_DEFAULTS"}
                or key.startswith(("CFLAGS", "CXXFLAGS", "CPPFLAGS", "ARFLAGS"))
                or key.endswith(("_CFLAGS", "_CXXFLAGS", "_CPPFLAGS", "_ARFLAGS", "_RUSTFLAGS"))):
            removed.append(key)
            del env[key]
    env.update({"CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(build / "rust"),
                "LIBSQLITE3_SYS_USE_PKG_CONFIG": "0", "LIBSQLITE3_FLAGS": inputs["sqlite"]["flags"],
                "CC_ENABLE_DEBUG_OUTPUT": "1", "IFW_ORACLE_EXPECT_ARCH": "arm64" if args.target.startswith("aarch64-") else "x64",
                "DOTNET_CLI_HOME": str(build / "dotnet-cli"), "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1"})
    result = {"format": "ifw-storage-faults-run-v1", "status": "running", "target": args.target,
              "host": platform.platform(), "steps": {}, "cases": [], "removed_override_names": removed,
              "limits": {"payload_bytes": 2097152, "additional_sqlite_pages": 16,
                         "command_timeout_seconds": 600, "kill_readiness_seconds": 30,
                         "tmpfs_watchdog_seconds": 30, "termination_wait_seconds": 10},
              "unproven": ["power loss", "physical disk ENOSPC", "application migration", "external side-effect rollback", "every transaction boundary", "other native hosts"]}
    if args.tmpfs:
        result["outer_namespaces"] = {name: os.readlink("/proc/self/ns/" + name) for name in ("user", "mnt", "net", "pid")}
        result["tmpfs_limit_bytes"] = 8388608
        result["bubblewrap_sha256"] = sha256(Path(shutil.which("bwrap")))
    if args.windows_vhd:
        result["windows_vhd_limit_bytes"] = 16777216
        result["limits"]["windows_volume_discovery_seconds"] = 30
        result["limits"]["windows_worker_seconds"] = 60

    command = partial(logged_command, output, env, result)

    try:
        if args.windows_vhd:
            windows_vhd.require_disposable_host(ROOT, env, args.local_qa_vm)
        command("native-toolchain", [sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"), args.target])
        expected_lock = {(item["name"], item["version"]): item["archive_sha256"] for item in inputs["packages"]}
        if external_lock(HERE / "Cargo.lock") != expected_lock or external_lock(STORAGE / "Cargo.lock") != expected_lock:
            raise ValueError("fault graph differs from the reviewed 31-package graph")
        verify_fixture(fixtures, native_os)
        metadata = json.loads(command("metadata", ["cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"), "--frozen", "--format-version", "1"]))
        counts = verify_sources(metadata, inputs, cargo_home, output)
        result["verified_archives"] = len(counts)
        result["verified_source_files"] = sum(counts.values())
        filtered = json.loads(command("native-graph", ["cargo", "metadata", "--manifest-path", str(HERE / "Cargo.toml"), "--frozen", "--format-version", "1", "--filter-platform", args.target]))
        if target_graph(filtered) != inputs["target_graphs"][args.target]:
            raise ValueError("native feature graph differs")
        hashes = export_source_snapshot(ROOT, output, recovery_sources(fixtures))
        result["first_party_sources"] = len(hashes)
        result["source_snapshot_paths"] = "first-party-source-paths.json"
        command("format", ["rustfmt", "--edition", "2024", "--check", str(HERE / "src/main.rs"), str(HERE / "build.rs")])
        command("windows-image-preparation-tests", [sys.executable, str(HERE / "test_windows_image.py"), "-v"])
        command("crash-capture-tests", [sys.executable, str(HERE / "test_crash_capture.py"), "-v"])
        command("source-snapshot-tests", [sys.executable, str(HERE / "test_source_snapshot.py"), "-v"])
        common = ["--manifest-path", str(HERE / "Cargo.toml"), "--frozen", "--target", args.target]
        command("clippy", ["cargo", "clippy", *common, "--all-targets", "--", "-D", "warnings"])
        command("build", ["cargo", "build", *common, "--release"])
        native_logs = sorted((build / "rust").glob("**/build/libsqlite3-sys/*/run/stdout"))
        if len(native_logs) != 2:
            raise ValueError("missing debug/release native SQLite compiler logs")
        for source in native_logs:
            if not all(flag in source.read_text(errors="replace") for flag in inputs["sqlite"]["flags"].split()):
                raise ValueError("SQLite compiler flags do not match the reviewed input")
            destination = output / "native-build-logs" / source.relative_to(build / "rust")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            shutil.copyfile(source.with_name("stderr"), destination.with_name("stderr"))
        result["native_compile_logs"] = len(native_logs)
        suffix = ".exe" if os.name == "nt" else ""
        binary = build / "rust" / args.target / "release" / ("ifw-storage-faults" + suffix)
        seed_binary = binary.with_name("ifw-reviewed-storage" + suffix)
        result["binaries"] = {binary.name: sha256(binary), seed_binary.name: sha256(seed_binary)}
        archive_reviewed_storage(build / "rust", output)
        seed = output / "seed"
        command("reviewed-seed", [str(seed_binary), str(fixtures), str(seed)])
        dotnet = str(Path(args.dotnet).resolve()) if Path(args.dotnet).is_file() else args.dotnet
        sdk_env = env.copy()
        if native_os == "linux":
            # NuGet can resolve an absent home relative to the project during restore.
            home = build / "dotnet-cli"
            for key, path in (("HOME", home), ("XDG_DATA_HOME", home / "data"),
                              ("XDG_CONFIG_HOME", home / "config"), ("XDG_CACHE_HOME", home / "cache")):
                path.mkdir(mode=0o700, parents=True, exist_ok=True)
                sdk_env[key] = str(path)
        sdk_command = partial(logged_command, output, sdk_env, result)
        project = HERE / "dotnet/FaultReadback.csproj"
        dotnet_common = [str(project), "--artifacts-path", str(build / "dotnet"), "-p:EnableWindowsTargeting=false"]
        sdk_command("csharp-restore", [dotnet, "restore", *dotnet_common, "--ignore-failed-sources", "-p:NuGetAudit=false"])
        sdk_command("csharp-build", [dotnet, "build", *dotnet_common, "--no-restore", "--configuration", "Release"])
        assembly = build / "dotnet/bin/FaultReadback/release/FaultReadback.dll"
        result["csharp_assembly_sha256"] = sha256(assembly)
        cases = output / "cases"
        cases.mkdir()
        def verify_case(name: str, case: Path, fault: str, events: list[dict]) -> None:
            anchor = producer_anchor(events)
            fault_evidence = json.loads((case / "fault.json").read_text())
            if (fault_evidence["snapshot_sha256"] != anchor
                    or any(event["snapshot_sha256"] != anchor for event in events if "snapshot_sha256" in event)):
                raise ValueError("raw fault marker changed original snapshot digest")
            checks = [snapshot_check(case, anchor, "before-rust")]
            command(name + "-verify", [str(binary), "verify", str(case), anchor])
            checks.append(snapshot_check(case, anchor, "after-rust"))
            checks.append(snapshot_check(case, anchor, "before-csharp"))
            sdk_command(name + "-csharp", [dotnet, str(assembly), str(case), anchor])
            checks.append(snapshot_check(case, anchor, "after-csharp"))
            readback = json.loads((case / "csharp-readback.json").read_text())
            if readback["Assertions"] != (32 if fault in ("enospc", "windows-full") else 24):
                raise ValueError("C# readback assertion count differs")
            verification = json.loads((case / "verification.json").read_text())
            if (not readback["RetainedSnapshotUnchanged"]
                    or any(verification[key] != anchor for key in ("snapshot_sha256", "snapshot_before_sha256", "snapshot_after_sha256", "snapshot_copy_sha256"))
                    or any(readback[key] != anchor for key in ("SnapshotSha256", "SnapshotBeforeSha256", "SnapshotAfterSha256", "SnapshotCopySha256"))):
                raise ValueError("retained pre-fault snapshot changed")
            # Exercise both actual preflight paths with an independently
            # corrupted copy, without giving either reader a new baseline.
            tampered = case / "tampered-snapshot"
            tampered.mkdir()
            shutil.copyfile(case / "snapshot.db", tampered / "snapshot.db")
            snapshot_check(tampered, anchor, "negative-copy-before-change")
            with (tampered / "snapshot.db").open("r+b") as stream:
                stream.seek(100)
                original_byte = stream.read(1)[0]
                stream.seek(100)
                stream.write(bytes([original_byte ^ 1]))
            changed_sha256 = sha256(tampered / "snapshot.db")
            if changed_sha256 == anchor:
                raise ValueError("negative control did not change actual snapshot bytes")
            for language, invoke, arguments, code in (
                    ("rust", command, [str(binary), "verify", str(tampered), anchor], 1),
                    ("csharp", sdk_command, [dotnet, str(assembly), str(tampered), anchor], 42)):
                rejected = invoke(name + "-tampered-" + language, arguments, code)
                if b"SNAPSHOT_SHA256_MISMATCH" not in rejected:
                    raise ValueError("tampered snapshot failed for an unrelated reason")
                if ({path.name for path in tampered.iterdir()} != {"snapshot.db"}
                        or sha256(tampered / "snapshot.db") != changed_sha256):
                    raise ValueError("rejected snapshot was opened or produced derived files")
            checks.append(snapshot_check(case, anchor, "after-negative-controls"))
            result["cases"].append({"name": name, "fault": fault_evidence,
                "producer_snapshot_sha256": anchor, "snapshot_checks": checks,
                "verification": verification, "csharp": readback,
                "byte_corruption_control": {"offset": 100, "original_byte": original_byte,
                    "changed_byte": original_byte ^ 1, "original_sha256": anchor, "changed_sha256": changed_sha256,
                    "rust_exit_code": 1, "csharp_exit_code": 42, "no_derived_files": True,
                    "rejected_before_sqlite_open": True}})
            write_json(output / "result.json", result)

        # Complete both casing modes before a platform-specific volume can report a missing capability.
        for fault in ("uncommitted", "commit-before-ack", "sqlite-full", *(["enospc"] if args.tmpfs else []),
                      *(["windows-full"] if args.windows_vhd else [])):
            for mode in ("sensitive", "insensitive"):
                name = mode + "-" + fault
                case = cases / name
                verified_before_provider = []
                if fault == "windows-full":
                    after_recovery = None
                    if args.windows_provider and mode == "insensitive":
                        def after_recovery(private, api, volume, directory, validate_volume):
                            # No provider setup or FAT writes until every existing
                            # recovery and cross-language control has completed.
                            verify_case(name, case, fault, private["events"])
                            for completed in result["cases"]:
                                completed["snapshot_checks"].append(snapshot_check(
                                    cases / completed["name"], completed["producer_snapshot_sha256"],
                                    "before-provider-after-all-cases"))
                            assertions = sum(item["csharp"]["Assertions"] for item in result["cases"])
                            if (len(result["cases"]), assertions) != (8, 208):
                                raise ValueError("incomplete recovery results before the optional provider")
                            checkpoint = {
                                "format": "ifw-before-provider-recovery-v1", "status": "passed",
                                "completed_cases": len(result["cases"]),
                                "csharp_assertions": assertions,
                                "original_snapshot_checks": len(result["cases"]),
                                "vhd_detach_and_final_readback_pending": True,
                                "target": args.target, "cases": result["cases"],
                                "source_index_sha256": sha256(output / "first-party-source-hashes.json")}
                            verified_before_provider.append(True)
                            observed = provider_followup(output, checkpoint, env, api, volume, directory, validate_volume)
                            result["provider_followup"] = observed
                            return {"status": observed["status"], "receipt": (
                                None if "receipt_error" in observed else "windows-provider.json")}
                    private = windows_vhd.run(binary, seed, case, mode, env, ROOT,
                                              after_recovery=after_recovery, local_vm=args.local_qa_vm)
                    result["steps"][name + "-volume"] = {"call": "windows_vhd.run", "exit_code": 0,
                        "expected_exit_code": 0, "receipt": str((case / "windows-vhd.json").relative_to(output))}
                    events = private["events"]
                elif fault == "enospc":
                    namespace_command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                        "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                        "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                        "--size", "8388608", "--tmpfs", "/fault", "--ro-bind", str(binary), "/probe",
                        "--ro-bind", str(seed), "/seed", "--ro-bind", str(HERE / "tmpfs.py"), "/runner.py",
                        "--bind", str(cases), "/evidence", "--clearenv", "--setenv", "PATH", "/usr/bin",
                        "--setenv", "HOME", "/tmp", "--setenv", "LC_ALL", "C.UTF-8",
                        "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--chdir", "/tmp", "--",
                        "/usr/bin/python3", "/runner.py", "/evidence/" + name, mode]
                    command(name + "-namespace", namespace_command)
                    private = json.loads((case / "tmpfs.json").read_text())
                    if any(private["namespaces"][name] == identity for name, identity in result["outer_namespaces"].items()):
                        raise ValueError("ENOSPC namespace did not isolate all required surfaces")
                    events = private["events"]
                elif fault == "sqlite-full":
                    raw = command(name + "-fault", [str(binary), "worker", str(seed), str(case), mode, fault])
                    events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
                else:
                    killed = kill_case(binary, seed, case, mode, fault, env)
                    write_json(case / "process-kill.json", killed)
                    events = killed["events"]
                if not verified_before_provider:
                    verify_case(name, case, fault, events)
        # Compare actual originals after every reader/negative trial has finished,
        # using the early producer anchors retained in memory, never a late hash.
        for case_result in result["cases"]:
            case_result["snapshot_checks"].append(snapshot_check(
                cases / case_result["name"], case_result["producer_snapshot_sha256"], "deferred-after-all-cases"))
        result["deferred_original_snapshot_checks"] = len(result["cases"])
        result["status"] = "passed"
        print("Storage faults passed:", output, flush=True)
    except Exception as error:
        result["status"] = "unavailable" if isinstance(error, windows_vhd.Unavailable) else "failed"
        result["error"] = str(error)
        traceback.print_exc()
    finally:
        if args.windows_provider:
            result["selected_checks_status"] = (result.get("provider_followup", {}).get("status", "not-run")
                                                 if result["status"] == "passed" else result["status"])
        write_json(output / "result.json", result)
        write_json(output / "evidence-hashes.json", evidence_inventory(output))
    status = result.get("selected_checks_status", result["status"])
    return 0 if status == "passed" else (2 if status == "unavailable" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
