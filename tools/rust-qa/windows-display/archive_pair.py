"""Retain the two original ARM64 display subjects and their paired inventory worker."""
import json
import os
from pathlib import Path
import runpy
import shutil

QA = Path(__file__).resolve().parents[1]
TARGET = "aarch64-pc-windows-msvc"


def main():
    shared = runpy.run_path(str(QA / "windows-launcher/local_build.py"))
    revision = shared["hosted_revision"]()
    if os.environ.get("RUNNER_ARCH") != "ARM64" or os.environ.get("NATIVE_TARGET") != TARGET:
        raise ValueError("Use the native ARM64 display worker")
    art = shared["ART"]
    out = art / "windows-display-inputs"
    (out / "canonical").mkdir(parents=True, exist_ok=False)
    shutil.copyfile(art / "gui-native" / TARGET / "gui-unit-tests.log", out / "canonical/gui-unit-tests.log")
    receipt = shared["stage_built_pair"](out, TARGET, revision)
    normal = json.loads((out / "canonical/build.json").read_bytes())
    warm = json.loads((out / "retained/build.json").read_bytes())
    files = receipt["files"]
    if (revision != normal["source"] or revision != warm["revision"] or normal["target"] != TARGET or warm["target"] != TARGET
            or not (normal["binarySha256"] == warm["baseline"] == files["canonical/native-gui-assessment.exe"])
            or not (warm["binary"] == receipt["inventory"]["gui"] == files["native-gui-assessment.exe"])
            or receipt["inventory"]["worker"] != files["ifw-performance-worker.exe"]
            or normal["unitTestLogSha256"] != files["canonical/gui-unit-tests.log"]):
        raise ValueError("The archived ARM64 inputs differ from the original native builds")
    (out / "display-build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
