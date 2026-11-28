"""Verify RDS-01 against the workspace's locked, native normal and build dependencies."""

import argparse
from collections import defaultdict, deque
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
QA = HERE.parent
ROOT = QA.parents[1]
WORKSPACE = ROOT / "rust"
sys.path.insert(0, str(QA))
from storage.evidence import sha256


# Assign each workspace member its architectural role when it is introduced.
ROLES = {
    "desktop-lifecycle": "generic lifecycle policy",
    "desktop-platform-log": "generic native log adapter",
    "safe-fs": "generic native filesystem adapter",
    "ifw-immich": "product transport adapter",
    "ifw-legacy": "product legacy codec",
}
RENDERER = {"egui", "eframe", "epaint", "winit", "wgpu"}
OS = {"windows", "winapi", "dbus", "libdbus", "zbus", "libc", "rustix", "nix"}
IO_IMPLEMENTATIONS = {"reqwest", "ureq", "hyper", "curl", "rusqlite", "libsqlite3", "sqlx"}


def in_family(name, families):
    return any(name == family or name.startswith((family + "-", family + "_")) for family in families)


def violation(root, name):
    if in_family(name, RENDERER):
        return "renderer or GUI inspection belongs in presentation"
    if ROLES[root].startswith("generic") and (
            ROLES.get(name, "").startswith("product") or in_family(name, {"ifw", "immich"})):
        return "generic crates must be independent of the product"
    if root == "desktop-lifecycle" and (name in {"safe-fs", "desktop-platform-log"}
                                       or in_family(name, OS | IO_IMPLEMENTATIONS)):
        return "the lifecycle policy must be independent of native, HTTP and database adapters"
    return None


def cargo_output(cargo, workspace, env, *args):
    completed = subprocess.run([str(cargo), *args], cwd=workspace, env=env, capture_output=True,
                               encoding="utf-8", errors="strict", timeout=120)
    if completed.returncode:
        raise RuntimeError(f"Cargo {args[0]} exited {completed.returncode}\n{completed.stderr.strip()}")
    return completed.stdout


def source_label(package, workspace):
    if package["source"]:
        return package["source"]
    relative = os.path.relpath(Path(package["manifest_path"]).parent, workspace)
    return "path:" + Path(relative).as_posix()


def resolve_edge(nodes, packages, parent, name, version, origin, kind):
    # Metadata supplies canonical package IDs even when Cargo dependencies are renamed.
    matches = defaultdict(set)
    for dep in nodes[parent]["deps"]:
        candidate = packages[dep["pkg"]]
        if (candidate["name"], "v" + candidate["version"]) == (name, version):
            for declaration in dep["dep_kinds"]:
                if (declaration["kind"] or "normal") == kind:
                    matches[dep["pkg"]].add((dep["name"], declaration["target"] or ""))
    if len(matches) > 1 and origin:
        folder = Path(origin[0].removeprefix("(").removesuffix(")"))
        paths = {key: rules for key, rules in matches.items()
                 if packages[key]["source"] is None and Path(packages[key]["manifest_path"]).parent == folder}
        if paths:
            matches = paths
    if len(matches) != 1:
        raise ValueError(f"Expected one resolved identity for {packages[parent]['name']} -> {name} {version}")
    return next(iter(matches.items()))


def active_graph(members, packages, nodes, tree):
    # Metadata can include optional normal dependencies enabled only by tests. The joint
    # workspace tree excludes dev edges while retaining real cross-member feature unification.
    roots, children, stack = defaultdict(set), defaultdict(dict), []
    kinds = []
    for line in tree.splitlines():
        if not line:
            continue
        if line.endswith("[build-dependencies]") and "PKG|" not in line:
            kinds[len(line.removesuffix("[build-dependencies]")) // 4] = "build"
            continue
        prefix, row = line.split("PKG|", 1)
        display, feature_text = row.removesuffix(" (*)").rsplit("|", 1)
        name, version, *origin = display.split(" ", 2)
        depth, remainder = divmod(len(prefix), 4)
        if remainder or depth > len(stack):
            raise ValueError(f"Unexpected Cargo tree depth in {line!r}")
        del stack[depth:]
        del kinds[depth:]
        features = tuple(sorted(filter(None, feature_text.split(","))))
        if stack:
            parent = stack[-1]
            kind = kinds[-1]
            key, declarations = resolve_edge(nodes, packages, parent[0], name, version, origin, kind)
            node = (key, features)
            children[parent][node, kind] = declarations
        else:
            key = members[name]
            if version != "v" + packages[key]["version"]:
                raise ValueError(f"Unexpected Cargo workspace root in {line!r}")
            node = (key, features)
            roots[name].add(node)
        stack.append(node)
        kinds.append("normal")
    if roots.keys() != members.keys():
        raise ValueError("The normal/build tree does not cover every workspace member")
    return roots, children


def profile(workspace, root, roots, packages, children):
    selected, edges, problems, seen = defaultdict(set), defaultdict(set), [], set()
    pending = deque((node, [root]) for node in sorted(roots))
    while pending:
        node, route = pending.popleft()
        if node in seen:
            continue
        seen.add(node)
        package_id, features = node
        selected[package_id].add(features)
        if len(route) > 1 and (reason := violation(root, route[-1])):
            problems.append(f"{' -> '.join(route)}: {reason}")
        for (child, kind), declarations in children[node].items():
            edges[package_id, child[0], kind].update(declarations)
            pending.append((child, [*route, packages[child[0]]["name"]]))

    labels = {key: f"{packages[key]['name']}@{packages[key]['version']} [{source_label(packages[key], workspace)}]"
              for key in selected}
    return {
        "role": ROLES[root],
        "packages": {labels[key]: sorted(groups) for key, groups in selected.items()},
        "edges": sorted([labels[a], labels[b], kind, sorted(declarations)]
                        for (a, b, kind), declarations in edges.items()),
    }, problems


def inspect(workspace, target, cargo, env):
    metadata = json.loads(cargo_output(cargo, workspace, env, "metadata", "--format-version", "1",
                                       "--locked", "--offline", "--filter-platform", target))
    packages = {p["id"]: p for p in metadata["packages"]}
    nodes = {n["id"]: n for n in metadata["resolve"]["nodes"]}
    members = {packages[key]["name"]: key for key in metadata["workspace_members"]}
    unknown = members.keys() - ROLES.keys()
    if unknown:
        raise ValueError("Assign an architectural role in ROLES for new workspace members: " + ", ".join(sorted(unknown)))
    if missing := ROLES.keys() - members.keys():
        raise ValueError("Workspace members missing from the checked manifest: " + ", ".join(sorted(missing)))
    tree = cargo_output(cargo, workspace, env, "tree", "--locked", "--offline", "--target", target,
                        "--workspace", "--edges", "normal,build", "--charset", "ascii", "--format", "PKG|{p}|{f}")
    roots, children = active_graph(members, packages, nodes, tree)
    profiles, violations = {}, []
    for name, root in sorted(roots.items()):
        profiles[name], problems = profile(workspace, name, root, packages, children)
        violations.extend(problems)
    manifests = [Path(packages[key]["manifest_path"]) for key in members.values()]
    return profiles, sorted(set(violations)), manifests


def main():
    pins_path = WORKSPACE / "toolchain-inputs.json"
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(pins["targets"]))
    parser.add_argument("--output", type=Path, required=True, help="atomically replace the JSON result for this run")
    args = parser.parse_args()
    tools = ROOT / "artifacts/rust/toolchain/bin"
    suffix = ".exe" if os.name == "nt" else ""
    cargo, rustc = tools / ("cargo" + suffix), tools / ("rustc" + suffix)
    env = dict(os.environ, RUSTC=str(rustc), CARGO_NET_OFFLINE="true")
    env.setdefault("CARGO_HOME", str(ROOT / "artifacts/rust/cargo-home"))
    check = QA / "check-toolchain.py"
    report = {"status": "failed", "target": args.target, "edgeColumns": ["from", "to", "kind", "manifestDeclarations"],
              "declarationColumns": ["cargoName", "declaredTargetCondition"]}
    try:
        report["source"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        report["rustc"] = subprocess.check_output([sys.executable, str(check), args.target, "--rustc", str(rustc)],
                                                  cwd=ROOT, env=env, text=True).strip()
        version = cargo_output(cargo, WORKSPACE, env, "-vV").splitlines()
        if f"release: {pins['version']}" not in version or f"host: {args.target}" not in version:
            raise ValueError("The workspace Cargo version or host differs from the pinned toolchain")
        report.update(cargoVersion=version[0], cargoSha256=sha256(cargo), lockSha256=sha256(WORKSPACE / "Cargo.lock"))
        profiles, errors, manifests = inspect(WORKSPACE, args.target, cargo, env)
        inputs = [HERE / "check.py", QA / "storage/evidence.py", check, pins_path, WORKSPACE / "Cargo.toml", *manifests]
        report.update(profiles=profiles, violations=errors,
                      inputSha256={path.relative_to(ROOT).as_posix(): sha256(path) for path in inputs})
        if not errors:
            report["status"] = "passed"
    except (OSError, subprocess.SubprocessError, KeyError, RuntimeError, ValueError) as error:
        report["error"] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=args.output.parent,
                                     delete=False) as temp:
        json.dump(report, temp, indent=2, sort_keys=True)
        temp.write("\n")
    os.replace(temp.name, args.output)
    for problem in report.get("violations", []):
        print(problem, file=sys.stderr)
    print(report.get("error") or f"RDS-01 {args.target}: {report['status']} ({args.output})")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
