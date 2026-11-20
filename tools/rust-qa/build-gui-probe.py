"""Verify the target graph and build the GUI fixture with the pinned native compiler."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


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
    env = {**os.environ, "CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(build),
           "IFW_QA_FONT_DIR": str(ROOT / "rust/assets/fonts")}
    subprocess.run([sys.executable, str(QA / "check-toolchain.py"), args.target], check=True)
    subprocess.run([sys.executable, str(QA / "verify-gui-inputs.py")], check=True)
    subprocess.run(["cargo", "fmt", "--manifest-path", str(MANIFEST), "--", "--check"], env=env, check=True)
    if not args.offline:
        subprocess.run(["cargo", "fetch", "--locked", "--manifest-path", str(MANIFEST)], env=env, check=True)
    graph = output / "graph.json"
    subprocess.run([sys.executable, str(QA / "audit-graph.py"), str(MANIFEST), args.target, str(graph),
                    "--verify-unpacked"],
                   env=env, check=True)
    profile = json.loads((ROOT / "rust/audit/gui-profile.json").read_text(encoding="utf-8"))
    graph_hash = hashlib.sha256(graph.read_bytes()).hexdigest()
    if hashlib.sha256(MANIFEST.with_name("Cargo.lock").read_bytes()).hexdigest() != profile["lockSha256"]:
        raise ValueError("The GUI lock differs from the reviewed native profile")
    if graph_hash != profile["targetReportSha256"][args.target]:
        raise ValueError(f"Resolved GUI inputs differ from the reviewed {args.target} graph: {graph_hash}")
    subprocess.run(["cargo", "clippy", "--manifest-path", str(MANIFEST), "--frozen",
                    "--all-targets", "--", "-D", "warnings"], env=env, check=True)
    if os.name == "nt":
        subprocess.run(["cargo", "build", "--manifest-path", str(MANIFEST), "--release", "--frozen"],
                       env=env, check=True)
        binary = build / "release/native-gui-assessment.exe"
    else:
        subprocess.run([sys.executable, str(QA / "gui/build.py"), "--registry", str(cargo_home / "registry")],
                       env=env, check=True)
        binary = build / "release/native-gui-assessment"
    record = {"source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "target": args.target, "graphSha256": graph_hash, "lockSha256": profile["lockSha256"],
              "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{args.target} built {record['binarySha256']}")


if __name__ == "__main__":
    main()
