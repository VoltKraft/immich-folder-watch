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
SUBJECT_SHA = "df337ee8c69b33490f08280e4aaac2a55e2e8c958edc64d97444d83c8dfae81f"
LOCK_SHA = "55959e8ab77241da561ad189b53f75b3cba769a917ef47c8aa6b0acf9e304ae9"
STARTUP_SUBJECT_SHA = "4edc76ff7af596588264cf0c6ea8d3f55c13bde1eb21b585ce7dc73bd9abf74e"
STARTUP_LOCK_SHA = "b5a1e53f83d3f17811fc88bd0bdfed3b304b3ae8be2c95d337d4662ef771b8ca"
STARTUP_MANIFEST_SHA = "2f75fc0557786f859b3f1c0a879fd3a37ac1198be3e6da3ece58b72fbbebe5dc"
STARTUP_SOURCE_TREE = {"files": 28, "sha256": "46845aa2c309ab78d60a25aea61223e0dd0d47dc56c8e76343ff797eb2d4712a"}
AREA = ROOT / "artifacts/rust"
SCOPE = AREA / "egui-cpu-assessment"
ICD = Path("/usr/share/vulkan/icd.d/lvp_icd.x86_64.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(out, *, startup_gui=None):
    gui = startup_gui or GUI
    subject_sha = STARTUP_SUBJECT_SHA if startup_gui else SUBJECT_SHA
    lock_sha = STARTUP_LOCK_SHA if startup_gui else LOCK_SHA
    patch = GUI / "startup/headless-view.patch" if startup_gui else HERE / "test-view.patch"
    if sha(gui / "src/main.rs") != subject_sha:
        raise ValueError("The ordinary application's source differs from the qualified Window::ui")
    out.mkdir()
    (out / "artifacts").mkdir()
    shutil.copytree(gui / "src", out / "src")
    for name in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(gui / name, out / name)
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--unidiff-zero",
                    "--whitespace=error", str(patch)], cwd=out, check=True)
    for name in ("cpu_view_observation.rs", "view_gpu_reference.rs"):
        shutil.copyfile(HERE / name, out / "src" / name)
    if startup_gui and (sha(out / "Cargo.toml") != STARTUP_MANIFEST_SHA
                        or source_profile.tree_info(out / "src") != STARTUP_SOURCE_TREE):
        raise ValueError("The startup editor instrumentation differs from the originally measured sources")
    if sha(out / "Cargo.lock") != lock_sha:
        raise ValueError("The headless test's lockfile changed")


def run(cache, build, *, startup_vendor=None, combined_receipt=None):
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
    startup_gui = None
    startup_record = None
    cargo_config = []
    registry = [(AREA / "assessment-cache/registry", "/cargo/registry")]
    rust = ROOT / "rust"
    if (startup_vendor is None) != (combined_receipt is None):
        raise ValueError("Supply both the startup directory source and its original combined receipt")
    if startup_vendor is not None:
        from gui.startup import qualify
        vendor = startup_vendor.resolve(strict=True)
        snapshot = trial / "startup"
        qualify.assess(snapshot, vendor, combined_receipt.resolve(strict=True), AREA / "toolchain")
        startup_gui = snapshot / "project/tools/rust-qa/gui"
        rust = snapshot / "project/rust"
        registry = [(vendor, "/reviewed"), (startup_gui.parent / "yaml", "/project/tools/rust-qa/yaml")]
        cargo_config = qualify.source_config("/reviewed")
        startup_record = {"revision": qualify.BASE, "originalSourcesSha256": sha(snapshot / "original-sources.json"),
                          "supplySha256": sha(snapshot / "supply.json"), "registrySourcesSha256": sha(snapshot / "registry-sources.json"),
                          "patchSha256": sha(GUI / "startup/headless-view.patch"), "manifestSha256": STARTUP_MANIFEST_SHA,
                          "runnerSha256": sha(Path(__file__)), "comparatorSha256": sha(HERE / "pixels.py")}
    stage(source, startup_gui=startup_gui)
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache", "--dev", "/dev",
            "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/test-home", "--dir", "/cargo",
            "--setenv", "HOME", "/test-home", "--setenv", "CARGO_HOME", "/cargo",
            "--setenv", "CARGO_NET_OFFLINE", "true", "--setenv", "VK_DRIVER_FILES", str(ICD),
            "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "CARGO_TARGET_DIR", "/build",
            "--setenv", "IFW_QA_FONT_DIR", "/fonts", "--setenv", "IFW_QA_FALLBACK_DIR", "/fallback-fonts"]
    sources = [*registry, (AREA / "toolchain", "/toolchain"),
               (rust, "/project/rust"), (source, "/project/tools/rust-qa/gui"),
               ((startup_gui or GUI) / "artifacts", "/project/tools/rust-qa/gui/artifacts"),
               (ROOT / "rust/assets/fonts", "/fonts"), (source_profile.FONTS, "/fallback-fonts")]
    for path in prepared.sources.values():
        sources.append((path, "/review/" + path.name))
    for path, mount in sources:
        args.extend(["--ro-bind", str(path), mount])
    args.extend(["--bind", str(build.resolve()), "/build", "--bind", str(pixels), "/pixels",
                 "--chdir", "/project/tools/rust-qa/gui", "--", "/toolchain/bin/cargo",
                 "test", "--release", "--frozen", "--jobs", "1" if startup_gui else "2", *cargo_config, "--bin", "native-gui-assessment",
                 "cpu_view_observation::actual_view_mesh_and_texture_requests", "--", "--exact", "--nocapture"])
    log = trial / "render.log"
    print(trial, flush=True)
    with log.open("wb") as stream:
        status = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    if status.returncode:
        raise RuntimeError(f"Isolated render failed with exit {status.returncode}. See {log}")
    rows = compare(pixels)
    report = {"compiler": compiler, "applicationSha256": sha((startup_gui or GUI) / "src/main.rs"),
              "lockSha256": sha(source / "Cargo.lock"),
              "rendererInputsSha256": sha(prepared.receipt), "baseFonts": base_fonts, "lavapipeIcdSha256": sha(ICD),
              "stagedSources": source_profile.tree_info(source / "src"), "renderLogSha256": sha(log),
              "frames": rows}
    if startup_record is not None:
        report["startup"] = startup_record
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
    parser.add_argument("--startup-vendor", type=Path, help="Reconstruct the qualified GUI using these reviewed directory sources")
    parser.add_argument("--combined-receipt", type=Path, help="Original combined source and four-target feature receipt directory")
    options = parser.parse_args()
    if (options.startup_vendor is None) != (options.combined_receipt is None):
        parser.error("--startup-vendor and --combined-receipt must be used together")
    SCOPE.mkdir(exist_ok=True, parents=True)
    run(options.cache, options.build_cache, startup_vendor=options.startup_vendor, combined_receipt=options.combined_receipt)
