"""Qualify the single offline RW-02 Cargo candidate and optionally execute it on the native host."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from check_imports import compare
from graphs import TARGETS, fingerprint, reproduce_lock, resolve
from licenses import inventory, totals
from native import run_native
import relink
from units import compiler_units
from sources import FIRST_PARTY, HERE, QA, ROOT, SCOPE, SPIKES, catalog, local_caches, prepare, read, sha256, source_profile, write


def environment(work, toolchain):
    # MSVC and Clang discovery use the host's selected Visual Studio tool paths.
    # Source/flag/credential variables do not enter the offline assessment.
    keep = {"path", "pathext", "systemroot", "windir", "comspec", "processor_architecture", "number_of_processors",
            "include", "lib", "libpath", "platform", "platformtoolset", "vscmd_arg_tgt_arch", "vscmd_arg_host_arch",
            "vctoolsinstalldir", "vcinstalldir", "vsinstalldir", "windowssdkdir", "windowssdkversion",
            "windowssdkbinpath", "windowssdkverbinpath", "universalcrtsdkdir", "ucrtversion",
            "programfiles", "programfiles(x86)", "programw6432", "programdata", "extensionsdkdir"}
    env = {key: value for key, value in os.environ.items() if key.lower() in keep}
    for local in ("home", "empty-cargo-home", "tmp", "appdata", "localappdata"):
        (work / local).mkdir()
    env.update(PATH=str(toolchain / "bin") + os.pathsep + os.environ["PATH"], HOME=str(work / "home"),
               USERPROFILE=str(work / "home"), APPDATA=str(work / "appdata"),
               LOCALAPPDATA=str(work / "localappdata"), TMP=str(work / "tmp"), TEMP=str(work / "tmp"),
               TMPDIR=str(work / "tmp"), CARGO_HOME=str(work / "empty-cargo-home"), CARGO_NET_OFFLINE="true",
               GIT_OPTIONAL_LOCKS="0")
    return env


def source_witness():
    files = [ROOT / "rust/toolchain-inputs.json", ROOT / "rust/Cargo.toml",
             ROOT / "rust/tests/fixtures/behavior/legacy-upload.json", QA / "audit-graph.py",
             QA / "check-toolchain.py", QA / "storage/evidence.py", QA / "gui/source_profile.py",
             QA / "gui/src/fonts.rs", QA / "yaml/prepare.py"]
    files += list((ROOT / "rust/audit").glob("*.json"))
    files += [p for d in SPIKES for p in [QA / d / "Cargo.toml", QA / d / "Cargo.lock"]]
    files += [QA / d / "inputs.json" for d in ("storage", "yaml", "realtime")]
    for name in FIRST_PARTY:
        crate = ROOT / "rust/crates" / name
        files += [crate / "Cargo.toml", *(crate / "src").rglob("*.rs")]
    files += list((ROOT / "rust/assets/fonts").glob("*"))
    files += [p for p in HERE.iterdir() if p.is_file()] + list((HERE / "src").glob("*.rs"))
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(files))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", choices=TARGETS, help="also link and exercise the selected native host")
    parser.add_argument("--fetch", action="store_true", help="acquire missing checksum-pinned archival inputs")
    parser.add_argument("--output", type=Path, help="new receipt directory below artifacts/rust/combined-profile/runs")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=3)
    parser.add_argument("--relink", action="store_true", help="also rebuild an edited LGPL binding on native Linux")
    parser.add_argument("--check-imports", action="store_true", help="also compare both Microsoft import archives to the cached upstream revision")
    args = parser.parse_args()
    if args.relink and (not args.native or "linux" not in args.native):
        parser.error("--relink requires --native with a Linux target")
    runs = SCOPE / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    if args.output:
        output = args.output.resolve()
        if not output.is_relative_to(runs) or output == runs:
            raise ValueError(f"Use a new output directory below {runs}")
        output.mkdir(parents=True)
    else:
        output = Path(tempfile.mkdtemp(prefix="assessment-", dir=runs))
    area = SCOPE / "work"
    area.mkdir(exist_ok=True)
    toolchain = ROOT / "artifacts/rust/toolchain"
    record = {"passed": False, "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                                   text=True).strip(),
              "workflow": os.environ.get("GITHUB_RUN_ID"), "sources": source_witness()}
    try:
        with tempfile.TemporaryDirectory(prefix="profile-", dir=area) as scratch:
            work = Path(scratch)
            env = environment(work, toolchain)
            compiler = subprocess.check_output(["rustc", "-vV"], env=env, text=True)
            cargo = subprocess.check_output(["cargo", "-Vv"], env=env, text=True)
            inputs = read(ROOT / "rust/toolchain-inputs.json")
            if (f"commit-hash: {inputs['commit']}" not in compiler.splitlines()
                    or f"release: {inputs['version']}" not in compiler.splitlines()
                    or f"release: {inputs['version']}" not in cargo.splitlines()
                    or "commit-hash: 3acc79c0c841844675bc53a605922dbfc441e750" not in cargo.splitlines()):
                raise ValueError("Expected the pinned rustc and Cargo binaries")
            record.update(rustc=compiler.splitlines(), cargo=cargo.splitlines(), lock=sha256(HERE / "Cargo.lock"))
            print("Preparing and authenticating the private directory sources", flush=True)
            vendor, staged, text = prepare(work, local_caches(), args.fetch)
            print("Checking the four normal/build graphs and the original substrate reviews", flush=True)
            record["emptyLockReplaySha256"] = reproduce_lock(vendor, work, env, toolchain)
            graphs, rows = resolve(vendor, env, output, toolchain)
            catalog_record = inventory(rows, vendor, staged, text)
            write(output / "inventory.json", catalog_record)
            write(output / "source-trees.json", staged)
            actual = {"lockSha256": record["lock"], "registryLockCount": len(catalog()),
                      "allCompilerTreesSha256": fingerprint(staged), "inventorySha256": fingerprint(catalog_record),
                      "summary": totals(catalog_record), "targets": graphs}
            write(output / "profile.json", actual)
            if actual != read(HERE / "review.json"):
                raise ValueError("The combined graph differs from the source/feature review")
            if args.check_imports:
                original = ROOT / "artifacts/rust/windows-imports/input/windows-rs-db06b51.tar.gz"
                record["microsoftImports"] = compare(original, vendor)
            record["profileSha256"] = sha256(output / "profile.json")
            subprocess.run(["rustfmt", "--edition", "2024", "--config", "skip_children=true", "--check",
                            *sorted((HERE / "src").glob("*.rs"))], env=env, check=True)
            if args.native:
                print(f"Linking and exercising {args.native}", flush=True)
                record["native"] = run_native(args.native, toolchain, vendor, work / "build", output, env, args.jobs)
                record["native"]["compilerUnits"] = compiler_units(output, args.native)
                if args.relink:
                    record["relink"] = relink.run(toolchain, vendor, work / "build", output, env, args.jobs,
                                                  args.native, record["native"])
            source_profile.validate()
            if record["sources"] != source_witness():
                raise ValueError("Source files changed during qualification")
            record["passed"] = True
    finally:
        record["outputs"] = {p.name: sha256(p) for p in sorted(output.iterdir())
                             if p.is_file() and p.name != "result.json"}
        write(output / "result.json", record)
        print(output / "result.json", flush=True)


if __name__ == "__main__":
    main()
