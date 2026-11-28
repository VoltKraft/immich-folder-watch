"""Compare the four complete staged startup audits with the original ordinary renderer reports."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA))
from gui.startup.audit_profile import BASE, FEATURES, LOCAL, UPDATED, UPDATED_YAML
from gui.startup import qualify
from gui import source_profile

AUDIT = QA / "audit-graph.py"
STAGED_REPORTS = {
    "x86_64-unknown-linux-gnu": "3e84d4df1f4e63cbac21b98b36d9ab79aa14bafd12702ae5f3b9b9897837b48e",
    "aarch64-unknown-linux-gnu": "b2f22a81c6d3683cc124ce751f20187d7c5b90ccd35a5ad5e8c7268d133b2cd6",
    "x86_64-pc-windows-msvc": "79a0ed7a1e0ca41324862e43a95fa17182140a36a18af5726f90b9249e7d5763",
    "aarch64-pc-windows-msvc": "1e74eb803d67b0f21e7e9545bc1705ef0673ceb789f60284036d7b854734ab89",
}


def current_manifest(output, env):
    gui, _ = qualify.stage(output)
    project = output / "project"
    scopes = [f"tools/rust-qa/{crate}/{part}" for crate in ("gui", "yaml")
              for part in ("Cargo.toml", "Cargo.lock", "src", "tests", "examples")]
    scopes.extend(("rust/Cargo.toml", "rust/crates/desktop-lifecycle"))
    names = subprocess.check_output(["git", "diff", "--name-only", "-z", BASE, UPDATED, "--", *scopes],
                                    cwd=ROOT).decode().split("\0")
    expected = {"tools/rust-qa/yaml/src/anchors.rs", "tools/rust-qa/yaml/src/model.rs"}
    if set(filter(None, names)) != expected:
        raise ValueError("Expected only the two reviewed YAML source changes at the updated revision")
    for name in sorted(expected):
        (project / name).write_bytes(subprocess.check_output(["git", "show", UPDATED + ":" + name], cwd=ROOT))
    subprocess.run(["git", "apply", "--no-index", "--whitespace=error", str(HERE / "language.patch")],
                   env={**os.environ, "GIT_CEILING_DIRECTORIES": str(output)}, cwd=gui, check=True)
    subprocess.run(["cargo", "metadata", "--offline", "--format-version", "1"], cwd=gui, env=env,
                   stdout=subprocess.DEVNULL, check=True)
    return gui / "Cargo.toml"


def verify_yaml_update(before, after):
    expected = deepcopy(before)
    yaml = [p for p in expected["packages"] if p["name"] == "ifw-yaml-assessment"]
    if "linux" in before["target"]:
        if len(yaml) != 1:
            raise ValueError("Expected exactly one first-party YAML library")
        _, manifest_sha, source_sha = LOCAL["ifw-yaml-assessment"]
        witness = yaml[0].get("firstPartyLibrary")
        if witness != {"entry": "src/lib.rs", "revision": BASE, "manifestSha256": manifest_sha,
                       "sourcesSha256": source_sha}:
            raise ValueError("The reference report differs from the original YAML library")
        witness.update(revision=UPDATED, sourcesSha256=UPDATED_YAML)
    elif yaml:
        raise ValueError("The Windows GUI should not select the Linux YAML startup reader")
    if expected != after:
        raise ValueError(f"Complete GUI report changed outside the reviewed YAML library on {before['target']}")
    return {"packages": len(before["packages"]), "updatedLinuxLibrary": bool(yaml)}


def verify_diff(before, after):
    target = before["target"]
    if before["lockSha256"] == after["lockSha256"]:
        raise ValueError("The composed and standalone locks unexpectedly agree")
    if {k: v for k, v in before.items() if k not in ("lockSha256", "packages")} != {
            k: v for k, v in after.items() if k not in ("lockSha256", "packages")}:
        raise ValueError(f"The target, font, notice or exclusion report changed on {target}")
    def packages(report):
        return {(row["name"], row["version"]): row for row in report["packages"]}
    old, new = packages(before), packages(after)
    if old.keys() - new.keys():
        raise ValueError(f"Original libraries disappeared on {target}")
    changed = []
    for key, previous in old.items():
        current = new[key]
        if current == previous:
            continue
        if {k: v for k, v in current.items() if k not in ("features", "featureSets")} != {
                k: v for k, v in previous.items() if k not in ("features", "featureSets")}:
            raise ValueError(f"Original metadata, notices or sources changed for {key} on {target}")
        changed.append(" ".join(key))
    added = sorted(" ".join(k) for k in new.keys() - old.keys())
    if "windows" in target and (added or changed or before["packages"] != after["packages"]):
        raise ValueError(f"The Windows package rows differ on {target}")
    if "linux" in target:
        if not new["ifw-yaml-assessment", "0.0.0"].get("firstPartyLibrary"):
            raise ValueError("The staged Linux GUI lacks the reviewed YAML library")
        if not new["base64", "0.23.1"].get("filteredCompilerSource"):
            raise ValueError("The staged Linux GUI lacks evidence of its filtered compiler source")
    return {"newPackages": added, "changedFeatureRows": sorted(changed),
            "originalPackages": len(old), "stagedPackages": len(new)}


def run(args):
    stage = args.stage.resolve(strict=True)
    staged = stage / "project/tools/rust-qa/gui/Cargo.toml"
    vendor = args.vendor.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "artifacts/rust"):
        raise ValueError("Use a fresh output directory below artifacts/rust")
    home = output / "cargo-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text('[source.crates-io]\nreplace-with = "startup"\n[source.startup]\ndirectory = '
                                      + json.dumps(str(vendor)) + "\n", encoding="utf-8")
    env = {"PATH": str(args.toolchain.resolve(strict=True) / "bin") + os.pathsep + os.environ["PATH"],
           "CARGO_HOME": str(home), "CARGO_NET_OFFLINE": "true", "CARGO_BUILD_JOBS": "1"}
    if args.current_yaml:
        original, candidate = staged, current_manifest(output / "current", env)
        pins = STAGED_REPORTS
        compare = verify_yaml_update
    else:
        ordinary, _ = qualify.stage(output / "ordinary")
        original, candidate = ordinary / "Cargo.toml", staged
        pins = qualify.baseline_json("rust/audit/gui-profile.json")["targetReportSha256"]
        compare = verify_diff
    results = {}
    for target in FEATURES:
        first, second = output / ("original-" + target + ".json"), output / (target + ".json")
        for manifest, dest in ((original, first), (candidate, second)):
            subprocess.run([sys.executable, AUDIT, manifest, target, dest, "--verify-unpacked", "--startup-vendor", vendor],
                           cwd=ROOT, env=env, check=True)
        if source_profile.sha(first) != pins[target]:
            raise ValueError(f"The complete original GUI report differs on {target}")
        delta = compare(json.loads(first.read_bytes()), json.loads(second.read_bytes()))
        if not args.current_yaml and source_profile.sha(second) != STAGED_REPORTS[target]:
            raise ValueError(f"The complete historical startup report differs on {target}")
        results[target] = dict(delta, originalSha256=source_profile.sha(first), stagedSha256=source_profile.sha(second))
    drivers = [Path(__file__), HERE / "qualify.py", HERE / "language.patch", HERE / "audit_profile.py",
               HERE / "vendor.py", AUDIT, QA / "gui/source_profile.py",
               QA / "storage/evidence.py", QA / "yaml/prepare.py"]
    summary = {"targets": results, "yamlSourceRevision": UPDATED if args.current_yaml else BASE,
               "drivers": {p.relative_to(ROOT).as_posix(): source_profile.sha(p) for p in drivers},
               "cargo": subprocess.check_output(["cargo", "--version"], env=env, text=True).strip()}
    (output / "results.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True, help="Source snapshot created by qualify.py")
    parser.add_argument("--vendor", type=Path, required=True, help="Directory source reconstructed by vendor.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--current-yaml", action="store_true",
                        help="Compare the historical startup GUI with its updated bb3afd5 YAML source")
    parser.add_argument("--toolchain", type=Path, default=ROOT / "artifacts/rust/toolchain")
    run(parser.parse_args())
