"""Prepare the offline Noble build seed from exact signed sources and the guest dependency plan."""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
NOBLE = HERE.parent
sys.path.insert(0, str(NOBLE))
from inputs import ART, BASE, ORIGINALS, PATCH, PATCH_SHA, SOURCE_RELEASE, sha
from verify import authenticate, signed_packages

FILES = ("inputs.py", "verify.py", "prepare.py", "build.py", "flock.patch", "installed/package/build.py")


def prepare(apt, destination):
    root = ART / "gui-noble-native/root"
    cache = BASE / "cache"
    source = authenticate(root, cache, False)
    destination.mkdir(exist_ok=False)
    packages = destination / "debs"
    packages.mkdir()
    plan = json.loads((apt / "plan.json").read_text())
    signed = signed_packages(root, "amd64", plan["packages"], destination)
    if signed != json.loads((apt / "apt-packages.json").read_text()):
        raise ValueError("Build dependency receipts differ from the signed Noble indices")
    for item in plan["packages"]:
        name = Path(item["Filename"]).name
        path = apt / "debs" / name
        if path.is_symlink() or path.stat().st_size != int(item["Size"]) or sha(path) != item["SHA256"]:
            raise ValueError("Dependency input differs from the signed plan: " + name)
        shutil.copyfile(path, packages / name)
    (destination / "plan.json").write_bytes((apt / "plan.json").read_bytes())
    inputs = destination / "ubuntu-source"
    inputs.mkdir()
    for name, digest in {**ORIGINALS, SOURCE_RELEASE + ".InRelease": SOURCE_RELEASE,
                         source["index"] + ".xz": source["index"]}.items():
        path = cache / name
        if path.is_symlink() or sha(path) != digest:
            raise ValueError("Changed source input: " + name)
        shutil.copyfile(path, inputs / name)
    fixture = destination / "tools/rust-qa/portal-noble"
    for name in FILES:
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(NOBLE / name, target)
    upstream = fixture.parent / "portal-reference/flock-upstream.patch"
    upstream.parent.mkdir()
    if sha(PATCH) != PATCH_SHA:
        raise ValueError("Unexpected upstream patch")
    shutil.copyfile(PATCH, upstream)
    shutil.copyfile(HERE / "package.sh", destination / "package.sh")
    print(destination, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apt", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.apt.resolve(strict=True), args.destination.resolve())
