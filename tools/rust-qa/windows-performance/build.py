"""Build the pinned shipping WPF entry point and the PID-filtered Windows SDK observer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REFERENCE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
REFERENCE_SOURCE_SHA256 = "74f1702ebd09511da3b8853342a776a12f4c7f8b458a1dd2d0e066add75fce3d"
INPUTS = ["Directory.Build.props", "Directory.Build.targets", "global.json", "NuGet.Config", "assets/branding",
          "packaging/windows/build-msi.ps1", "tools/BrandAssetGen", "src/ImmichFolderWatch.App", "src/ImmichFolderWatch.Core",
          "src/ImmichFolderWatch.Immich", "src/ImmichFolderWatch.App.Shared"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def pe_machine(path):
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError(f"Invalid native image {path.name}")
        source.seek(60)
        source.seek(struct.unpack("<I", source.read(4))[0])
        if source.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature {path.name}")
        return struct.unpack("<H", source.read(2))[0]


def verify_reference(project):
    digest = hashlib.sha256()
    for path in sorted(project.rglob("*"), key=lambda p: p.relative_to(project).as_posix()):
        if path.is_symlink():
            raise ValueError("Linked input in the shipping WPF source tree")
        if path.is_file():
            digest.update(path.relative_to(project).as_posix().encode("utf-8") + b"\0" + bytes.fromhex(sha(path)))
    if digest.hexdigest() != REFERENCE_SOURCE_SHA256:
        raise ValueError("The extracted shipping WPF source tree has changed")


def extract_reference(project):
    sys.path.insert(0, str(HERE.parent))
    from storage.evidence import relative_member
    project.mkdir()
    archive = project.parent / "reference.tar"
    with archive.open("xb") as stream:
        subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive", "--format=tar",
                        REFERENCE, "--", *INPUTS], cwd=ROOT, stdout=stream, check=True)
    with tarfile.open(archive) as sources:
        for entry in sources:
            path = project.joinpath(*relative_member(entry.name).parts)
            if entry.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                with sources.extractfile(entry) as data, path.open("xb") as dest:
                    shutil.copyfileobj(data, dest)
            else:
                raise ValueError(f"Unexpected shipping source member {entry.name}")
    verify_reference(project)
    return sha(archive)


def build(area, output, target):
    arch = {"aarch64-pc-windows-msvc": "arm64", "x86_64-pc-windows-msvc": "x64"}[target]
    machine = 0xaa64 if arch == "arm64" else 0x8664
    rust = ROOT / "artifacts/rust/gui-build/release/native-gui-assessment.exe"
    receipt = ROOT / f"artifacts/rust/gui-native/{target}/build.json"
    gui = json.loads(receipt.read_text(encoding="utf-8"))
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (gui["source"] != source or gui["target"] != target or gui["binarySha256"] != sha(rust)
            or pe_machine(rust) != machine):
        raise ValueError("Expected the reviewed native GUI build for this process architecture")
    profile = json.loads((ROOT / "rust/audit/gui-profile.json").read_text(encoding="utf-8"))
    if (gui["graphSha256"] != profile["targetReportSha256"][target] or gui["lockSha256"] != profile["lockSha256"]
            or any(sha(ROOT / path) != digest for path, digest in gui["compilerSources"].items())):
        raise ValueError("The native GUI performance subject differs from its reviewed checkout")
    env = dict(os.environ, DOTNET_CLI_HOME=str(area / "dotnet-home"), DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_NOLOGO="1", DOTNET_GENERATE_ASPNET_CERTIFICATE="false", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
    project = area / "source"
    archive_digest = extract_reference(project)
    sdk = subprocess.check_output(["dotnet", "--version"], cwd=project, env=env, text=True).strip()
    if sdk != json.loads((project / "global.json").read_text())["sdk"]["version"]:
        raise ValueError("The .NET SDK differs from the shipping global.json")
    app = project / "src/ImmichFolderWatch.App/ImmichFolderWatch.App.csproj"
    reference = area / "reference"
    with (output / "wpf-build.log").open("wb") as log:
        subprocess.run(["dotnet", "publish", str(app), "-c", "Release", "-r", "win-" + arch,
                        "--self-contained", "true", "-o", str(reference), "-p:SourceRevisionId=" + REFERENCE],
                       cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1000, check=True)
    wpf = reference / "ImmichFolderWatch.exe"
    native = area / "present.exe"
    with (output / "observer-build.log").open("wb") as log:
        compile_result = subprocess.run(["cl.exe", "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/utf-8",
                                         "/DUNICODE", "/D_UNICODE", str(HERE / "present.cpp"), "/link", "advapi32.lib", "tdh.lib"],
                                        cwd=area, stdout=log, stderr=subprocess.STDOUT)
    if compile_result.returncode:
        native = None
    if pe_machine(wpf) != machine or (native is not None and pe_machine(native) != machine):
        raise ValueError("The shipping host or measurement helper has the wrong PE machine")
    nuget = {}
    for graph in sorted(project.glob("**/obj/project.assets.json")):
        libraries = json.loads(graph.read_text(encoding="utf-8-sig"))["libraries"]
        nuget[graph.relative_to(project).as_posix()] = {
            name: package["sha512"] for name, package in libraries.items() if package["type"] == "package"
        }
    if "src/ImmichFolderWatch.App/obj/project.assets.json" not in nuget:
        raise ValueError("Missing resolved WPF package inventory")
    facts = dict(target=target, candidateRevision=source, dotnetSdk=sdk, referenceRevision=REFERENCE,
                 referenceSourceSha256=REFERENCE_SOURCE_SHA256, referenceArchiveSha256=archive_digest,
                 referenceNuGetPackages=nuget,
                 wpfOutput={p.relative_to(reference).as_posix(): sha(p) for p in sorted(reference.rglob("*")) if p.is_file()},
                 guiReceiptSha256=sha(receipt), guiBinarySha256=sha(rust), observerSha256=sha(native) if native else None,
                 drivers={p.name: sha(p) for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".cpp", ".h")},
                 sharedDrivers={name: sha(HERE.parent / name) for name in
                                ("observe-windows-gui.py", "windows_observer.py", "storage/evidence.py")})
    return wpf, rust, native, facts
