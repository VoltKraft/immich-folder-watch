"""Bind both native scalar captures to the Release DLL and the selected .NET runtime files."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_VERSION = "10.0.12"


def installed_corelib(frameworks):
    versions = re.findall(r"^Microsoft\.NETCore\.App (\S+) \[([^\r\n]+)\]\r?$", frameworks, re.MULTILINE)
    roots = [Path(root) for version, root in versions if version == RUNTIME_VERSION]
    if len(roots) != 1:
        raise ValueError(f"Expected one installed Microsoft.NETCore.App {RUNTIME_VERSION}, found {len(roots)}")
    return roots[0] / RUNTIME_VERSION / "System.Private.CoreLib.dll", [version for version, _ in versions]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=json.loads((ROOT / "rust/toolchain-inputs.json").read_text())["targets"])
    parser.add_argument("assembly", type=Path)
    parser.add_argument("ordinary", type=Path)
    parser.add_argument("managed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    installed_host = shutil.which("dotnet")
    if not installed_host:
        raise FileNotFoundError("The native dotnet host is missing from PATH")
    host = Path(installed_host).resolve(strict=True)
    sdk = subprocess.check_output([host, "--version"], cwd=ROOT, text=True).strip()
    expected_sdk = json.loads((ROOT / "global.json").read_text())["sdk"]["version"]
    if sdk != expected_sdk:
        raise ValueError(f"Expected SDK {expected_sdk}, found {sdk}")
    frameworks = subprocess.check_output([host, "--list-runtimes"], cwd=ROOT, text=True)
    corelib, versions = installed_corelib(frameworks)
    arch = "Arm64" if args.target.startswith("aarch64-") else "X64"
    expected = {"Runtime": RUNTIME_VERSION, "CoreLibSha256": sha256(corelib), "OracleAssemblySha256": sha256(args.assembly),
                "ProcessArchitecture": arch, "OSArchitecture": arch, "OS": "windows" if "windows" in args.target else "linux"}
    manifests = {}
    for directory, managed in ((args.ordinary, False), (args.managed, True)):
        path = directory / "manifest.json"
        data = json.loads(path.read_bytes())
        for key, value in expected.items():
            if data.get(key) != value:
                raise ValueError(f"{directory.name}: {key} expected {value}, observed {data.get(key)}")
        if data["GlobalizationInvariantRequested"] is not managed:
            raise ValueError(f"{directory.name}: unexpected globalization mode")
        manifests[directory.name] = {"sha256": sha256(path), "coreLibBuild": data["CoreLibBuild"]}
    result = {"format": "ifw-native-scalar-runtime-v1", "target": args.target, "sdk": sdk, "hostSha256": sha256(host),
              "installedNetCoreVersions": versions, "runtime": expected, "manifests": manifests}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Both {args.target} captures used the Release DLL and Microsoft.NETCore.App {RUNTIME_VERSION} with SDK {sdk}.")


if __name__ == "__main__":
    main()
