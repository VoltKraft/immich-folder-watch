"""Stage a Linux GUI, bounded inventory worker and optional Vulkan observer from reviewed inputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust"


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--vendor", type=Path, default=ART / "yaml-assessment/source-review-01/vendor")
    parser.add_argument("--gui", type=Path, default=ART / "gui-build/release/native-gui-assessment")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.name):
        raise ValueError("A simple staging label is required")
    output = ART / "performance/subjects" / args.name
    if output.exists():
        raise FileExistsError(output)
    target = platform.machine() + "-unknown-linux-gnu"
    toolchain = ART / "toolchain"
    subprocess.run([sys.executable, str(HERE.parent / "check-toolchain.py"), target,
                    "--rustc", str(toolchain / "bin/rustc")], check=True)
    source_inputs = HERE.parent / "yaml/inputs.json"
    reviewed = json.loads(source_inputs.read_text())
    packages = {(p["name"], p["version"]): p for p in reviewed["packages"]}
    profile = {(p["name"], p["version"]): set(p["features"]) for p in reviewed["target_graphs"][target]}
    gui_receipt = args.gui.with_suffix(".inputs.json")
    gui_inputs = json.loads(gui_receipt.read_text())
    if gui_inputs["binary_sha256"] != sha(args.gui):
        raise ValueError("The GUI binary does not match its source receipt")
    build = ART / "performance/worker-build"
    build.mkdir(parents=True, exist_ok=True)
    config = build / "cargo-offline.toml"
    config.write_text('[source.crates-io]\nreplace-with = "reviewed"\n[source.reviewed]\ndirectory = "/vendor"\n')
    mount = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
             "--ro-bind", "/usr", "/usr", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
             "--dir", "/cargo", "--ro-bind", str(config), "/cargo/config.toml", "--dir", "/test-home",
             "--ro-bind", str(toolchain), "/toolchain",
             "--ro-bind", str(args.vendor.resolve(strict=True)), "/vendor", "--bind", str(build), "/build",
             "--ro-bind", str(ROOT / "rust"), "/project/rust", "--ro-bind", str(HERE), "/project/tools/rust-qa/performance",
             "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "HOME", "/test-home",
             "--setenv", "CARGO_HOME", "/cargo", "--setenv", "CARGO_TARGET_DIR", "/build"]
    for name in ("/bin", "/lib", "/lib64"):
        path = Path(name)
        if path.is_symlink():
            mount += ["--symlink", os.readlink(path), name]
        elif path.is_dir():
            mount += ["--ro-bind", name, name]
    for name in ("/etc/ld.so.cache", "/etc/alternatives"):
        if Path(name).exists():
            mount += ["--ro-bind", name, name]
    mount += ["--chdir", "/project/tools/rust-qa/performance/worker", "--"]
    cargo = [*mount, "/toolchain/bin/cargo"]
    meta = json.loads(subprocess.check_output([*cargo, "metadata", "--frozen", "--format-version", "1",
                                               "--filter-platform", target]))
    by_id = {p["id"]: p for p in meta["packages"]}
    closure = []
    for node in meta["resolve"]["nodes"]:
        p = by_id[node["id"]]
        if not p["source"]:
            continue
        key = p["name"], p["version"]
        if key not in profile or not set(node["features"]) <= profile[key]:
            raise ValueError(f"Unreviewed worker input {key} with features {node['features']}")
        directory = args.vendor / f"{key[0]}-{key[1]}"
        checks = json.loads((directory / ".cargo-checksum.json").read_text())
        canonical = (json.dumps(checks["files"], sort_keys=True, separators=(",", ":")) + "\n").encode()
        if (hashlib.sha256(canonical).hexdigest() != packages[key]["filtered_tree_sha256"]
                or checks["package"] != packages[key]["archive_sha256"]):
            raise ValueError(f"Changed filtered source manifest for {key}")
        actual = {x.relative_to(directory).as_posix(): sha(x) for x in directory.rglob("*")
                  if x.is_file() and x.name != ".cargo-checksum.json"}
        if actual != checks["files"]:
            raise ValueError(f"Changed filtered source content for {key}")
        closure.append({"name": key[0], "version": key[1], "features": node["features"]})
    subprocess.run([*cargo, "clippy", "--frozen", "--all-targets", "--", "-D", "warnings"], check=True)
    subprocess.run([*cargo, "build", "--frozen", "--release"], check=True)
    subprocess.run([*mount, "/toolchain/bin/rustc", "--edition", "2024", "--crate-type", "cdylib", "-O",
                    "-D", "warnings", "-Clink-arg=-Wl,-z,nodelete", "-Clink-arg=-Wl,-soname,libvulkan.so.1",
                    "../present.rs", "-o", "/build/present-observer.so"], check=True)
    output.mkdir(parents=True)
    observer = output / "observer/libvulkan.so.1"
    observer.parent.mkdir()
    shutil.copy2(build / "present-observer.so", observer)
    worker = output / "ifw-performance-worker"
    shutil.copy2(build / "release/ifw-performance-worker", worker)
    shutil.copy2(args.gui, output / "native-gui-assessment")
    shutil.copy2(gui_receipt, output / "native-gui-assessment.inputs.json")
    sources = [*sorted((HERE / "worker").rglob("*.rs")), HERE / "worker/Cargo.toml", HERE / "worker/Cargo.lock",
               HERE / "present.rs", HERE / "build_worker.py", source_inputs, ROOT / "rust/Cargo.toml",
               ROOT / "rust/crates/safe-fs/Cargo.toml", *sorted((ROOT / "rust/crates/safe-fs/src").glob("*.rs"))]
    record = {"worker_sha256": sha(worker), "observer_sha256": sha(observer), "gui_sha256": sha(args.gui),
              "sources": {x.relative_to(ROOT).as_posix(): sha(x) for x in sources}, "resolved": closure}
    (output / "worker.inputs.json").write_text(json.dumps(record, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
