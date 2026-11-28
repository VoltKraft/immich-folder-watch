"""Reconstruct the two reviewed Flatpak application-bus changes in a fresh compiler tree."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
sys.path.insert(0, str(QA / "combined-profile"))
from sources import ROOT, read, sha256, source_profile, yaml_prepare

REVIEW = HERE / "source-review.json"
PATCH = HERE / "application-bus.patch"


def reconstruct(archive, destination, notices):
    """Verify the original archive, reconstruct a new directory and retain the original notices."""
    expected = read(REVIEW)
    files, filters = yaml_prepare.source_files(archive, expected["crate"], expected["archiveSha256"])
    if filters or sha256(PATCH) != expected["patchSha256"]:
        raise ValueError("Unexpected source filter or patch for the reviewed AccessKit adapter")
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    before = source_profile.tree_info(destination)
    if before != expected["originalTree"] or read(destination / ".cargo_vcs_info.json") != expected["sourceRevision"]:
        raise ValueError("The original AccessKit tree or upstream revision differs from the review")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(destination.parent.resolve())}
    subprocess.run(["git", "apply", "--no-index", "--whitespace=error", str(PATCH)], cwd=destination, env=env, check=True)
    changed = {name: {"before": yaml_prepare.digest(data), "after": sha256(destination / name)}
               for name, data in files.items() if (destination / name).read_bytes() != data}
    if changed != expected["files"] or source_profile.tree_info(destination) != expected["compilerTree"]:
        raise ValueError("The reconstructed AccessKit compiler bytes differ from the measured candidate")
    notices.mkdir(parents=True, exist_ok=False)
    selected = {}
    for row in read(ROOT / "rust/audit/gui-inputs.json")["files"]:
        source = ROOT / "rust" / row["path"]
        if source.name.startswith("accesskit-"):
            if sha256(source) != row["sha256"]:
                raise ValueError(f"Upstream notice changed: {source.name}")
            shutil.copyfile(source, notices / source.name)
            selected[source.name] = sha256(notices / source.name)
    if selected != expected["notices"]:
        raise ValueError("The AccessKit MIT, Apache and Chromium notices differ from the source review")
    return expected
