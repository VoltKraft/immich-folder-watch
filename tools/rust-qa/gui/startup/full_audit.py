"""Compare the four complete staged startup audits with the original ordinary renderer reports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
sys.path.insert(0, str(QA))
from gui.startup.audit_profile import FEATURES
from gui import source_profile

AUDIT = QA / "audit-graph.py"


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
    candidate = stage / "project/tools/rust-qa/gui/Cargo.toml"
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
    original = json.loads((ROOT / "rust/audit/gui-profile.json").read_bytes())
    results = {}
    for target in FEATURES:
        first, second = output / ("original-" + target + ".json"), output / (target + ".json")
        for manifest, dest, extra in ((QA / "gui/Cargo.toml", first, []), (candidate, second, ["--startup-vendor", vendor])):
            subprocess.run([sys.executable, AUDIT, manifest, target, dest, "--verify-unpacked", *extra],
                           cwd=ROOT, env=env, check=True)
        if source_profile.sha(first) != original["targetReportSha256"][target]:
            raise ValueError(f"The complete original GUI report differs on {target}")
        delta = verify_diff(json.loads(first.read_bytes()), json.loads(second.read_bytes()))
        results[target] = dict(delta, originalSha256=source_profile.sha(first), stagedSha256=source_profile.sha(second))
    drivers = [Path(__file__), HERE / "audit_profile.py", HERE / "vendor.py", AUDIT, QA / "gui/source_profile.py",
               QA / "storage/evidence.py", QA / "yaml/prepare.py"]
    summary = {"targets": results, "drivers": {p.relative_to(ROOT).as_posix(): source_profile.sha(p) for p in drivers},
               "cargo": subprocess.check_output(["cargo", "--version"], env=env, text=True).strip()}
    (output / "results.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True, help="Source snapshot created by qualify.py")
    parser.add_argument("--vendor", type=Path, required=True, help="Directory source reconstructed by vendor.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path, default=ROOT / "artifacts/rust/toolchain")
    run(parser.parse_args())
