"""Attach the frozen development inventory and Vulkan observers to a canonical GUI build."""

import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from build import instrument_submit
from inputs import WORKER_SOURCES, sha, source_digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / "artifacts/rust"


def verify(subject):
    sys.path.insert(0, str(HERE.parent / "gui"))
    import source_profile
    gui = json.loads((subject / "native-gui-assessment.inputs.json").read_text())
    worker = json.loads((subject / "worker.inputs.json").read_text())
    required = {"tools/rust-qa/gui/src/" + name for name in ("main.rs", "graphics.rs", "fonts.rs", "native_window.rs", "linux.rs")}
    if (not required.issubset(gui["sources"]) or gui["binary_sha256"] != sha(subject / "native-gui-assessment")
            or worker["gui_sha256"] != gui["binary_sha256"] or source_digest(worker) != WORKER_SOURCES
            or gui.get("sourceProfileSha256") != sha(source_profile.REVIEW)):
        raise ValueError("The integrated GUI, source profile and frozen worker receipt are required")
    for name, digest in gui["sources"].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"The build differs from the working native GUI source {name}")
    for name, digest in (("ifw-performance-worker", worker["worker_sha256"]),
                         ("observer/libvulkan.so.1", worker["observer_sha256"])):
        if sha(subject / name) != digest:
            raise ValueError(f"Changed QA input {name}")
    return worker


def stage(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.name):
        raise ValueError("Select a fresh staging label")
    base = args.source.resolve(strict=True)
    if not base.is_relative_to(ART / "performance/subjects"):
        raise ValueError("Select the canonical GUI staged by build_worker.py")
    worker = verify(base)
    work = ART / "graphics" / args.name
    work.mkdir(parents=True, exist_ok=False)
    subject = work / "subject"
    subject.mkdir()
    for name in ("native-gui-assessment", "native-gui-assessment.inputs.json", "worker.inputs.json",
                 "ifw-performance-worker", "observer/libvulkan.so.1"):
        dest = subject / name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(base / name, dest)
    observer = instrument_submit(work, subject, worker)
    receipt = dict(gui_receipt=sha(subject / "native-gui-assessment.inputs.json"),
                   worker_receipt=sha(subject / "worker.inputs.json"), submit_observer=observer,
                   submit_source=sha(HERE / "submit_loss.rs"), observer_builder=sha(HERE / "build.py"),
                   stage=sha(Path(__file__)))
    (subject / "integrated.inputs.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(subject)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("source", type=Path)
    stage(parser.parse_args())
