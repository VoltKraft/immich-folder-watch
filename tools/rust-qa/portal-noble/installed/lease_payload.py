"""Prepare the read-only application and package inputs for the installed Documents lease trial."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from vm import AREA, HERE, IMAGE_SHA, ROOT, sha
sys.path.insert(0, str(HERE.parent))
from inputs import ART, SOURCE, VERSION
from verify import signed_packages
sys.path.insert(0, str(HERE.parents[1] / "portal-dialog"))
from runtime_pin import BRANCH, COMMITS, PLATFORM


def checked_copy(source, destination, digest):
    if source.is_symlink() or not source.is_file() or sha(source) != digest:
        raise ValueError("Unexpected lease trial input: " + str(source))
    shutil.copyfile(source, destination)


def native_package(build, payload):
    receipt = json.loads((build / "vm.json").read_text())
    if (receipt["stage"] != "package" or receipt["image"] != IMAGE_SHA
            or (build / "exit").read_text().strip() != "0"
            or receipt["outputs"]["package-result.json"] != sha(build / "package-result.json")):
        raise ValueError("A completed native package VM build is required")
    result = json.loads((build / "package-result.json").read_text())
    package = result["packages"][SOURCE]
    if (result["status"] != "native-packages-built" or package["version"] != VERSION + "+ifwqa1"
            or package["architecture"] != "amd64" or receipt["outputs"]["candidate.deb"] != package["sha256"]):
        raise ValueError("The native Ubuntu build receipt does not match the candidate")
    checked_copy(build / "candidate.deb", payload / "candidate.deb", package["sha256"])
    return {"packageVm": sha(build / "vm.json"), "buildResult": sha(build / "package-result.json"),
            "candidate": package["sha256"]}


def prepare(apt, runtime, build=None):
    work = Path(tempfile.mkdtemp(prefix="lease-inputs-", dir=AREA))
    payload = work / "payload"
    payload.mkdir()
    candidate = native_package(build, payload) if build else {}
    plan = json.loads((apt / "plan.json").read_text())
    if plan["image"] != IMAGE_SHA:
        raise ValueError("The native guest and apt package plan differ")
    signed = signed_packages(ART / "gui-noble-native/root", "amd64", plan["packages"], work)
    (payload / "debs").mkdir()
    for row in plan["packages"]:
        name = Path(row["Filename"]).name
        checked_copy(apt / "debs" / name, payload / "debs" / name, signed["packages"][row["Filename"]])
    platform = json.loads((runtime / "runtime.json").read_text())
    if (platform["ref"] != f"runtime/{PLATFORM}/x86_64/{BRANCH}" or platform["commit"] != COMMITS["x86_64"]):
        raise ValueError("The offline runtime differs from the pinned signed Platform")
    checked_copy(runtime / "platform.flatpak", payload / "platform.flatpak", platform["sha256"])
    (payload / "runtime.json").write_text(json.dumps(platform, indent=2) + "\n")
    (payload / "runtime-commit").write_text(platform["commit"] + "\n")
    recipes = [HERE / name for name in ("lease.py", "lease.sh", "lease_result.py")]
    for recipe in recipes:
        shutil.copyfile(recipe, payload / recipe.name)
    compiler = ART / "toolchain/bin/rustc"
    target = "x86_64-unknown-linux-gnu"
    pin = json.loads((ROOT / "rust/toolchain-inputs.json").read_text())
    archive = ART / "toolchain-inputs" / Path(pin["targets"][target]["rust"]["url"]).name
    subprocess.run([sys.executable, HERE.parents[1] / "check-toolchain.py", target, "--rustc", compiler,
                    "--archive", archive], check=True)
    lib = ROOT / "rust/crates/safe-fs/src"
    source = HERE / "flatpak-reader.rs"
    rlib = work / "libsafe_fs.rlib"
    flags = ["--edition=2024", "-Dwarnings", "-C", "opt-level=2"]
    subprocess.run([compiler, *flags, "--crate-name", "safe_fs", "--crate-type=rlib",
                    lib / "lib.rs", "-o", rlib], check=True)
    subprocess.run([compiler, *flags, source, "--extern", "safe_fs=" + str(rlib), "-o", payload / "reader"], check=True)
    inputs = [source, *(lib.glob("*.rs")), *recipes]
    (payload / "inputs.json").write_text(json.dumps({
        "compiler": subprocess.check_output([compiler, "-vV"], text=True), "compilerSha256": sha(compiler),
        "sources": {str(p.relative_to(ROOT)): sha(p) for p in sorted(inputs)},
        **candidate,
        "baseImage": IMAGE_SHA, "guestStatus": plan["status"], "reader": sha(payload / "reader"),
        "downloadOperations": True,
        "stock": next(r["SHA256"] for r in plan["packages"] if Path(r["Filename"]).name.startswith(SOURCE + "_")),
        "runtime": platform,
    }, indent=2) + "\n")
    print(payload, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("apt", "runtime"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--build", type=Path, help="completed native package VM for the full rollback trial")
    args = parser.parse_args()
    prepare(args.apt.resolve(strict=True), args.runtime.resolve(strict=True), args.build.resolve(strict=True) if args.build else None)
