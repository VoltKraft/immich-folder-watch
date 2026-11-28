"""Verify the target graph and build the GUI fixture with the pinned native compiler."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

from gui import source_profile


QA = Path(__file__).resolve().parent
ROOT = QA.parents[1]
ARTIFACTS = ROOT / "artifacts/rust"
MANIFEST = QA / "gui/Cargo.toml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--offline", action="store_true", help="use pre-fetched locked registry archives")
    parser.add_argument("--local-x64-inputs", type=Path, metavar="DIRECTORY",
                        help="compile the ordinary x64 GUI and its native test executables for the local VM")
    args = parser.parse_args()
    if args.local_x64_inputs and (os.name != "nt" or args.target != "x86_64-pc-windows-msvc"):
        parser.error("--local-x64-inputs requires the native Windows x64 compiler")
    output = ARTIFACTS / "gui-native" / args.target
    output.mkdir(parents=True, exist_ok=True)
    cargo_home = ARTIFACTS / "assessment-cache"
    build = ARTIFACTS / "gui-build"
    profile = source_profile.prepare(fetch=not args.offline, registry=cargo_home / "registry")
    env = {**os.environ, "CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(build),
           "IFW_QA_FONT_DIR": str(ROOT / "rust/assets/fonts"), "IFW_QA_FALLBACK_DIR": str(source_profile.FONTS)}
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), args.target], check=True)
    subprocess.run([sys.executable, str(QA / "verify-gui-inputs.py")], check=True)
    if not args.local_x64_inputs:
        subprocess.run(["cargo", "fmt", "--manifest-path", str(MANIFEST), "--", "--check"], env=env, check=True)
    if not args.offline:
        source_profile.fetch_replay_registry(env)
        subprocess.run(["cargo", "fetch", "--locked", "--manifest-path", str(MANIFEST)], env=env, check=True)
    source_profile.validate()
    compiler_evidence = {}
    if os.name == "nt":
        source_paths = [MANIFEST, *sorted((MANIFEST.parent / "src").glob("*.rs")), MANIFEST.parent / "src/tray-icon.argb",
                        ROOT / "rust/Cargo.toml", ROOT / "rust/crates/desktop-lifecycle/Cargo.toml",
                        ROOT / "rust/crates/desktop-lifecycle/src/lib.rs"]
        lock_hash, graph_hash = source_profile.verify_native_graph(args.target, env, output / "graph.json")
        if not args.local_x64_inputs:
            subprocess.run(["cargo", "clippy", "--manifest-path", str(MANIFEST), "--frozen",
                            "--all-targets", "--", "-D", "warnings"], env=env, check=True)
        subprocess.run(["cargo", "build", "--manifest-path", str(MANIFEST), "--release", "--frozen"],
                       env=env, check=True)
        binary = build / "release/native-gui-assessment.exe"
        tests = ["cargo", "test", "--manifest-path", str(MANIFEST), "--release", "--frozen",
                 "--lib", "--bin", "native-gui-assessment"]
        compiler_sources = {p.relative_to(ROOT).as_posix(): source_profile.sha(p) for p in source_paths}
    else:
        builder = [sys.executable, str(QA / "gui/build.py"), "--registry", str(cargo_home / "registry")]
        subprocess.run([*builder, "--clippy"], env=env, check=True)
        subprocess.run(builder, env=env, check=True)
        binary = build / "release/native-gui-assessment"
        inputs = json.loads(binary.with_suffix(".inputs.json").read_bytes())
        compiler_sources = dict(inputs["sources"])
        if compiler_sources.pop("tools/rust-qa/gui/Cargo.lock") != source_profile.sha(MANIFEST.with_name("Cargo.lock")):
            raise ValueError("The archived GUI compiler inputs differ from the selected lock")
        shutil.copyfile(build / "gui-graph.json", output / "graph.json")
        shutil.copyfile(build / "gui-compiler.jsonl", output / "compiler.jsonl")
        shutil.copyfile(build / "gui-registry-sources.json", output / "registry-sources.json")
        lock_hash = source_profile.sha(MANIFEST.with_name("Cargo.lock"))
        graph_hash = source_profile.sha(output / "graph.json")
        if (inputs["graphSha256"] != graph_hash or inputs["binary_sha256"] != source_profile.sha(binary)
                or inputs["compilerStreamSha256"] != source_profile.sha(output / "compiler.jsonl")
                or inputs["registryReceiptSha256"] != source_profile.sha(output / "registry-sources.json")):
            raise ValueError("The Linux GUI and its compiler inputs differ from the build receipt")
        compiler_evidence = {key: inputs[key] for key in
                             ("compilerStreamSha256", "compilerUnits", "registryReceiptSha256", "compilerDrivers")}
        tests = [*builder, "--test"]
    if args.local_x64_inputs:
        kit = args.local_x64_inputs.resolve()
        kit.mkdir(parents=True, exist_ok=False)
        test_inputs = kit / "tests"
        pack = runpy.run_path(str(QA / "windows-local/workspace.py"))["build_harnesses"]
        pack(test_inputs, "gui", ["cargo", "test", "--release", "--all-targets", "--frozen"], env,
             graph=output / "graph.json")
        test_evidence = {"testHarnessReceiptSha256": source_profile.sha(test_inputs / "build.json")}
    else:
        test_log = output / "gui-unit-tests.log"
        with test_log.open("wb") as log:
            outcome = subprocess.run(tests, env=env, stdout=log, stderr=subprocess.STDOUT)
        if outcome.returncode:
            print(test_log.read_text(encoding="utf-8", errors="replace")[-8000:], file=sys.stderr)
            outcome.check_returncode()
        test_evidence = {"unitTestLogSha256": source_profile.sha(test_log)}
    record = {"source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "target": args.target, "graphSha256": graph_hash, "lockSha256": lock_hash,
              **test_evidence, **compiler_evidence,
              "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "sourceTrees": profile["trees"], "fallbackFonts": profile["fonts"],
              "textNotices": profile["noticeFiles"], "sourceProfileSha256": source_profile.sha(source_profile.REVIEW),
              "sourceReconstructionSha256": source_profile.sha(Path(source_profile.__file__)),
              "compilerSources": compiler_sources}
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if args.local_x64_inputs:
        desktop = kit / "desktop"
        desktop.mkdir()
        for path in (binary, output / "graph.json", output / "build.json"):
            shutil.copyfile(path, desktop / path.name)
    print(f"{args.target} built {record['binarySha256']}")


if __name__ == "__main__":
    main()
