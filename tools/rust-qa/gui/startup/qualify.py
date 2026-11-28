"""Reconstruct the GUI with the reviewed YAML reader, using only original offline compiler inputs."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent
GUI = HERE.parent
QA = GUI.parent
ROOT = QA.parents[1]
AREA = ROOT / "artifacts/rust"
BASE = "c63d91c42eae9f71f07a2d1816214a1e16609ef8"
sys.path.insert(0, str(QA / "combined-profile"))
from graphs import TARGETS, feature_map, fingerprint, normal_build
from sources import locked, read, sha256, source_config, source_profile, write
from gui.compiler_inputs import verify_gui_units
from gui.startup.vendor import verify_sources as verify_registry_sources


def baseline_json(path):
    return json.loads(subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT))


def stage(output):
    project = output / "project"
    gui = project / "tools/rust-qa/gui"
    yaml = gui.parent / "yaml"
    inputs = [f"tools/rust-qa/{name}/{part}" for name in ("gui", "yaml")
              for part in ("Cargo.toml", "Cargo.lock", "src", "tests", "examples")]
    inputs += ["rust/Cargo.toml", "rust/crates/desktop-lifecycle"]
    names = subprocess.check_output(["git", "ls-tree", "-r", "-z", "--name-only", BASE, "--", *inputs],
                                    cwd=ROOT).decode().split("\0")
    sources = {}
    for name in filter(None, names):
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", BASE + ":" + name], cwd=ROOT))
        sources[name] = sha256(path)
    write(output / "original-sources.json", sources)
    # The patched text trees have separate source and notice witnesses.
    text = source_profile.validate()
    shutil.copytree(GUI / "artifacts/text", gui / "artifacts/text")
    for name, expected in text["trees"].items():
        if source_profile.tree_info(gui / "artifacts/text" / name) != expected:
            raise ValueError(f"The staged GUI text compiler tree differs for {name}")
    return gui, yaml


def verify_sources(gui, yaml, vendor, original, output):
    catalog = read(original / "source-trees.json")
    combined = baseline_json("tools/rust-qa/combined-profile/review.json")
    if fingerprint(catalog) != combined["allCompilerTreesSha256"]:
        raise ValueError("The original combined source receipt differs from the reviewed compiler trees")
    projection = verify_registry_sources(vendor, locked(gui) | locked(yaml), catalog)
    write(output / "registry-sources.json", projection)
    return projection


def assess(output, vendor, original, toolchain):
    output.mkdir(parents=True)
    gui, yaml = stage(output)
    approved = baseline_json("rust/audit/gui-text-inputs.json")["nativeFeatureReports"]
    reviewed_targets = baseline_json("tools/rust-qa/combined-profile/review.json")["targets"]
    projection = verify_sources(gui, yaml, vendor, original, output)
    env = {"PATH": str(toolchain / "bin") + os.pathsep + os.environ["PATH"],
           "CARGO_HOME": str(output / "empty-cargo-home"), "CARGO_NET_OFFLINE": "true",
           "CARGO_TARGET_DIR": str(output / "cargo-layout")}
    cargo_bin = toolchain / "bin/cargo"
    def cargo(op, where, args, *, frozen=True):
        return subprocess.check_output([cargo_bin, op, "--manifest-path", where / "Cargo.toml",
                                        "--frozen" if frozen else "--offline", *source_config(vendor), *args],
                                       env=env, text=True)
    renderer = {t: normal_build(cargo, gui, t) for t in TARGETS}
    language = {t: normal_build(cargo, yaml, t) for t in TARGETS}
    lock = sha256(gui / "Cargo.lock")
    if lock != baseline_json("rust/audit/gui-profile.json")["lockSha256"]:
        raise ValueError("The original GUI lock differs from its standalone review")
    subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--whitespace=error",
                    str(HERE / "language.patch")], cwd=gui, check=True)
    def rows(manifest):
        return {(p["name"], p["version"]): (p.get("source"), p.get("checksum"))
                for p in tomllib.loads((manifest / "Cargo.lock").read_text(encoding="utf-8"))["package"]}
    inputs = rows(gui) | rows(yaml)
    cargo("metadata", gui, ["--format-version", "1"], frozen=False)
    if rows(gui) != inputs:
        raise ValueError("The new lock is not the exact union of the original GUI and YAML identities")
    summary = {}
    for target in TARGETS:
        before = renderer[target]
        if fingerprint(feature_map(before)) != approved[target]["nativeFeatureSetsSha256"]:
            raise ValueError(f"The original renderer feature sets differ on {target}")
        after = normal_build(cargo, gui, target)
        archived = read(original / (target + ".json"))["features"]
        reviewed = reviewed_targets[target]
        if fingerprint(archived) != reviewed["normalBuildFeatureSetsSha256"]:
            raise ValueError(f"The original combined feature sets differ on {target}")
        expected_packages = set(before) | (set(language[target]) if "linux" in target else set())
        if set(after) != expected_packages or ("windows" in target and before != after):
            raise ValueError(f"Unexpected packages or Windows feature changes on {target}")
        for (name, version), groups in after.items():
            if name in ("native-gui-assessment", "ifw-yaml-assessment"):
                continue
            combined = {tuple(group) for group in archived[name + " v" + version]}
            individual = before.get((name, version), set()) | language[target].get((name, version), set())
            if groups - (combined | individual):
                raise ValueError(f"New Cargo compiler feature group for {name} {version} on {target}")
        features = feature_map(after)
        write(output / (target + ".json"), features)
        summary[target] = {"packages": len(after), "featuresSha256": fingerprint(features)}
    drivers = [Path(__file__), HERE / "language.patch", HERE / "vendor.py", GUI / "compiler_inputs.py", QA / "gui/source_profile.py", QA / "combined-profile/graphs.py",
               QA / "combined-profile/sources.py", QA / "yaml/prepare.py", QA / "check-toolchain.py"]
    report = {"drivers": {str(path.relative_to(ROOT)): sha256(path) for path in drivers}, "revision": BASE, "originalLock": lock, "manifest": sha256(gui / "Cargo.toml"),
              "lock": sha256(gui / "Cargo.lock"), "patch": sha256(HERE / "language.patch"),
              "registryTrees": len(projection), "registryReceipt": sha256(output / "registry-sources.json"),
              "targets": summary, "cargo": subprocess.check_output([cargo_bin, "--version"], env=env, text=True).strip()}
    write(output / "supply.json", report)


def compile_gui(vendor, toolchain, output, build):
    target = platform.machine() + "-unknown-linux-gnu"
    compiler = subprocess.check_output([sys.executable, QA / "check-toolchain.py", target, "--rustc",
                                       toolchain / "bin/rustc"], text=True).strip()
    if target not in TARGETS:
        raise ValueError("Run the native Linux compiler on a reviewed architecture")
    build.mkdir(exist_ok=True, parents=True)
    base = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--dir", "/test-home", "--dir", "/cargo"]
    for name in ("bin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            base += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            base += ["--ro-bind", str(path), str(path)]
    for path in ("/etc/alternatives", "/etc/ld.so.cache"):
        if Path(path).exists():
            base += ["--ro-bind", path, path]
    for src, dest in ((output / "project", "/project"), (toolchain, "/toolchain"), (vendor, "/vendor"),
                      (ROOT / "rust/assets/fonts", "/fonts"), (source_profile.FONTS, "/fallback-fonts")):
        base += ["--ro-bind", str(src), dest]
    base += ["--bind", str(build), "/build", "--chdir", "/project/tools/rust-qa/gui"]
    for key, value in {"PATH": "/toolchain/bin:/usr/bin", "HOME": "/test-home", "CARGO_HOME": "/cargo",
                       "CARGO_TARGET_DIR": "/build", "CARGO_NET_OFFLINE": "true",
                       "IFW_QA_FONT_DIR": "/fonts", "IFW_QA_FALLBACK_DIR": "/fallback-fonts"}.items():
        base += ["--setenv", key, value]
    passwd, group = (output / path for path in ("passwd", "group"))
    passwd.write_text(f"qa:x:{os.getuid()}:{os.getgid()}:Synthetic GUI:/test-home:/bin/false\n")
    group.write_text(f"qa:x:{os.getgid()}:\n")
    base += ["--ro-bind", str(passwd), "/etc/passwd", "--ro-bind", str(group), "/etc/group"]
    cargo = [*base, "--", "/toolchain/bin/cargo"]
    log = output / "compiler.jsonl"
    with log.open("wb") as stream:
        subprocess.run([*cargo, "build", "--release", "--frozen", "--jobs", "2", "--message-format",
                        "json-render-diagnostics", *source_config("/vendor")], stdout=stream, check=True)
    count = verify_gui_units(log, read(output / (target + ".json")))
    binary = build / "release/native-gui-assessment"
    with (output / "units-test.log").open("wb") as stream:
        subprocess.run([*cargo, "test", "--release", "--frozen", "--jobs", "2", "--bin", "native-gui-assessment",
                        *source_config("/vendor")], stdout=stream, stderr=subprocess.STDOUT, check=True)
    inputs = [p for p in (output / "project").rglob("*") if p.is_file() and "artifacts" not in p.relative_to(output / "project").parts]
    write(output / "native.json", {"target": target, "compiler": compiler, "binarySha256": sha256(binary),
          "supplySha256": sha256(output / "supply.json"), "unitTestLogSha256": sha256(output / "units-test.log"),
          "textAndFontProfileSha256": sha256(source_profile.REVIEW),
          "unitsCount": count, "unitsSha256": sha256(log),
          "sources": {p.relative_to(output / "project").as_posix(): sha256(p) for p in sorted(inputs)}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", required=True, type=Path, help="Original combined registry/src/reviewed directory")
    parser.add_argument("--combined-receipt", required=True, type=Path, help="Original reviewed combined run directory")
    parser.add_argument("--toolchain", type=Path, default=AREA / "toolchain")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native", action="store_true", help="Also compile and check actual native Linux units")
    parser.add_argument("--build-cache", type=Path, help="Existing private Cargo target directory below artifacts/rust")
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(AREA) or out.exists():
        parser.error("Use a new output directory below artifacts/rust")
    vendor = args.vendor.resolve(strict=True)
    toolchain = args.toolchain.resolve(strict=True)
    assess(out, vendor, args.combined_receipt.resolve(strict=True), toolchain)
    if args.native:
        cache = (args.build_cache or out / "native-build").resolve()
        if cache == AREA or not cache.is_relative_to(AREA):
            parser.error("Use a native build cache below artifacts/rust")
        compile_gui(vendor, toolchain, out, cache)
