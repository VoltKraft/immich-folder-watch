"""Resolve the source build and Flatpak test packages against the disposable guest's actual dpkg status."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from inputs import ART, BASE, ORIGINALS, SOURCE, VERSION, fetch, sha, snapshot_url
from prepare import package_plan
from verify import authenticate, signed_packages


def requirements(dsc):
    # The four source objects are pinned to the authenticated Noble source index.
    if sha(dsc) != ORIGINALS[dsc.name]:
        raise ValueError("Unexpected source control file")
    line, = re.findall(r"^Build-Depends: (.+)$", dsc.read_text(), re.MULTILINE)
    names = []
    for term in line.split(", "):
        m = re.fullmatch(r"([a-z0-9.+-]+)(?: \((?:>=|=) [^)]+\))?(?: <!(?:nocheck|nodoc)>)?", term)
        if not m:
            raise ValueError("Unsupported build dependency in pinned source: " + term)
        # debhelper supplies the chosen virtual compatibility level. dpkg-checkbuilddeps
        # inside the VM checks the full versioned expression before building.
        names.append("debhelper" if m[1] == "debhelper-compat" else m[1])
    return sorted(set(names) | {"build-essential", "dpkg-dev", "fakeroot", "quilt", "patch", "ninja-build",
                                "pkg-config", "flatpak", "ostree", "dbus-user-session", "libglib2.0-bin",
                                SOURCE + "=" + VERSION})


def resolve(inventory, output, download, runtime_only=False):
    record = json.loads((inventory / "vm.json").read_text())
    status = inventory / "dpkg-status"
    if (record["stage"] != "inventory" or record["outputs"]["dpkg-status"] != sha(status)
            or (inventory / "arch").read_text().strip() != "amd64"):
        raise ValueError("Expected the completed native VM inventory")
    root = ART / "gui-noble-native/root"
    cache = BASE / "cache"
    output.mkdir(parents=True, exist_ok=True)
    authenticate(root, cache, False)
    if runtime_only:
        packages = ["flatpak", "ostree", "dbus-user-session", "python3-gi", "gir1.2-glib-2.0",
                    "libglib2.0-bin", SOURCE + "=" + VERSION]
    else:
        packages = requirements(cache / (SOURCE + "_" + VERSION + ".dsc"))
    plan = package_plan(root, output, packages, guest_status=status)
    signed = signed_packages(root, "amd64", plan, output)
    target = output / "debs"
    target.mkdir(exist_ok=True)
    caches = [root / "var/cache/apt/archives", root / "var/cache/apt/compiler", cache / "debs",
              ART / "plasma/cache", BASE / "installed/apt-amd64/debs"]
    known = {}
    for directory in caches:
        for file in directory.glob("*.deb"):
            known.setdefault(file.name, []).append(file)

    def copy(row):
        pool = row["Filename"]
        name = Path(pool).name
        digest = row["SHA256"]
        out = target / name
        if out.exists():
            if sha(out) != digest:
                raise ValueError("Changed local package: " + name)
            return
        for candidate in known.get(name, []):
            if sha(candidate) == digest:
                shutil.copyfile(candidate, out)
                return
        fetch(snapshot_url(signed["snapshots"][pool], pool), out, digest, download, int(row["Size"]))

    with ThreadPoolExecutor(max_workers=6) as queue:
        list(queue.map(copy, plan))
    (output / "plan.json").write_text(json.dumps({"image": record["image"], "status": sha(status),
                                                 "requirements": packages, "packages": plan}, indent=2) + "\n")
    print(f"Verified {len(plan)} Debian packages for the native test image")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--runtime-only", action="store_true", help="prepare the installed lease guest without build dependencies")
    args = parser.parse_args()
    resolve(args.inventory.resolve(), args.output.resolve(), args.download, args.runtime_only)
