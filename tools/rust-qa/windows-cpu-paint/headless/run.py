"""Run the real GUI's six frames headlessly with the frozen Linux CPU Vulkan profile."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA))
sys.path.insert(0, str(HERE.parent))
import upstream
from gui import source_profile

from pixels import compare


GUI = QA / "gui"
SUBJECT_SHA = "650a20201c02196d9b483d880bd3abe9f80f974830bcebd0dd0c2fc51b8b5fc0"
LOCK_SHA = "55959e8ab77241da561ad189b53f75b3cba769a917ef47c8aa6b0acf9e304ae9"
AREA = ROOT / "artifacts/rust"
SCOPE = AREA / "egui-cpu-assessment"
ICD = Path("/usr/share/vulkan/icd.d/lvp_icd.x86_64.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(out):
    if sha(GUI / "src/main.rs") != SUBJECT_SHA:
        raise ValueError("The ordinary application's source differs from the qualified Window::ui")
    out.mkdir()
    (out / "artifacts").mkdir()
    shutil.copytree(GUI / "src", out / "src")
    for name in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(GUI / name, out / name)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero",
                    "--whitespace=error", str(HERE / "test-view.patch")], cwd=out, check=True)
    for name in ("cpu_view_observation.rs", "view_gpu_reference.rs"):
        shutil.copyfile(HERE / name, out / "src" / name)
    if sha(out / "Cargo.lock") != LOCK_SHA:
        raise ValueError("The headless test's lockfile changed")


def run(cache, build):
    if sys.platform != "linux" or platform.machine() != "x86_64" or not ICD.is_file():
        raise ValueError(f"This headless reference requires Linux x64 and {ICD}")
    build = build.resolve()
    if not build.is_relative_to(AREA) or build == AREA:
        raise ValueError("The writable build cache must be inside artifacts/rust/")
    compiler = subprocess.check_output([sys.executable, str(QA / "check-toolchain.py"),
                                        "x86_64-unknown-linux-gnu", "--rustc", str(AREA / "toolchain/bin/rustc")],
                                       text=True).strip()
    prepared = upstream.prepare(cache)
    source_profile.validate()
    font_catalog = json.loads((ROOT / "rust/audit/gui-inputs.json").read_bytes())["files"]
    base_fonts = {row["path"]: row["sha256"] for row in font_catalog if row["path"].endswith(".ttf")}
    for filename, checksum in base_fonts.items():
        upstream.checked(ROOT / "rust" / filename, checksum)
    build.mkdir(parents=True, exist_ok=True)
    trial = Path(tempfile.mkdtemp(prefix="headless-", dir=SCOPE))
    source = trial / "source"
    pixels = trial / "pixels"
    pixels.mkdir()
    stage(source)
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache", "--dev", "/dev",
            "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/test-home", "--dir", "/cargo",
            "--setenv", "HOME", "/test-home", "--setenv", "CARGO_HOME", "/cargo",
            "--setenv", "CARGO_NET_OFFLINE", "true", "--setenv", "VK_DRIVER_FILES", str(ICD),
            "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "CARGO_TARGET_DIR", "/build",
            "--setenv", "IFW_QA_FONT_DIR", "/fonts", "--setenv", "IFW_QA_FALLBACK_DIR", "/fallback-fonts"]
    sources = [(AREA / "assessment-cache/registry", "/cargo/registry"), (AREA / "toolchain", "/toolchain"),
               (ROOT / "rust", "/project/rust"), (source, "/project/tools/rust-qa/gui"),
               (GUI / "artifacts", "/project/tools/rust-qa/gui/artifacts"),
               (ROOT / "rust/assets/fonts", "/fonts"), (source_profile.FONTS, "/fallback-fonts")]
    for path in prepared.sources.values():
        sources.append((path, "/review/" + path.name))
    for path, mount in sources:
        args.extend(["--ro-bind", str(path), mount])
    args.extend(["--bind", str(build.resolve()), "/build", "--bind", str(pixels), "/pixels",
                 "--chdir", "/project/tools/rust-qa/gui", "--", "/toolchain/bin/cargo",
                 "test", "--release", "--frozen", "--jobs", "2", "--bin", "native-gui-assessment",
                 "cpu_view_observation::actual_view_mesh_and_texture_requests", "--", "--exact", "--nocapture"])
    log = trial / "render.log"
    print(trial, flush=True)
    with log.open("wb") as stream:
        status = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    if status.returncode:
        raise RuntimeError(f"Isolated render failed with exit {status.returncode}. See {log}")
    rows = compare(pixels)
    report = {"compiler": compiler, "applicationSha256": SUBJECT_SHA, "lockSha256": LOCK_SHA,
              "rendererInputsSha256": sha(prepared.receipt), "baseFonts": base_fonts, "lavapipeIcdSha256": sha(ICD),
              "stagedSources": source_profile.tree_info(source / "src"), "renderLogSha256": sha(log),
              "frames": rows}
    result = trial / "pixel-comparison.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(result, flush=True)
    if any(row["above2"] for row in rows):
        raise ValueError("At least one pixel exceeded the historical two-code-value channel difference.")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path, help="Archive cache seeded by the sibling upstream.py")
    parser.add_argument("--build-cache", type=Path, default=SCOPE / "headless-build",
                        help="Private Cargo target directory, separate from each run's new pixel files")
    options = parser.parse_args()
    SCOPE.mkdir(exist_ok=True, parents=True)
    run(options.cache, options.build_cache)
