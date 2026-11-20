"""Build the actual shipping Core project and a thin development-only caller offline."""

import json
import os
from pathlib import Path
import subprocess


def reference_sdk(artifacts):
    default = artifacts.parent / "flatpak-local-2.11.2/sdk"
    return Path(os.environ.get("IFW_QA_REFERENCE_SDK", default)).resolve(strict=True)


def build_reference(root, here, artifacts, output, sha):
    sdk = reference_sdk(artifacts)
    packages = Path(os.environ.get("IFW_QA_REFERENCE_PACKAGES", artifacts.parent / "nuget-packages")).resolve(strict=True)
    if not packages.is_relative_to(artifacts.parent) or packages == artifacts.parent:
        raise ValueError("Select a dedicated package cache below the project artifacts directory")
    pin = json.loads((root / "global.json").read_text())["sdk"]["version"]
    if not (sdk / "sdk" / pin).is_dir():
        raise RuntimeError(f"Missing isolated reference SDK {pin} under {sdk}")
    destination = output / "dotnet"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "NuGet.Config").write_text('<configuration><packageSources><clear/><add key="cache" value="/packages"/></packageSources></configuration>\n')
    (destination / "passwd").write_text(f"fixture:x:{os.getuid()}:{os.getgid()}:SDK fixture:/tmp/sdk-home:/bin/false\n")
    (destination / "group").write_text(f"fixture:x:{os.getgid()}:\n")
    command = ["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--clearenv", "--ro-bind", "/usr", "/usr",
               "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--ro-bind", str(sdk), "/runtime",
               "--ro-bind", str(packages), "/packages", "--bind", str(destination), "/out",
               "--ro-bind", str(destination / "passwd"), "/etc/passwd", "--ro-bind", str(destination / "group"), "/etc/group"]
    for name in ("bin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            command += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            command += ["--ro-bind", str(path), str(path)]
    for path in ("/etc/ld.so.cache", "/etc/alternatives"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    project = root / "src/ImmichFolderWatch.Core"
    for source in (project, here / "dotnet", root / "Directory.Build.props", root / "Directory.Build.targets", root / "global.json"):
        command += ["--ro-bind", str(source), f"/repo/{source.relative_to(root)}"]
    command += ["--tmpfs", "/repo/src/ImmichFolderWatch.Core/obj", "--tmpfs", "/repo/src/ImmichFolderWatch.Core/bin",
                "--dir", "/tmp/sdk-home", "--setenv", "PATH", "/runtime:/usr/bin", "--setenv", "HOME", "/tmp/sdk-home",
                "--setenv", "DOTNET_CLI_HOME", "/tmp/sdk-home", "--setenv", "DOTNET_ROOT", "/runtime",
                "--setenv", "NUGET_PACKAGES", "/tmp/sdk-home/packages", "--setenv", "DOTNET_NOLOGO", "1",
                "--setenv", "MSBuildEnableWorkloadResolver", "false", "--setenv", "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE", "true",
                "--setenv", "DOTNET_CLI_TELEMETRY_OPTOUT", "1", "--chdir", "/repo", "--", "/runtime/dotnet",
                "build", "tools/rust-qa/linux-services/dotnet/PortalReference.csproj", "--artifacts-path", "/out",
                "--configuration", "Release", "--source", "/packages", "-p:NuGetAudit=false",
                "-p:RestoreConfigFile=/out/NuGet.Config",
                "-p:EnableWindowsTargeting=false", "-p:UseSharedCompilation=false", "-p:RestoreDisableParallel=true",
                "-m:1", "--disable-build-servers"]
    subprocess.run(command, check=True, timeout=100)
    actual = destination / "bin/PortalReference/release"
    manifest = json.loads((destination / "obj/ImmichFolderWatch.Core/project.assets.json").read_text())
    core_sources = [p for p in sorted(project.rglob("*.cs")) if not {"obj", "bin"}.intersection(p.relative_to(project).parts)]
    sources = [*(here / "dotnet").glob("*"), project / "ImmichFolderWatch.Core.csproj", *core_sources,
               root / "Directory.Build.props", root / "Directory.Build.targets", root / "global.json"]
    record = {"sdk": pin, "project_reference": "src/ImmichFolderWatch.Core/ImmichFolderWatch.Core.csproj",
              "restored_packages_sha512": {name: item["sha512"] for name, item in manifest["libraries"].items() if item["type"] == "package"},
              "source": {str(p.relative_to(root)): sha(p) for p in sources},
              "output": {n: sha(actual / n) for n in ("PortalReference.dll", "ImmichFolderWatch.Core.dll")}}
    (destination / "inputs.json").write_text(json.dumps(record, indent=2) + "\n")
