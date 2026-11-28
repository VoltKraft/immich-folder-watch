"""Compare the Rust output with the shipping .NET 3.0.4 file provider and console formatter."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess


FILE_PROVIDER_SHA = "383b7e9cb608de608f6dca6c2d1cbf3a698363aafd30fb6396fe65df1954688a"
TIMESTAMP = re.compile(rb"(?m)^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} [+-]\d\d:\d\d (?=\[)")


def compare(root, here, profile, binary, nonce):
    project = profile / "reference-build"
    project.mkdir()
    for name in ("LogReference.cs", "LogReference.csproj"):
        shutil.copyfile(here / name, project / name)
    shipping = root / "src/ImmichFolderWatch.Core/Logging/FileLoggerProvider.cs"
    source = shipping.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(source).hexdigest() != FILE_PROVIDER_SHA:
        raise ValueError("The file logger source differs from the shipping 3.0.4 reference")
    (project / "FileLoggerProvider.cs").write_bytes(source)
    shutil.copyfile(root / "global.json", project / "global.json")
    home = profile / "reference-home"
    home.mkdir()
    empty = project / "empty-feed"
    empty.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), DOTNET_CLI_HOME=str(home),
               APPDATA=str(home), LOCALAPPDATA=str(home), NUGET_PACKAGES=str(home / "nuget"),
               DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
               DOTNET_GENERATE_ASPNET_CERTIFICATE="false", DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE="1")
    sdk = subprocess.check_output(["dotnet", "--version"], cwd=project, env=env, text=True, timeout=15).strip()
    if sdk != "10.0.401":
        raise ValueError("The reference requires the pinned SDK")
    subprocess.run(["dotnet", "restore", "--source", str(empty), "-p:NuGetAudit=false"],
                   env=env, cwd=project, check=True, timeout=75)
    subprocess.run(["dotnet", "build", "--configuration", "Release", "--no-restore", "--disable-build-servers",
                    "-p:UseSharedCompilation=false"], cwd=project, env=env, check=True, timeout=90)
    console = subprocess.check_output(["dotnet", project / "bin/Release/net10.0/LogReference.dll", nonce],
                                      cwd=profile, env=env, timeout=20)
    files = list((profile / "reference-files").glob("immich-folder-watch-*.log"))
    if len(files) != 1:
        raise RuntimeError("The reference did not produce its dated file")
    reference_file = files[0].read_bytes()
    actual_file = (profile / "synthetic.log").read_bytes().removeprefix(b"previous session\n")
    shipping_records, count = TIMESTAMP.subn(b"", reference_file)
    candidate_records, doubled = TIMESTAMP.subn(b"", actual_file)
    if count != 6 or doubled != 12 or candidate_records != shipping_records * 2:
        raise RuntimeError("The Rust file records differ from shipping output after replacing local timestamps")
    result = {"sdk": sdk, "shippingFileProviderSha256": FILE_PROVIDER_SHA, "matchingFileRecords": count,
              "referenceFileSha256": hashlib.sha256(reference_file).hexdigest()}
    if os.name != "nt":
        native = subprocess.check_output([binary, "journal", nonce], cwd=profile, timeout=10)
        if native != console:
            raise RuntimeError("The Rust journal stream differs from the shipping .NET formatter")
        result.update(matchingJournalRecords=len(console.splitlines()), nativeAndReferenceStreamSha256=hashlib.sha256(native).hexdigest())
    return result
