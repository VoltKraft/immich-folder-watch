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
from gui.compiler_inputs import linux_project_sources
from gui.startup import qualify, vendor

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


def stage(out, gui, *, original_control=False):
    subject_sha = SUBJECT_SHA if original_control else STARTUP_SUBJECT_SHA
    lock_sha = LOCK_SHA if original_control else STARTUP_LOCK_SHA
    patch = HERE / "test-view.patch" if original_control else GUI / "startup/headless-view.patch"
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
    if not original_control and (sha(out / "Cargo.toml") != STARTUP_MANIFEST_SHA
                                 or source_profile.tree_info(out / "src") != STARTUP_SOURCE_TREE):
        raise ValueError("The startup editor instrumentation differs from the originally measured sources")
    if sha(out / "Cargo.lock") != lock_sha:
        raise ValueError("The headless test's lockfile changed")
    return patch


def project_inputs(project):
    return {p.relative_to(project).as_posix(): sha(p) for p in linux_project_sources(project)}


def stage_dependencies(project, inputs, destination):
    # Give local path crates fresh mtimes even when reusing a target cache from a newer historical snapshot.
    mounts = []
    for relative in ("rust", "tools/rust-qa/yaml"):
        if relative + "/Cargo.toml" not in inputs:
            continue
        for name, digest in inputs.items():
            if name.startswith(relative + "/"):
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project / name, path)
                if sha(path) != digest:
                    raise ValueError(f"The staged first-party compiler input changed: {name}")
        mounts.append((destination / relative, "/project/" + relative))
    return mounts


def run(cache, build, *, startup_vendor=None, combined_receipt=None, original_control=False):
    if sys.platform != "linux" or platform.machine() != "x86_64" or not ICD.is_file():
        raise ValueError(f"This headless reference requires Linux x64 and {ICD}")
    build = build.resolve()
    if not build.is_relative_to(AREA) or build == AREA:
        raise ValueError("The writable build cache must be inside artifacts/rust/")
    runner_sha = sha(Path(__file__))
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
    gui = GUI
    startup_record = None
    profile = "ordinary"
    if (startup_vendor is None) != (combined_receipt is None):
        raise ValueError("Supply both the startup directory source and its original combined receipt")
    if startup_vendor is not None and original_control:
        raise ValueError("Select one historical editor for the replay")
    snapshot = trial / "startup"
    if startup_vendor is not None:
        profile = "staged-startup"
        directory = startup_vendor.resolve(strict=True)
        qualify.assess(snapshot, directory, combined_receipt.resolve(strict=True), AREA / "toolchain")
        gui = snapshot / "project/tools/rust-qa/gui"
        receipt = snapshot / "registry-sources.json"
        startup_record = {"revision": qualify.BASE, "originalSourcesSha256": sha(snapshot / "original-sources.json"),
                          "supplySha256": sha(snapshot / "supply.json"), "registrySourcesSha256": sha(snapshot / "registry-sources.json"),
                          "patchSha256": sha(GUI / "startup/headless-view.patch"), "manifestSha256": STARTUP_MANIFEST_SHA,
                          "runnerSha256": runner_sha, "comparatorSha256": sha(HERE / "pixels.py")}
    else:
        if original_control:
            profile = "original-control"
            gui, _ = qualify.stage(snapshot)
        directory = vendor.compiler_directory(AREA / "assessment-cache/registry", gui, stock=original_control)
        receipt = directory.parents[2] / "registry-sources.json"
    project = gui.parents[2]
    inputs = project_inputs(project)
    dependencies = stage_dependencies(project, inputs, trial / "first-party")
    patch = stage(source, gui, original_control=original_control)
    registry_receipt = trial / "registry-sources.json"
    shutil.copyfile(receipt, registry_receipt)
    digest = sha(registry_receipt)
    expected = (vendor.RECEIPT_SHA256 if startup_vendor is not None else
                vendor.GUI_LOCK_RECEIPTS[inputs["tools/rust-qa/gui/Cargo.lock"]])
    if digest != expected:
        raise ValueError("The compiler source receipt differs from the reviewed GUI lock")
    target_dir = build / "targets" / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    args = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache", "--dev", "/dev",
            "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/test-home", "--dir", "/cargo",
            "--setenv", "HOME", "/test-home", "--setenv", "CARGO_HOME", "/cargo",
            "--setenv", "CARGO_NET_OFFLINE", "true", "--setenv", "VK_DRIVER_FILES", str(ICD),
            "--setenv", "PATH", "/toolchain/bin:/usr/bin", "--setenv", "CARGO_TARGET_DIR", "/build",
            "--setenv", "IFW_QA_FONT_DIR", "/fonts", "--setenv", "IFW_QA_FALLBACK_DIR", "/fallback-fonts"]
    sources = [*dependencies, (directory, "/reviewed"), (AREA / "toolchain", "/toolchain"),
               (source, "/project/tools/rust-qa/gui"),
               (gui / "artifacts", "/project/tools/rust-qa/gui/artifacts"),
               (ROOT / "rust/assets/fonts", "/fonts"), (source_profile.FONTS, "/fallback-fonts")]
    for path in prepared.sources.values():
        sources.append((path, "/review/" + path.name))
    for path, mount in sources:
        args.extend(["--ro-bind", str(path), mount])
    args.extend(["--bind", str(target_dir), "/build", "--bind", str(pixels), "/pixels",
                 "--chdir", "/project/tools/rust-qa/gui", "--", "/toolchain/bin/cargo",
                 "test", "--release", "--frozen", "--jobs", "1", *qualify.source_config("/reviewed"), "--bin", "native-gui-assessment",
                 "cpu_view_observation::actual_view_mesh_and_texture_requests", "--", "--exact", "--nocapture"])
    log = trial / "render.log"
    print(trial, flush=True)
    with log.open("wb") as stream:
        status = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    if status.returncode:
        raise RuntimeError(f"Isolated render failed with exit {status.returncode}. See {log}")
    rows = compare(pixels)
    if project_inputs(project) != inputs or sha(Path(__file__)) != runner_sha:
        raise ValueError("The original project sources or runner changed during the headless render")
    report = {"compiler": compiler, "applicationSha256": sha(gui / "src/main.rs"),
              "lockSha256": sha(source / "Cargo.lock"),
              "profile": profile, "firstPartyInputs": inputs, "registryReceiptSha256": sha(registry_receipt),
              "manifestSha256": sha(source / "Cargo.toml"), "patchSha256": sha(patch),
              "runnerSha256": runner_sha, "comparatorSha256": sha(HERE / "pixels.py"),
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
    replay = parser.add_mutually_exclusive_group()
    replay.add_argument("--original-control", action="store_true", help="Reconstruct the editor before startup integration")
    replay.add_argument("--startup-vendor", type=Path, help="Reconstruct the qualified startup GUI using these reviewed sources")
    parser.add_argument("--combined-receipt", type=Path, help="Original combined source and four-target feature receipt directory")
    options = parser.parse_args()
    if (options.startup_vendor is None) != (options.combined_receipt is None):
        parser.error("--startup-vendor and --combined-receipt must be used together")
    SCOPE.mkdir(exist_ok=True, parents=True)
    run(options.cache, options.build_cache, startup_vendor=options.startup_vendor, combined_receipt=options.combined_receipt,
        original_control=options.original_control)
