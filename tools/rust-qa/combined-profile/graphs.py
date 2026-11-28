"""Compare Cargo's combined normal/build graph to the individual source reviews."""
from collections import defaultdict
from functools import cache
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

from sources import (FIRST_PARTY, HERE, HYPER_KEY, HYPER_ROOT, QA, ROOT, catalog, hyper_util_source, locked,
                     read, sha256, source_config, source_profile, write)
from storage.evidence import target_graph

spec = importlib.util.spec_from_file_location("rw02_audit", QA / "audit-graph.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
TARGETS = sorted(read(ROOT / "rust/toolchain-inputs.json")["targets"])


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def feature_map(sets):
    return {f"{name} v{version}": sorted(groups) for (name, version), groups in sorted(sets.items())}


def normal_build(cargo, directory, target):
    data = cargo("tree", directory, ["--target", target, "--edges", "normal,build", "--prefix", "none",
                                     "--format", "{p}|{f}"])
    sets = defaultdict(set)
    for line in data.splitlines():
        if line == "[build-dependencies]":
            continue
        identity, features = line.removesuffix(" (*)").split("|", 1)
        name, version, *_ = identity.split()
        if not version.startswith("v"):
            raise ValueError(f"Unrecognized Cargo tree row {line}")
        sets[name, version[1:]].add(tuple(sorted(filter(None, features.split(",")))))
    return dict(sets)


def scope_for(target):
    return ["gui", "realtime", "storage", "yaml", "performance/worker"] + (
        ["linux-services", "portal-dialog"] if "linux" in target else ["windows-services"])


def reproduce_lock(vendor, work, env, toolchain):
    directory = work / "empty-lock-replay"
    (directory / "src").mkdir(parents=True)
    manifest = (HERE / "Cargo.toml").read_text(encoding="utf-8")

    def relocate(match):
        path = (HERE / match[1]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Unexpected local source in the combined manifest")
        return "path = " + json.dumps(str(path))

    relocated, count = re.subn(r'\bpath = "([^"]+)"', relocate, manifest)
    if count != len(FIRST_PARTY) + 3:
        raise ValueError("Unexpected number of first-party and reconstructed manifest paths")
    (directory / "Cargo.toml").write_text(relocated, encoding="utf-8")
    (directory / "src/main.rs").touch()
    cargo = toolchain / "bin" / ("cargo.exe" if (toolchain / "bin/cargo.exe").exists() else "cargo")
    subprocess.run([str(cargo), "generate-lockfile", "--offline", *source_config(vendor)],
                   cwd=directory, env=env, check=True)
    replay = sha256(directory / "Cargo.lock")
    if replay != sha256(HERE / "Cargo.lock"):
        raise ValueError("Cargo did not reproduce the combined lock from the empty standalone root")
    return replay


def resolve(vendor, env, output, toolchain):
    binary = str(toolchain / "bin" / ("cargo.exe" if (toolchain / "bin/cargo.exe").exists() else "cargo"))

    def cargo(operation, directory, args):
        return subprocess.check_output([binary, operation, "--manifest-path", str(directory / "Cargo.toml"),
                                        "--frozen", *source_config(vendor), *args], env=env, cwd=HERE,
                                       encoding="utf-8")

    @cache
    def metadata(directory, target=None):
        args = ["--format-version", "1"]
        if target:
            args += ["--filter-platform", target]
        return json.loads(cargo("metadata", directory, args))

    pool = catalog()
    combined = locked(HERE)
    if combined != pool:
        raise ValueError("The resolved registry identities differ from the source lock catalog")
    approved = source_profile.validate()
    gui = read(ROOT / "rust/audit/gui-profile.json")
    inputs = {name: read(QA / name / "inputs.json") for name in ("storage", "yaml", "realtime")}
    for name, expected in (("gui", gui["lockSha256"]), ("realtime", inputs["realtime"]["lockSha256"]),
                           ("storage", inputs["storage"]["lock_sha256"]), ("yaml", inputs["yaml"]["lock_sha256"])):
        if sha256(QA / name / "Cargo.lock") != expected:
            raise ValueError(f"Changed reviewed {name} lock")
    combined_meta = metadata(HERE)
    packages = {(p["name"], p["version"]): p for p in combined_meta["packages"]}
    checksums = {(name, version, REGISTRY): value for (name, version), value in combined.items()}
    members = {p.resolve(): p.relative_to(ROOT).as_posix() for p in (ROOT / "rust/crates" / n / "Cargo.toml" for n in FIRST_PARTY)}

    @cache
    def external(key):
        data = packages[key]
        root = Path(data["manifest_path"]).resolve().parent
        if key == HYPER_KEY:
            if data["source"] is not None:
                raise ValueError("The combined compiler selected a different hyper-util source")
            archive = vendor.parent.parent / "cache" / vendor.name / hyper_util_source.ARCHIVE.name
            return audit.private_hyper_input(root, archive)
        if data["source"] == REGISTRY and root == vendor / (key[0] + "-" + key[1]):
            return audit.archive_inputs(data, checksums, False)
        if data["source"] is None and key[0] in approved["trees"]:
            return audit.private_gui_input(root, key[0], approved)
        raise ValueError(f"Unexpected external compiler source for {key}")

    def audit_rows(directory, selected):
        rows = []
        for data in sorted(metadata(directory)["packages"], key=lambda p: (p["name"], p["version"])):
            key = data["name"], data["version"]
            if key not in selected:
                continue
            groups = sorted(selected[key])
            features = sorted({f for group in groups for f in group})
            if key[0] in audit.EXCLUDED_PACKAGES or (key[0] in audit.GUI_CRATES and set(features) & audit.EXCLUDED_FEATURES):
                raise ValueError(f"Excluded desktop input selected in {directory}: {key}")
            row = {k: data[k] for k in ("name", "version", "source", "repository", "license", "license_file")}
            row.update(featureSets=groups, features=features, buildScriptsAndMacros=sorted(
                t["name"] for t in data["targets"] if {"custom-build", "proc-macro"} & set(t["kind"])))
            manifest = Path(data["manifest_path"]).resolve()
            if data["source"] or key[0] in approved["trees"] or key == HYPER_KEY:
                if key == HYPER_KEY and (data["source"] is not None or manifest != HYPER_ROOT / "Cargo.toml"):
                    raise ValueError("The individual transport selected a different hyper-util source")
                row.update(external(key))
            elif manifest in members:
                row["repositoryManifest"] = members[manifest]
            elif manifest == directory / "Cargo.toml":
                row["assessmentWorkspaceMember"] = True
            else:
                raise ValueError(f"Unknown path dependency {manifest}")
            rows.append(row)
        if len(rows) != len(selected):
            raise ValueError("Missing a dependency from the selected normal/build graph")
        return rows

    first_party = {(path.parent.name, "0.0.0") for path in members}
    all_selected = set()
    records = {}
    sources_by_key = defaultdict(set)
    for target in TARGETS:
        selected = normal_build(cargo, HERE, target)
        all_selected.update(selected)
        sets_by_spike = {}
        for name in scope_for(target):
            directory = QA / name
            sets = sets_by_spike[name] = normal_build(cargo, directory, target)
            for key in sets:
                sources_by_key[key].add(name)
            if name in ("gui", "realtime"):
                report = {"target": target, "lockSha256": sha256(directory / "Cargo.lock"),
                          "packages": audit_rows(directory, sets), "excludedPackagesOrFeatures": []}
                if name == "gui":
                    report.update(desktopFontAssets=approved["fonts"], textNotices=approved["noticeFiles"])
                    raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
                    if (hashlib.sha256(raw).hexdigest() != gui["targetReportSha256"][target]
                            or fingerprint(feature_map(sets)) != approved["nativeFeatureReports"][target]["nativeFeatureSetsSha256"]):
                        raise ValueError(f"GUI source/notice/feature baseline differs on {target}")
                elif fingerprint(report) != inputs[name]["graphs"][target]["sha256"]:
                    raise ValueError(f"Realtime source/notice/feature baseline differs on {target}")
            if name in ("storage", "yaml"):
                if target_graph(metadata(directory, target)) != inputs[name]["target_graphs"][target]:
                    raise ValueError(f"Reviewed {name} metadata differs on {target}")

        prior = defaultdict(set)
        for sets in sets_by_spike.values():
            for key, groups in sets.items():
                prior[key].update(groups)
        newly_combined, newly_active = {}, {}
        for key, groups in selected.items():
            if key[0] == "ifw-combined-assessment" or key in first_party:
                continue
            if key not in prior:
                raise ValueError(f"New package lacks individual native review: {target} {key}")
            before = {f for group in prior[key] for f in group}
            introduced = sorted({f for group in groups for f in group} - before)
            identity = " ".join(key)
            if introduced:
                newly_active[identity] = introduced
            novel = sorted(groups - prior[key])
            if novel:
                newly_combined[identity] = {"combined": novel, "individual": {
                    name: sorted(sets[key]) for name, sets in sets_by_spike.items() if key in sets}}
        slots = feature_map(selected)
        typed = cargo("tree", HERE, ["--target", target, "--edges", "normal,build", "--prefix", "indent",
                                      "--charset", "ascii", "--format", "{p}|{f}"])
        # Local path identities were verified above. Strip only absolute path annotations,
        # retaining Cargo's tree structure, build edges, proc macros and separate feature sets.
        typed = re.sub(r" \((?!proc-macro\))[^\n|]*\)(?=\|)", "", typed)
        (output / (target + ".tree")).write_text(typed, encoding="utf-8", newline="\n")
        counts = {name: len(sets) for name, sets in sets_by_spike.items()}
        result = {"packages": len(selected), "registryPackages": sum(key in combined for key in selected),
                  "normalBuildFeatureSetsSha256": fingerprint(slots), "treeSha256": sha256(output / (target + ".tree")),
                  "individualPackageCounts": counts, "newlyActiveFeatures": newly_active,
                  "newFeatureCombinations": sorted(newly_combined)}
        write(output / (target + ".json"), {"summary": result, "features": slots, "combinations": newly_combined})
        records[target] = result

    inventory = []
    for key in sorted(all_selected):
        if key not in combined and key[0] not in approved["trees"] and key != HYPER_KEY:
            continue
        external_data = external(key)
        data = packages[key]
        entry = dict(name=key[0], version=key[1], source=data["source"], declared=data["license"], repository=data["repository"],
                     components=sorted(sources_by_key[key]), **external_data)
        entry["buildScriptsAndMacros"] = sorted(t["name"] for t in data["targets"]
                                               if {"custom-build", "proc-macro"} & set(t["kind"]))
        inventory.append(entry)
    return records, inventory
