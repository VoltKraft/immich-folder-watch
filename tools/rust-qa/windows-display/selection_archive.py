"""Verify and stage an original canonical ARM64 image from this repository's display workflow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

TARGET = "aarch64-pc-windows-msvc"
ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "artifacts/rust/gui-native" / TARGET
REPO = "VoltKraft/immich-folder-watch"
PREFIX = "windows-display-inputs/canonical/"


def stage(archive, destination, metadata, workflow, current):
    expected_source = workflow["head_sha"]
    origin = metadata["workflow_run"]
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if (metadata["expired"] or metadata["digest"] != "sha256:" + digest or origin["id"] != workflow["id"]
            or origin["head_branch"] != "rewrite/rust" or origin["head_sha"] != expected_source
            or metadata["name"] != "rust-source-display-arm64-" + expected_source
            or workflow["path"] != ".github/workflows/rust-windows-arm64-display.yaml"
            or workflow["head_repository"]["full_name"] != REPO):
        raise ValueError("Expected an original compiler archive of the native ARM64 display workflow")
    with zipfile.ZipFile(archive) as bundle:
        raw = bundle.read(PREFIX + "build.json")
        receipt = json.loads(raw)
        output_fields = {"source", "binarySha256", "unitTestLogSha256"}
        if (receipt["source"] != expected_source or receipt["target"] != TARGET
                or {k: v for k, v in receipt.items() if k not in output_fields}
                != {k: v for k, v in current.items() if k not in output_fields}):
            raise ValueError("Archived compiler sources, graph, target, fonts or reconstruction differ from the current build")
        for name, key in (("gui-unit-tests.log", "unitTestLogSha256"), ("graph.json", "graphSha256"),
                          ("native-gui-assessment.exe", "binarySha256")):
            data = bundle.read(PREFIX + name)
            if hashlib.sha256(data).hexdigest() != receipt[key]:
                raise ValueError("Original ARM64 compiler artifact mismatch for " + name)
            if name == "native-gui-assessment.exe":
                with (destination / name).open("xb") as out:
                    out.write(data)
    return dict(source=expected_source, target=TARGET, binarySha256=receipt["binarySha256"],
                artifact=metadata["id"], run=workflow["id"], archiveSha256=digest, receiptSha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=int)
    args = parser.parse_args()
    if (args.artifact <= 0 or os.getenv("GITHUB_REPOSITORY") != REPO or os.getenv("RUNNER_ARCH") != "ARM64"
            or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"):
        parser.error("Select an original archive on the native ARM64 rewrite runner")
    def endpoint(path):
        return ["gh", "api", f"repos/{REPO}/actions/{path}"]

    metadata = json.loads(subprocess.check_output(endpoint(f"artifacts/{args.artifact}")))
    workflow = json.loads(subprocess.check_output(endpoint(f"runs/{metadata['workflow_run']['id']}")))
    out = BUILD / "selection-replay"
    out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as temp:
        path = Path(temp) / "archive.zip"
        with path.open("xb") as target:
            subprocess.run(endpoint(f"artifacts/{args.artifact}/zip"), stdout=target, check=True)
        current = (BUILD / "build.json").read_bytes()
        receipt = stage(path, out, metadata, workflow, json.loads(current))
        receipt["currentReceiptSha256"] = hashlib.sha256(current).hexdigest()
    (out / "replay.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
