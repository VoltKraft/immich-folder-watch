"""Build the assessment offline and retain its exact native source and input binding."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

import source_profile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUT = ROOT / "artifacts/rust"


def sha(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def main(args):
    toolchain = args.toolchain.resolve(strict=True)
    registry = args.registry.resolve(strict=True)
    fonts = ROOT / "rust/assets/fonts"
    profile = source_profile.prepare(fetch=False, registry=registry)
    subprocess.run([sys.executable, str(ROOT / "tools/rust-qa/verify-gui-inputs.py")], check=True)
    target = f"{platform.machine()}-unknown-linux-gnu"
    version = subprocess.check_output([sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"),
                                       target, "--rustc", str(toolchain / "bin/rustc")], text=True)
    build = OUTPUT / "gui-build"
    build.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=build) as home:
        (Path(home) / "registry").symlink_to(registry, target_is_directory=True)
        audit_env = dict(os.environ, PATH=str(toolchain / "bin") + os.pathsep + os.environ["PATH"],
                         CARGO_HOME=home, CARGO_TARGET_DIR=str(build))
        _, graph_sha = source_profile.verify_native_graph(target, audit_env)
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
    command += ["--ro-bind", str(registry), "/cargo/registry", "--ro-bind", str(toolchain), "/toolchain",
                "--ro-bind", str(ROOT / "rust"), "/project/rust", "--ro-bind", str(HERE), "/project/tools/rust-qa/gui",
                "--ro-bind", str(fonts), "/fonts", "--bind", str(build), "/build",
                "--setenv", "IFW_QA_FONT_DIR", "/fonts", "--setenv", "HOME", "/test-home",
                "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "CARGO_HOME", "/cargo",
                "--setenv", "CARGO_TARGET_DIR", "/build", "--chdir", "/project/tools/rust-qa/gui",
                "--", "/toolchain/bin/cargo"]
    if args.clippy:
        subprocess.run([*command, "clippy", "--frozen", "--all-targets", "--jobs", str(args.jobs),
                        "--", "-D", "warnings"], check=True)
        return
    subprocess.run([*command, "build", "--release", "--frozen", "--jobs", str(args.jobs)], check=True)
    sources = [HERE / "Cargo.toml", HERE / "Cargo.lock", *sorted((HERE / "src").glob("*.rs")),
               ROOT / "rust/Cargo.toml", ROOT / "rust/crates/desktop-lifecycle/Cargo.toml",
               ROOT / "rust/crates/desktop-lifecycle/src/lib.rs"]
    binary = build / "release/native-gui-assessment"
    record = {"rustc": version.strip(), "target": target, "command": "cargo build --release --frozen",
              "binary_sha256": sha(binary), "fonts": {p.name: sha(p) for p in sorted(fonts.glob("*.ttf"))},
              "font_notice": sha(fonts / "OFL-1.1.txt"),
              "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}}
    record["graphSha256"] = graph_sha
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
    parser.add_argument("--registry", type=Path, default=OUTPUT / "assessment-cache/registry",
                        help="An offline Cargo registry directory containing all locked crate archives")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--clippy", action="store_true", help="Lint every native fixture target with warnings denied")
    main(parser.parse_args())
