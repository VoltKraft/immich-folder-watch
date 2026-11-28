"""Verify reviewed realtime inputs and exercise the real native client on loopback."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
sys.path.insert(0, str(QA / "storage"))
from evidence import sha256, verify_archive
import hyper_util_source


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_graph(graph, inputs, metadata, cargo_home):
    canonical = canonical_digest(graph)
    if canonical != inputs["graphs"][graph["target"]]["sha256"]:
        raise ValueError("Resolved target graph does not match the reviewed graph")
    reviewed = {(p["name"], p["version"]): p for p in inputs["packages"]}
    sources = {(p["name"], p["version"]): Path(p["manifest_path"]).parent for p in metadata["packages"]
               if p["source"]}
    count = files = notices = rebuilt = 0
    for package in graph["packages"]:
        if not package["source"] and "reconstructedSource" not in package:
            continue
        key = package["name"], package["version"]
        entry = reviewed[key]
        if (entry["archiveSha256"] != package["archiveSha256"] or entry["notices"] != package["notices"]
                or entry["declared"] != package["license"]):
            raise ValueError(f"Reviewed source or notice differs for {key}")
        if "reconstructedSource" in package:
            if key != ("hyper-util", "0.1.21"):
                raise ValueError("Unexpected reconstructed transport input")
            target = hyper_util_source.verify(hyper_util_source.ARCHIVE, hyper_util_source.SOURCE)
            if target != package["reconstructedSource"]:
                raise ValueError("CONNECT metadata source differs from the resolved graph")
            files += target["fileCount"]
            notices += len(target["notices"])
            rebuilt += 1
            continue
        source = sources[key]
        registry = cargo_home / "registry"
        if not source.is_relative_to(registry / "src"):
            raise ValueError("Source is outside the dedicated Cargo registry")
        archive = registry / "cache" / source.parent.name / (source.name + ".crate")
        files += verify_archive(archive, source, entry["archiveSha256"])
        count += 1
        notices += len(entry["notices"])
    if rebuilt != 1:
        raise ValueError("Missing reconstructed CONNECT metadata source")
    return {"canonicalInventorySha256": canonical, "registryPackages": count, "reconstructedPackages": rebuilt,
            "verifiedUnpackedFiles": files, "verifiedNotices": notices}


def main():
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["graphs"]))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cargo-home", type=Path, default=ROOT / "artifacts/rust/realtime-cargo")
    parser.add_argument("--offline", action="store_true", help="use the already-populated isolated Cargo cache")
    parser.add_argument("--build-only", action="store_true",
                        help="compile the Windows x64 subject and unit executable for a separate native test guest")
    args = parser.parse_args()
    if args.build_only and args.target != "x86_64-pc-windows-msvc":
        parser.error("--build-only requires the Windows x64 compiler host")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output directory to keep individual native results separate")
    output.mkdir(parents=True, exist_ok=True)
    target_dir = ROOT / "artifacts/rust/realtime-build" / args.target
    cargo_home = args.cargo_home.resolve()
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith(("CARGO_", "RUSTC_", "RUSTDOC", "RING_"))
                   or k in {"RUSTFLAGS", "RUSTC", "CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS"})}
    env.update(CARGO_HOME=str(cargo_home), CARGO_TARGET_DIR=str(target_dir), GIT_OPTIONAL_LOCKS="0")
    manifest = HERE / "Cargo.toml"
    record = {"target": args.target, "lockSha256": sha256(HERE / "Cargo.lock"), "steps": {},
              "sourceFiles": {}, "workflowRun": os.getenv("GITHUB_RUN_ID")}
    if args.build_only:
        record["mode"] = "build-only"
    for file in sorted([p for p in HERE.glob("*") if p.is_file()] + list((HERE / "src").glob("*.rs"))
                       + list((ROOT / "rust/crates/ifw-immich/src").glob("*.rs"))
                       + [ROOT / "rust/Cargo.toml", ROOT / "rust/crates/ifw-immich/Cargo.toml",
                          ROOT / "rust/toolchain-inputs.json", QA / "audit-graph.py", QA / "check-toolchain.py",
                          QA / "storage/evidence.py"]):
        record["sourceFiles"][file.relative_to(ROOT).as_posix()] = sha256(file)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    record["head"] = revision.stdout.strip() if revision.returncode == 0 else None
    if record["lockSha256"] != inputs["lockSha256"]:
        raise ValueError("Lockfile does not match the reviewed network profile")

    def step(name, command, timeout=900):
        with (output / (name + ".txt")).open("wb") as stream:
            print("Running " + name, flush=True)
            try:
                status = subprocess.run(command, cwd=HERE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                status = 124
        record["steps"][name] = status
        if status:
            raise RuntimeError(f"{name} failed ({status}), see {output / (name + '.txt')}")

    try:
        original = hyper_util_source.original(cargo_home, fetch=not args.offline)
        record["reconstructedHyperUtil"] = hyper_util_source.reconstruct(original, hyper_util_source.SOURCE)
        shutil.copyfile(original, output / original.name)
        shutil.copyfile(hyper_util_source.PATCH, output / hyper_util_source.PATCH.name)
        shutil.copyfile(hyper_util_source.SOURCE / "LICENSE", output / "hyper-util-0.1.21-LICENSE.txt")
        step("compiler", [sys.executable, QA / "check-toolchain.py", args.target])
        if not args.offline:
            step("fetch", ["cargo", "fetch", "--locked", "--manifest-path", manifest])
        step("inventory", [sys.executable, QA / "audit-graph.py", manifest, args.target, output / "graph.json"])
        metadata = json.loads(subprocess.check_output(
            ["cargo", "metadata", "--frozen", "--format-version", "1", "--manifest-path", manifest], cwd=HERE, env=env))
        graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
        record["inputs"] = verify_graph(graph, inputs, metadata, cargo_home)
        if args.build_only:
            step("unit-build", ["cargo", "test", "--frozen", "--no-run", "--message-format=json"])
            messages = (output / "unit-build.txt").read_text(encoding="utf-8").splitlines()
            units = [message["executable"] for line in messages if line.startswith("{")
                     and (message := json.loads(line)).get("reason") == "compiler-artifact"
                     and message["profile"]["test"] and message["target"]["name"] == "ifw-realtime-probe"
                     and message["executable"]]
            if len(units) != 1:
                raise ValueError("Expected one compiled realtime unit test executable")
            shutil.copy2(units[0], output / "ifw-realtime-unit.exe")
        else:
            step("format", ["cargo", "fmt", "--all", "--check"])
            step("unit", ["cargo", "test", "--frozen"])
            step("clippy", ["cargo", "clippy", "--frozen", "--all-targets", "--", "-D", "warnings"])
        step("build", ["cargo", "build", "--frozen", "--release"])
        binary = target_dir / "release" / ("ifw-realtime-probe.exe" if os.name == "nt" else "ifw-realtime-probe")
        if os.name == "nt":
            # Replay the compiler's actual executable alongside the installed reference.
            binary = Path(shutil.copy2(binary, output / binary.name))
        if not args.build_only:
            step("sessions", [sys.executable, HERE / "verify.py", "--probe", binary, "--output", output / "sessions.json"])
        record["passed"] = True
    finally:
        record.setdefault("passed", False)
        record["outputs"] = {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "result.json"}
        (output / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
