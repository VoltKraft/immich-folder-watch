"""Verify the target graph and build the GUI fixture with the pinned native compiler."""

import argparse
import hashlib
import json
import os
from pathlib import Path
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
    args = parser.parse_args()
    output = ARTIFACTS / "gui-native" / args.target
    output.mkdir(parents=True, exist_ok=True)
    cargo_home = ARTIFACTS / "assessment-cache"
    build = ARTIFACTS / "gui-build"
    profile = source_profile.prepare(fetch=not args.offline, registry=cargo_home / "registry")
    env = {**os.environ, "CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(build),
           "IFW_QA_FONT_DIR": str(ROOT / "rust/assets/fonts"), "IFW_QA_FALLBACK_DIR": str(source_profile.FONTS)}
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), args.target], check=True)
    subprocess.run([sys.executable, str(QA / "verify-gui-inputs.py")], check=True)
    subprocess.run(["cargo", "fmt", "--manifest-path", str(MANIFEST), "--", "--check"], env=env, check=True)
    if not args.offline:
        source_profile.fetch_replay_registry(env)
        subprocess.run(["cargo", "fetch", "--locked", "--manifest-path", str(MANIFEST)], env=env, check=True)
    lock_hash, graph_hash = source_profile.verify_native_graph(args.target, env, output / "graph.json")
    source_profile.validate()
    subprocess.run(["cargo", "clippy", "--manifest-path", str(MANIFEST), "--frozen",
                    "--all-targets", "--", "-D", "warnings"], env=env, check=True)
    if os.name == "nt":
        subprocess.run(["cargo", "build", "--manifest-path", str(MANIFEST), "--release", "--frozen"],
                       env=env, check=True)
        binary = build / "release/native-gui-assessment.exe"
        tests = ["cargo", "test", "--manifest-path", str(MANIFEST), "--release", "--frozen",
                 "--lib", "--bin", "native-gui-assessment"]
    else:
        builder = [sys.executable, str(QA / "gui/build.py"), "--registry", str(cargo_home / "registry")]
        subprocess.run(builder, env=env, check=True)
        binary = build / "release/native-gui-assessment"
        tests = [*builder, "--test"]
    test_log = output / "gui-unit-tests.log"
    with test_log.open("wb") as log:
        outcome = subprocess.run(tests, env=env, stdout=log, stderr=subprocess.STDOUT)
    if outcome.returncode:
        print(test_log.read_text(encoding="utf-8", errors="replace")[-8000:], file=sys.stderr)
        outcome.check_returncode()
    record = {"source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "target": args.target, "graphSha256": graph_hash, "lockSha256": lock_hash,
              "unitTestLogSha256": source_profile.sha(test_log),
              "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "sourceTrees": profile["trees"], "fallbackFonts": profile["fonts"],
              "textNotices": profile["noticeFiles"], "sourceProfileSha256": source_profile.sha(source_profile.REVIEW),
              "sourceReconstructionSha256": source_profile.sha(Path(source_profile.__file__)),
              "compilerSources": {p.relative_to(ROOT).as_posix(): source_profile.sha(p) for p in
                                  [MANIFEST, *sorted((MANIFEST.parent / "src").glob("*.rs")), MANIFEST.parent / "src/tray-icon.argb",
                                   ROOT / "rust/Cargo.toml",
                                   ROOT / "rust/crates/desktop-lifecycle/Cargo.toml", ROOT / "rust/crates/desktop-lifecycle/src/lib.rs"]}}
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{args.target} built {record['binarySha256']}")


if __name__ == "__main__":
    main()
