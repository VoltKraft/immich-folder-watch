"""Stage the ordinary HWND retention change beside a source-verified, existing Windows GUI build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
GUI = QA / "gui"
AREA = ROOT / "artifacts/rust/windows-warm-window"
TARGETS = ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
ORIGINALS = {
    "main.rs": "f8e39611a025754a01bb006936220a7526f67437d15e1f8960f373adb89d6d93",
    "native_window.rs": "68f5025187929bea6121de9b5aca6d821a80cf0156406837fa9188c71399641f",
    "graphics.rs": "d13c3087261770a73f3e904d677b71ace1deba6efce47f68061f3a40184d828e",
}
sys.path.insert(0, str(QA))
from gui import source_profile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(project):
    gui = project / "tools/rust-qa/gui"
    for name, expected in ORIGINALS.items():
        if sha(GUI / "src" / name) != expected:
            raise ValueError(f"Review the change against the new canonical {name}")
    gui.mkdir(parents=True)
    for name in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(GUI / name, gui / name)
    shutil.copytree(GUI / "src", gui / "src")
    # Cargo's first-party paths and the reconstructed, audited text source trees retain their layout.
    shutil.copytree(GUI / "artifacts/text", gui / "artifacts/text")
    lifecycle = project / "rust/crates/desktop-lifecycle"
    shutil.copytree(ROOT / "rust/crates/desktop-lifecycle", lifecycle)
    shutil.copyfile(ROOT / "rust/Cargo.toml", project / "rust/Cargo.toml")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(project.parent)}
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    command = ["git", "apply", "--whitespace=error", str(HERE / "candidate.patch")]
    subprocess.run([*command, "--check"], cwd=gui, env=env, check=True)
    subprocess.run(command, cwd=gui, env=env, check=True)
    shutil.copyfile(HERE / "loop_wake.rs", gui / "src/loop_wake.rs")
    return gui


def feature_rows(manifest, target, env):
    tree = subprocess.check_output(["cargo", "tree", "--frozen", "--workspace", "--target", target, "--edges", "normal,build",
                                    "--prefix", "none", "--format", "{p}|{f}", "--manifest-path", str(manifest)],
                                   env=env, text=True)
    rows = set()
    for line in tree.splitlines():
        if line == "[build-dependencies]":
            continue
        package, features = line.removesuffix(" (*)").split("|")
        name, version, *_ = package.split()
        rows.add((name, version, tuple(sorted(filter(None, features.split(","))))))
    return sorted(rows)


def main(target):
    if os.name != "nt" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted" or os.getenv("GITHUB_ACTIONS") != "true":
        raise ValueError("Build this native comparison on a disposable Windows rewrite runner")
    output = AREA / target
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    ordinary_path = ROOT / f"artifacts/rust/gui-native/{target}/build.json"
    ordinary = json.loads(ordinary_path.read_text(encoding="utf-8"))
    canonical = ROOT / "artifacts/rust/gui-build/release/native-gui-assessment.exe"
    if (ordinary["source"] != revision or ordinary["target"] != target or ordinary["binarySha256"] != sha(canonical)
            or any(sha(ROOT / name) != digest for name, digest in ordinary["compilerSources"].items())):
        raise ValueError("The ordinary native build does not match this checkout")
    cache = ROOT / "artifacts/rust/assessment-cache"
    approved = source_profile.prepare(fetch=False, registry=cache / "registry")
    subprocess.run([sys.executable, str(QA / "verify-gui-inputs.py")], check=True)
    gui = stage(output / "project")
    env = dict(os.environ, CARGO_HOME=str(cache), CARGO_TARGET_DIR=str(output / "build"),
               IFW_QA_FONT_DIR=str(ROOT / "rust/assets/fonts"), IFW_QA_FALLBACK_DIR=str(source_profile.FONTS))
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), target], check=True)
    manifest = str(gui / "Cargo.toml")
    lock, graph = source_profile.verify_native_graph(target, env)
    selected = feature_rows(gui / "Cargo.toml", target, env)
    if (lock != ordinary["lockSha256"] or graph != ordinary["graphSha256"] or sha(gui / "Cargo.lock") != lock
            or sha(gui / "Cargo.toml") != sha(GUI / "Cargo.toml") or selected != feature_rows(GUI / "Cargo.toml", target, env)
            or any(source_profile.tree_info(gui / "artifacts/text" / name) != info for name, info in approved["trees"].items())):
        raise ValueError("Unexpected canonical native dependency graph")
    subprocess.run(["cargo", "fmt", "--manifest-path", manifest, "--", "--check"], env=env, check=True)
    subprocess.run(["cargo", "clippy", "--manifest-path", manifest, "--frozen", "--all-targets", "--", "-D", "warnings"],
                   cwd=gui, env=env, check=True)
    subprocess.run(["cargo", "build", "--manifest-path", manifest, "--frozen", "--release"], cwd=gui, env=env, check=True)
    exe = output / "build/release/native-gui-assessment.exe"
    record = dict(target=target, revision=revision, baselineReceipt=sha(ordinary_path), baseline=sha(canonical), binary=sha(exe),
                  graph=graph, lock=lock, selectedFeatureRows=len(selected), canonicalInputs=ORIGINALS,
                  baseFonts={p.name: sha(p) for p in sorted((ROOT / "rust/assets/fonts").glob("*.ttf"))},
                  fallbackFonts={name: asset["sha256"] for name, asset in approved["fonts"].items()},
                  compilerInputs={p.name: sha(p) for p in [*sorted((gui / "src").glob("*.rs")), gui / "src/tray-icon.argb"]},
                  variantInputs={p.name: sha(p) for p in (HERE / "candidate.patch", HERE / "loop_wake.rs", Path(__file__))})
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{target} {record['binary']} {exe}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    main(parser.parse_args().target)
