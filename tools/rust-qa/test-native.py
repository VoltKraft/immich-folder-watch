"""Build and exercise the RW-02 probes on their actual host and retain the observations."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "tools/rust-qa"
WORKSPACE = ROOT / "rust"


def main():
    inputs = json.loads((WORKSPACE / "toolchain-inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["targets"]))
    args = parser.parse_args()
    evidence = ROOT / "artifacts/rust/feasibility" / args.target
    evidence.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    cargo_target = ROOT / "artifacts/rust/build" / args.target
    scalar_project = str(QA / "legacy/LegacyScalarOracle.csproj")
    empty_feed = ROOT / "artifacts/rust/empty-nuget-feed"
    empty_feed.mkdir(exist_ok=True)
    env = {**os.environ, "CARGO_TARGET_DIR": str(cargo_target),
           "IFW_ORACLE_EXPECT_ARCH": "arm64" if args.target.startswith("aarch64-") else "x64",
           "DOTNET_CLI_HOME": str(ROOT / "artifacts/rust/dotnet-cli"),
           "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false",
           "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1"}
    env.setdefault("CARGO_HOME", str(ROOT / "artifacts/rust/cargo-home"))
    result = {
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "modifiedSources": subprocess.check_output(
            ["git", "status", "--porcelain", "--", "rust", "tools/rust-qa", ".github/workflows/rust-feasibility.yaml"],
            cwd=ROOT, text=True,
        ).splitlines(),
        "workflowRun": os.getenv("GITHUB_RUN_ID"),
        "target": args.target,
        "operatingSystem": platform.platform(),
        "lockSha256": hashlib.sha256((WORKSPACE / "Cargo.lock").read_bytes()).hexdigest(),
        "steps": {},
    }
    commands = {
        "compiler": [sys.executable, str(QA / "check-toolchain.py"), args.target],
        "format": ["cargo", "fmt", "--all", "--check"],
        "clippy": ["cargo", "clippy", "--frozen", "--workspace", "--all-targets", "--", "-D", "warnings"],
        "tests": ["cargo", "test", "--frozen", "--workspace", "--", "--show-output"],
        "release-probes": ["cargo", "build", "--frozen", "--workspace", "--release", "--examples", "--bins"],
        "window-reference": [
            sys.executable, str(QA / "replay-window.py"),
            str(cargo_target / "release/examples" / ("window_trace" + suffix)),
        ],
        # This BCL-only console program needs no WPF targeting pack or NuGet
        # sources, even though the shipping solution enables Windows targeting.
        "legacy-restore": ["dotnet", "restore", scalar_project, "--source", str(empty_feed),
                           "-p:EnableWindowsTargeting=false"],
        "legacy-oracle": ["dotnet", "run", "--no-restore", "--configuration", "Release", "--project",
                          scalar_project, "-p:EnableWindowsTargeting=false", "--", "export", str(evidence / "scalar-reference")],
        "legacy-reference": [
            sys.executable, str(QA / "legacy/verify.py"), "--probe", str(cargo_target / "release" / ("legacy-probe" + suffix)),
            "--scalar-reference", str(evidence / "scalar-reference"),
            "--fixtures", str(WORKSPACE / "tests/fixtures/legacy"), "--output", str(evidence / "legacy.json"),
        ],
    }
    for name, command in commands.items():
        log = evidence / f"{name}.log"
        print(f"Running {name}", flush=True)
        directory = WORKSPACE if command[0] == "cargo" else ROOT
        with log.open("wb") as stream:
            try:
                status = subprocess.run(command, cwd=directory, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=900).returncode
            except subprocess.TimeoutExpired:
                status = 124
                stream.write(b"Timed out after 900 seconds.\n")
        result["steps"][name] = {"exitCode": status, "log": log.name}
        if name == "tests" and os.name == "nt":
            observations = [line.removeprefix("distinct_short_name=") for line
                            in log.read_text(encoding="utf-8", errors="replace").splitlines()
                            if line.startswith("distinct_short_name=")]
            result["windowsDistinctShortName"] = {"observation": observations, "verified": observations == ["true"]}
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(log.read_text(encoding="utf-8", errors="replace"), end="", flush=True)
        if status:
            raise SystemExit(status)


if __name__ == "__main__":
    main()
