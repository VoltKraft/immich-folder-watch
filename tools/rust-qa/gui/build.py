"""Build the assessment offline and retain its exact native source and input binding."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

import source_profile
from compiler_inputs import linux_project_sources, verify_gui_units
from startup import vendor


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUT = ROOT / "artifacts/rust"


def sha(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def source_digests(paths):
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}


def main(args):
    toolchain = args.toolchain.resolve(strict=True)
    registry = args.registry.resolve(strict=True)
    fonts = ROOT / "rust/assets/fonts"
    profile = source_profile.prepare(fetch=False, registry=registry)
    directory = vendor.compiler_directory(registry)
    subprocess.run([sys.executable, str(ROOT / "tools/rust-qa/verify-gui-inputs.py")], check=True)
    target = f"{platform.machine()}-unknown-linux-gnu"
    version = subprocess.check_output([sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"),
                                       target, "--rustc", str(toolchain / "bin/rustc")], text=True)
    build = args.output.resolve()
    if build == OUTPUT or not build.is_relative_to(OUTPUT.resolve()):
        raise ValueError("Use a build directory below artifacts/rust")
    build.mkdir(exist_ok=True, parents=True)
    sources = linux_project_sources(ROOT)
    with tempfile.TemporaryDirectory(dir=build) as home:
        vendor.configure_cargo_home(Path(home), directory)
        audit_env = dict(os.environ, PATH=str(toolchain / "bin") + os.pathsep + os.environ["PATH"],
                         CARGO_HOME=home, CARGO_TARGET_DIR=str(build))
        graph_file = Path(home) / "graph.json" if args.clippy or args.test else build / "gui-graph.json"
        _, graph_sha = source_profile.verify_native_graph(target, audit_env, graph_file, directory_source=directory)
        packages = json.loads(graph_file.read_bytes())["packages"]
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--dir", "/test-home", "--dir", "/cargo"]
    for name in ("bin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            command += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            command += ["--ro-bind", str(path), str(path)]
    for path in ("/etc/alternatives", "/etc/ld.so.cache"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    command += ["--ro-bind", str(source_profile.FONTS), "/fallback-fonts",
                    "--setenv", "IFW_QA_FALLBACK_DIR", "/fallback-fonts"]
    if HERE.parent / "yaml/Cargo.toml" in sources:
        command += ["--ro-bind", str(HERE.parent / "yaml"), "/project/tools/rust-qa/yaml"]
    command += ["--ro-bind", str(directory), "/vendor", "--ro-bind", str(toolchain), "/toolchain",
                "--ro-bind", str(ROOT / "rust"), "/project/rust", "--ro-bind", str(HERE), "/project/tools/rust-qa/gui",
                "--ro-bind", str(fonts), "/fonts", "--bind", str(build), "/build",
                "--setenv", "IFW_QA_FONT_DIR", "/fonts", "--setenv", "HOME", "/test-home",
                "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "CARGO_HOME", "/cargo",
                "--setenv", "CARGO_TARGET_DIR", "/build", "--chdir", "/project/tools/rust-qa/gui"]
    cargo = ["--", "/toolchain/bin/cargo"]
    selection = ["--config", 'source.crates-io.replace-with="combined-review"',
                 "--config", 'source.combined-review.directory="/vendor"']
    if args.clippy:
        subprocess.run([*command, *cargo, "clippy", *selection, "--frozen", "--all-targets", "--jobs", str(args.jobs),
                        "--", "-D", "warnings"], check=True)
        return
    if args.test:
        # The private test bus resolves the namespace UID for D-Bus EXTERNAL authentication.
        with tempfile.TemporaryDirectory(dir=build) as temporary:
            passwd, group = Path(temporary) / "passwd", Path(temporary) / "group"
            passwd.write_text(f"qa:x:{os.getuid()}:{os.getgid()}:Synthetic GUI:/test-home:/bin/false\n")
            group.write_text(f"qa:x:{os.getgid()}:\n")
            subprocess.run([*command, "--ro-bind", str(passwd), "/etc/passwd", "--ro-bind", str(group), "/etc/group",
                            *cargo, "test", *selection, "--release", "--frozen", "--jobs", str(args.jobs)], check=True)
        return
    drivers = [Path(__file__).resolve(), HERE / "compiler_inputs.py", HERE / "startup/vendor.py",
               HERE / "source_profile.py", HERE.parent / "combined-profile/sources.py", HERE.parent / "yaml/prepare.py",
               HERE.parent / "audit-graph.py", HERE.parent / "storage/evidence.py"]
    original_sources = source_digests(sources)
    original_drivers = source_digests(drivers)
    log = build / "gui-compiler.jsonl"
    with log.open("wb") as stream:
        subprocess.run([*command, *cargo, "build", *selection, "--release", "--frozen", "--jobs", str(args.jobs),
                        "--message-format=json-render-diagnostics"], stdout=stream, check=True)
    expected = {p["name"] + " v" + p["version"]: p["featureSets"] for p in packages}
    units = verify_gui_units(log, expected)
    if source_digests(sources) != original_sources or source_digests(drivers) != original_drivers:
        raise ValueError("The native GUI sources or compiler drivers changed during compilation")
    binary = build / "release/native-gui-assessment"
    record = {"rustc": version.strip(), "target": target, "command": "cargo build --release --frozen",
              "binary_sha256": sha(binary), "fonts": {p.name: sha(p) for p in sorted(fonts.glob("*.ttf"))},
              "font_notice": sha(fonts / "OFL-1.1.txt"),
              "sources": original_sources}
    record["graphSha256"] = graph_sha
    registry_receipt = build / "gui-registry-sources.json"
    shutil.copyfile(directory.parents[2] / "registry-sources.json", registry_receipt)
    record["registryReceiptSha256"] = sha(registry_receipt)
    if record["registryReceiptSha256"] != vendor.GUI_LOCK_RECEIPTS[original_sources["tools/rust-qa/gui/Cargo.lock"]]:
        raise ValueError("The GUI directory-source receipt changed during compilation")
    record["compilerStreamSha256"] = sha(log)
    record["compilerUnits"] = units
    record["compilerDrivers"] = original_drivers
    record["fallbackFonts"] = {name: asset["sha256"] for name, asset in profile["fonts"].items()}
    record["sourceTrees"] = profile["trees"]
    record["textNotices"] = profile["noticeFiles"]
    record["sourceProfileSha256"] = source_profile.sha(source_profile.REVIEW)
    record["sourceReconstructionSha256"] = sha(Path(source_profile.__file__))
    binary.with_suffix(".inputs.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"{target} {record['binary_sha256']} {binary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=OUTPUT / "toolchain")
    parser.add_argument("--output", type=Path, default=OUTPUT / "gui-build",
                        help="Build directory for this isolated comparison")
    parser.add_argument("--registry", type=Path, default=OUTPUT / "assessment-cache/registry",
                        help="An offline Cargo registry directory containing all locked crate archives")
    parser.add_argument("--jobs", type=int, default=4)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--clippy", action="store_true", help="Lint every native fixture target with warnings denied")
    mode.add_argument("--test", action="store_true", help="Run native GUI library and adapter checks offline")
    main(parser.parse_args())
