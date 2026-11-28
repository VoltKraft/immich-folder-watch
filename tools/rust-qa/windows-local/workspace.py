"""Compile Rust's Windows x64 test harnesses and execute them on the local QA guest."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
TARGET = "x86_64-pc-windows-msvc"
LOCKS = {"workspace": ROOT / "rust/Cargo.lock", "gui": ROOT / "tools/rust-qa/gui/Cargo.lock"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def test_counts(log):
    matches = re.findall(rb"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; "
                         rb"(\d+) measured; (\d+) filtered out;", log, re.M)
    if len(matches) != 1:
        return None
    return dict(zip(("passed", "failed", "ignored", "measured", "filtered"), map(int, matches[0])))


def harnesses(stream):
    found = {}
    for line in stream.splitlines():
        message = json.loads(line)
        if (message["reason"] == "compiler-artifact" and message["profile"]["test"]
                and message.get("executable")):
            # Compiler paths in the original stream use Windows syntax even during host replay.
            name = PureWindowsPath(message["executable"]).name
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.exe", name) or name in found:
                raise ValueError("Ambiguous Cargo test executable")
            found[name] = {"package": message["package_id"], "target": message["target"]["name"],
                           "kind": message["target"]["kind"], "original": message["executable"]}
    if not found:
        raise ValueError("Cargo produced no workspace test harnesses")
    return found


def check_gui_targets(rows):
    actual = {(row["target"], tuple(row["kind"])) for row in rows.values()}
    expected = {("native_gui_assessment", ("lib",)), ("native-gui-assessment", ("bin",))}
    tests = LOCKS["gui"].parent / "tests"
    expected.update((file.stem, ("test",)) for file in tests.glob("*.rs"))
    if not expected <= actual:
        raise ValueError(f"Missing native GUI test targets: {sorted(expected - actual)}")


def gui_test_sources():
    gui = LOCKS["gui"].parent
    lifecycle = ROOT / "rust/crates/desktop-lifecycle"
    files = [gui / "Cargo.toml", gui / "src/tray-icon.argb", lifecycle / "Cargo.toml",
             *gui.joinpath("tests").glob("*.rs"), *gui.joinpath("src").rglob("*.rs"),
             *lifecycle.joinpath("src").rglob("*.rs")]
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(files)}


def build_harnesses(output, suite, command, env=None, *, graph=None):
    output.mkdir(parents=True, exist_ok=False)
    compiler = output / "compiler.jsonl"
    with compiler.open("xb") as log:
        subprocess.run([*command, "--no-run", "--message-format=json-render-diagnostics"],
                       cwd=LOCKS[suite].parent, env=env, stdout=log, check=True)
    binaries = harnesses(compiler.read_bytes())
    if suite == "gui":
        check_gui_targets(binaries)
    for name, row in binaries.items():
        source = Path(row["original"])
        shutil.copyfile(source, output / name)
        row["sha256"] = digest(output / name)
    receipt = {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "target": TARGET, "rustc": subprocess.check_output(["rustc", "-vV"], text=True),
               "suite": suite, "lockSha256": digest(LOCKS[suite]), "compilerSha256": digest(compiler),
               "binaries": binaries}
    if suite == "gui":
        shutil.copyfile(graph, output / "graph.json")
        receipt.update(graphSha256=digest(output / "graph.json"), testSources=gui_test_sources())
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def build(output):
    subprocess.run([sys.executable, ROOT / "tools/rust-qa/check-toolchain.py", TARGET], check=True)
    build_harnesses(output, "workspace", ["cargo", "test", "--workspace", "--all-targets", "--locked"])


def run(archive, expected, output, suite="workspace"):
    native_architecture = runpy.run_path(str(ROOT / "tools/rust-qa/check-toolchain.py"))["native_architecture"]
    if os.environ.get("GITHUB_ACTIONS") or sys.platform != "win32" or native_architecture() != "x86_64":
        raise ValueError("Run the harnesses on the local Windows x64 VM")
    expected = expected.removeprefix("sha256:")
    if not re.fullmatch("[0-9a-f]{64}", expected) or digest(archive) != expected:
        raise ValueError("The archive differs from the supplied Actions digest")
    output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix="ifw-workspace-") as tmp, ZipFile(archive) as kit:
        root = Path(tmp)
        manifest = json.loads(kit.read("build.json"))
        stream = kit.read("compiler.jsonl")
        rows = harnesses(stream)
        extra = []
        if suite == "gui":
            check_gui_targets(rows)
            extra.append("graph.json")
            reviewed = json.loads((ROOT / "rust/audit/gui-profile.json").read_bytes())
            if (hashlib.sha256(kit.read("graph.json")).hexdigest() != manifest["graphSha256"]
                    or manifest["graphSha256"] != reviewed["targetReportSha256"][TARGET]
                    or manifest["testSources"] != gui_test_sources()):
                raise ValueError("The GUI graph or native test sources differ from the compiler inputs")
        checkout = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if (manifest["target"] != TARGET or not re.fullmatch("[0-9a-f]{40}", manifest["revision"])
                or manifest["revision"] != checkout
                or hashlib.sha256(stream).hexdigest() != manifest["compilerSha256"]
                or manifest.get("suite", "workspace") != suite or manifest["lockSha256"] != digest(LOCKS[suite])
                or set(rows) != set(manifest["binaries"])
                or sorted(kit.namelist()) != sorted(["build.json", "compiler.jsonl", *extra, *rows])):
            raise ValueError("The archive does not match the original native compiler receipt")
        for name, row in rows.items():
            entry = manifest["binaries"][name]
            if row != {k: v for k, v in entry.items() if k != "sha256"}:
                raise ValueError("The test target differs from Cargo's output")
            with kit.open(name) as src, (root / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if digest(root / name) != entry["sha256"]:
                raise ValueError("The archived test binary does not match its receipt")
        env = dict(os.environ, TEMP=tmp, TMP=tmp)
        if suite == "workspace":
            env["IFW_RUST_REQUIRE_WINDOWS_SHORT_NAME"] = "1"
        results = {}
        for name in rows:
            log = output / (name + ".log")
            with log.open("xb") as stream:
                try:
                    rc = subprocess.run([root / name], cwd=root, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=300).returncode
                except subprocess.TimeoutExpired:
                    rc = 124
            results[name] = {"exit": rc, "logSha256": digest(log), "counts": test_counts(log.read_bytes())}
        passed = (all(row["exit"] == 0 and row["counts"] is not None and row["counts"]["failed"] == 0
                      for row in results.values())
                  and any(row["counts"]["passed"] for row in results.values()))
        result = {"revision": manifest["revision"], "archiveSha256": expected, "target": TARGET, "suite": suite,
                  "platform": platform.platform(), "host": "local-vm", "passed": passed, "tests": results}
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("build").add_argument("output", type=Path)
    guest = modes.add_parser("run")
    guest.add_argument("archive", type=Path)
    guest.add_argument("sha256")
    guest.add_argument("output", type=Path)
    guest.add_argument("--suite", choices=LOCKS, default="workspace")
    args = parser.parse_args()
    if args.mode == "build":
        build(args.output.resolve())
    else:
        sys.exit(run(args.archive, args.sha256, args.output.resolve(), args.suite))
