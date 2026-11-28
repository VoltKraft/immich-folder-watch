"""Stage the ordinary HWND retention change beside a source-verified, existing Windows GUI build."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
QA, ROOT = HERE.parent, HERE.parents[2]
GUI = QA / "gui"
AREA = ROOT / "artifacts/rust/windows-warm-window"
TARGETS = ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
ORIGINALS = {
    "main.rs": "df337ee8c69b33490f08280e4aaac2a55e2e8c958edc64d97444d83c8dfae81f",
    "native_window.rs": "da24451a27c06a361a29e69f56019257b4303d54297e348eb222c2d69aca680e",
    "graphics.rs": "d13c3087261770a73f3e904d677b71ace1deba6efce47f68061f3a40184d828e",
}
sys.path.insert(0, str(QA))
from gui import source_profile
from windows_observer import isolated_windows_vm
import eframe_source
from compiler_units import VARIANT_INPUTS, compiled_library


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
    patches = [(HERE / name).read_bytes() for name in ("candidate.patch", "presentation.patch", "dispatch.patch")]
    pins = json.loads(eframe_source.PINS.read_bytes())
    patches.append(eframe_source.checked_bytes(eframe_source.APPLICATION_PATCH, pins["applicationPatchSha256"]))
    for patch in patches:
        subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--no-index", "--whitespace=error", "-"],
                       input=patch, cwd=gui, env=env, check=True)
    for name in ("loop_wake.rs", "windows_present.rs", "ui_trace.rs", "dwm_transitions.rs"):
        shutil.copyfile(HERE / name, gui / "src" / name)
    # Extend the canonical read-only Win32 queries with the comparison's existing timing queries.
    shutil.copyfile(HERE / "win32_clock.rs", gui / "src/win32_clock.rs")
    with (gui / "src/lib.rs").open("a", encoding="utf-8", newline="\n") as library:
        library.write("\nmod win32_clock;\npub use win32_clock::{counter, frequency, thread_id};\n")
        library.write('#[cfg(all(windows, target_arch = "x86_64"))]\nmod dwm_transitions;\n'
                      '#[cfg(all(windows, target_arch = "x86_64"))]\npub use dwm_transitions::observe_transitions;\n')
    eframe_source.prepare(gui)
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
        rows.add((name, version.removeprefix("v"), tuple(sorted(filter(None, features.split(","))))))
    return sorted(rows)


def compiler_graph(messages, gui, selected, *, extra_local=None):
    """Match every reported Cargo package and feature set to the retained lock and native tree."""
    successful = {"reason": "build-finished", "success": True}
    if (not messages or messages[-1] != successful
            or sum(item["reason"] == "build-finished" for item in messages) != 1):
        raise ValueError("The retained compiler log must end with one successful build")
    lock = tomllib.loads((gui / "Cargo.lock").read_text(encoding="utf-8"))
    locked = {(row["name"], row["version"]): row.get("source") for row in lock["package"]}
    local = {"native-gui-assessment": gui, "desktop-lifecycle": gui.parents[2] / "rust/crates/desktop-lifecycle",
             "eframe": gui / eframe_source.PACKAGE, "winit": gui / eframe_source.WINIT_PACKAGE,
             **{name: gui / "artifacts/text" / name for name in ("egui", "epaint", "unicode-bidi")}}
    if extra_local:
        local.update(extra_local)
    observed = set()
    units = [item for item in messages if item["reason"] == "compiler-artifact"]
    for unit in units:
        origin, identity = unit["package_id"].rsplit("#", 1)
        if "@" in identity:
            name, version = identity.split("@", 1)
        else:
            name, version = PurePosixPath(unquote(origin)).name, identity
        if (name, version) not in locked:
            raise ValueError(f"Unlisted retained compiler package: {name} {version}")
        if locked[name, version] is None:
            if (not origin.startswith("path+file:") or name not in local
                    or Path(unit["manifest_path"]).resolve() != (local[name] / "Cargo.toml").resolve()):
                raise ValueError(f"Unexpected local compiler input for {name}")
        elif origin != locked[name, version]:
            raise ValueError(f"The compiler and lock disagree on the source of {name}")
        observed.add((name, version, tuple(sorted(unit["features"]))))
    if observed != set(selected):
        raise ValueError("The retained compiler packages or features differ from the native normal/build tree")
    return {"units": len(units), "featureSets": len(observed), "packages": len({(n, v) for n, v, _ in observed})}


def application_artifact(messages, gui, executable):
    """Identify the local binary Cargo linked and bind its bytes to the tested executable."""
    manifest = (gui / "Cargo.toml").resolve()
    units = [item for item in messages if item["reason"] == "compiler-artifact"
             and item["target"]["kind"] == ["bin"] and Path(item["manifest_path"]).resolve() == manifest]
    if len(units) != 1:
        raise ValueError("The retained compiler must report exactly one local GUI binary")
    unit, = units
    target = unit["target"]
    output = executable.resolve()
    if (target["name"] != "native-gui-assessment" or target["crate_types"] != ["bin"]
            or Path(target["src_path"]).resolve() != (gui / "src/main.rs").resolve()
            or not unit["executable"] or Path(unit["executable"]).resolve() != output
            or sum(Path(name).resolve() == output for name in unit["filenames"]) != 1):
        raise ValueError("The retained GUI compiler output does not match the selected executable")
    return {"target": target["name"], "crateRoot": "src/main.rs", "output": executable.name, "sha256": sha(output)}


def main(target, *, isolated_vm=False, compile_only=False):
    hosted = os.name == "nt" and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and os.getenv("GITHUB_ACTIONS") == "true"
    if not (hosted or isolated_windows_vm(isolated_vm)):
        raise ValueError("Build on a native hosted Windows runner or an explicitly selected disposable Windows VM")
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
    compiler_version = subprocess.check_output([sys.executable, str(QA / "check-toolchain.py"), target], text=True)
    print(compiler_version, end="")
    manifest = str(gui / "Cargo.toml")
    lock, graph = source_profile.verify_native_graph(target, env)
    selected = feature_rows(gui / "Cargo.toml", target, env)
    if (lock != ordinary["lockSha256"] or graph != ordinary["graphSha256"] or selected != feature_rows(GUI / "Cargo.toml", target, env)
            or any(source_profile.tree_info(gui / "artifacts/text" / name) != info for name, info in approved["trees"].items())):
        raise ValueError("Unexpected package, feature or text engine change in the retained Windows graph")
    if not compile_only:
        subprocess.run(["cargo", "fmt", "--manifest-path", manifest, "--", "--check"], env=env, check=True)
        subprocess.run(["cargo", "clippy", "--manifest-path", manifest, "--frozen", "--all-targets", "--", "-D", "warnings"],
                       cwd=gui, env=env, check=True)
    compiled = subprocess.check_output(["cargo", "build", "--manifest-path", manifest, "--frozen", "--release",
                                        "--message-format=json-render-diagnostics"], cwd=gui, env=env)
    messages = [json.loads(line) for line in compiled.splitlines()]
    libraries = {}
    for package, version in ((eframe_source.PACKAGE, "0.37.0"), (eframe_source.WINIT_PACKAGE, "0.30.13")):
        features, = [flags for name, v, flags in selected if (name, v) == (package.name, version)]
        libraries[package.name] = compiled_library(messages, gui, output / "build", package, features)
    compiler = compiler_graph(messages, gui, selected)
    exe = output / "build/release/native-gui-assessment.exe"
    compiler["application"] = application_artifact(messages, gui, exe)
    log = output / "compiler.jsonl"
    log.write_bytes(compiled)
    compiler.update(file=log.name, sha256=sha(log))
    sources = eframe_source.source_bundle(gui, output / "eframe-source.zip")
    record = dict(target=target, revision=revision, nativeCompiler=compiler_version.strip(),
                  buildHost="github-hosted" if hosted else "isolated-vm",
                  baselineReceipt=sha(ordinary_path), baseline=sha(canonical),
                  binary=compiler["application"]["sha256"],
                  canonicalGraph=graph, canonicalLock=lock, lock=sha(gui / "Cargo.lock"),
                  selectedFeatureRows=len(selected), compilerEvidence=compiler, canonicalInputs=ORIGINALS,
                  eframeSource=sources, eframeUnit=libraries["eframe"], winitUnit=libraries["winit"],
                  baseFonts={p.name: sha(p) for p in sorted((ROOT / "rust/assets/fonts").glob("*.ttf"))},
                  fallbackFonts={name: asset["sha256"] for name, asset in approved["fonts"].items()},
                  compilerInputs={p.name: sha(p) for p in [*sorted((gui / "src").glob("*.rs")), gui / "src/tray-icon.argb"]},
                  variantInputs={name: sha(HERE / name) for name in VARIANT_INPUTS})
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{target} {record['binary']} {exe}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--isolated-vm", action="store_true", help="build in an explicitly selected disposable Windows VM")
    parser.add_argument("--compile-only", action="store_true", help="prepare compiler receipts and executable inputs for local VM tests")
    args = parser.parse_args()
    main(args.target, isolated_vm=args.isolated_vm, compile_only=args.compile_only)
