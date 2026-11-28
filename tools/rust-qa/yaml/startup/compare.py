"""Compare startup language with the signed 3.0.4 Linux assemblies using fresh synthetic XDG profiles."""
import argparse
import codecs
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REVISION = "abeebe13b83cc4b8246fb4a8715daddce7f3dd4bf52861ae4ca33b06755104da"
ASSEMBLIES = {
    "ImmichFolderWatch.App.Shared.dll": "4787464c2b9619b7b09b1d61740c76b9862edfb1153a64e85c8779eab303ada8",
    "ImmichFolderWatch.Core.dll": "22fd3d96b18f11a6bd018a3d378cbf7903140e1aed5bee2eb5a39c9a730a8e03",
    "YamlDotNet.dll": "d618138109a40e4a7250e49e2abad8c450e3636bee18d7499ab231e37fa9150a",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def oracle(sdk, repository, work, env):
    package = work / "signed-package"
    subprocess.run(["ostree", "--repo=" + str(repository), "checkout", "--user-mode", "--force-copy",
                    "--subpath=/files/lib/immich-folder-watch", REVISION, package], check=True)
    for name, expected in ASSEMBLIES.items():
        if sha(package / name) != expected:
            raise ValueError(f"Unexpected signed reference assembly {name}")
    harness = package / "StartupLanguage.dll"
    compiler = sdk / "sdk/10.0.401/Roslyn/bincore/csc.dll"
    references = sorted(sdk.glob("packs/Microsoft.NETCore.App.Ref/10.0.12/ref/net10.0/*.dll"))
    subprocess.run([sdk / "dotnet", compiler, "-nologo", "-nostdlib", "-target:exe", "-out:" + str(harness),
                    *["-reference:" + str(p) for p in [*references, *(package / n for n in ASSEMBLIES)]],
                    HERE / "Reference.cs"], check=True, cwd=work, env=env)
    return [sdk / "dotnet", "exec", "--runtimeconfig", package / "immich-folder-watch.runtimeconfig.json",
            "--depsfile", package / "immich-folder-watch.deps.json", harness]


def read(command, home, env):
    return json.loads(subprocess.check_output(command, cwd=home, env=env, timeout=10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--signed-repo", type=Path, required=True)
    parser.add_argument("--rust", type=Path, required=True, help="frozen linux_startup_language example")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    if not work.is_relative_to(ROOT / "artifacts/rust"):
        parser.error("Use a new directory under artifacts/rust")
    work.mkdir(parents=True, exist_ok=False)
    env = {"HOME": str(work), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "DOTNET_NOLOGO": "1",
           "DOTNET_CLI_HOME": str(work), "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_EnableDiagnostics": "0"}
    csharp = oracle(args.sdk.resolve(strict=True), args.signed_repo.resolve(strict=True), work, env)
    rust = [args.rust.resolve(strict=True)]
    de, en = "de_CH.UTF-8", "en_US.UTF-8"
    cases = [
        ("missing-german", {"LANG": de}, None, "de"),
        ("missing-english", {"LANG": en}, None, "en"),
        ("missing-other", {"LANG": "fr_FR.UTF-8"}, None, "en"),
        ("messages-beats-lang", {"LC_MESSAGES": de, "LANG": en}, None, "de"),
        ("all-beats-messages", {"LC_ALL": en, "LC_MESSAGES": de}, None, "en"),
        ("ignore-gettext-list", {"LANGUAGE": "de:fr", "LANG": en}, None, "en"),
        ("empty-lc-all", {"LC_ALL": "", "LC_MESSAGES": de}, None, "en"),
        ("empty-lc-messages", {"LC_MESSAGES": "", "LANG": de}, None, "en"),
        ("invariant", {"LANG": "C.UTF-8"}, None, "en"),
        ("iso-three", {"LANG": "deu_DE"}, None, "de"),
        ("english-over-german", {"LANG": de}, b"localization: {language: ' En '}\n", "en"),
        ("german-over-english", {"LANG": en}, b"localization: {language: DE}\n", "de"),
        ("fallback-home", {"LANG": en}, b"localization: {language: de}\n", "de"),
        ("auto", {"LANG": de}, b"localization: {language: AUTO}\n", "de"),
        ("blank", {"LANG": de}, b"localization: {language: ' '}\n", "de"),
        ("unknown-code", {"LANG": en}, b"localization: {language: de-DE}\n", "en"),
        ("missing-key", {"LANG": de}, b"localization: {}\n", "de"),
        ("utf32be", {"LANG": de}, codecs.BOM_UTF32_BE + "localization: {language: en}\n".encode("utf-32-be"), "en"),
        ("duplicate", {"LANG": de}, b"localization: {language: de}\nlocalization: {language: en}\n", "en"),
        ("recognized-alias", {"LANG": en}, b"logging: {target: &lang de}\nlocalization: {language: *lang}\n", "de"),
        ("malformed", {"LANG": de}, b"localization: [\n", "de"),
        ("typed-document-error", {"LANG": en}, b"localization: {language: de}\nretry: {maxAttempts: invalid}\n", "en"),
    ]
    records = []
    for name, variables, contents, expected in cases:
        home = work / name
        home.mkdir()
        profile = home / (".config" if name == "fallback-home" else "config")
        path = profile / "immich-folder-watch/config.yaml"
        if contents is not None:
            path.parent.mkdir(parents=True)
            path.write_bytes(contents)
        process_env = {**env, **variables, "HOME": str(home)}
        if name != "fallback-home":
            process_env["XDG_CONFIG_HOME"] = str(profile)
        first, second = read(csharp, home, process_env), read(rust, home, process_env)
        if second != {k: first[k] for k in ("path", "language", "systemLanguage", "setting", "read")} or first["language"] != expected:
            raise ValueError(f"Startup selection differs for {name}: {first}, {second}")
        if str(path) != first["path"] or (path.read_bytes() if path.exists() else None) != contents:
            raise ValueError(f"Incorrect path or modified configuration for {name}")
        if contents is None and profile.exists():
            raise ValueError(f"Reading a missing preference created directories for {name}")
        records.append({"case": name, "locale": variables, "signed": first, "rust": second})
    # Opening a FIFO with the signed reference could block. Only compare regular files above.
    special = work / "special"
    path = special / "immich-folder-watch/config.yaml"
    path.parent.mkdir(parents=True)
    os.mkfifo(path, mode=0o600)
    special_env = {**env, "HOME": str(work), "XDG_CONFIG_HOME": str(special), "LANG": de}
    fifo = read(rust, work, special_env)
    if fifo["read"] != "failed" or fifo["language"] != "de" or not path.is_fifo():
        raise ValueError("A non-regular preference must fall back without waiting for a writer")
    path.unlink()
    report = {"signedCommit": REVISION, "signedAssemblies": ASSEMBLIES, "binarySha256": sha(rust[0]),
              "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in [HERE / "Reference.cs", Path(__file__),
                          HERE.parent / "examples/linux_startup_language.rs", *sorted((HERE.parent / "src").glob("*.rs"))]},
              "cases": records, "fifo": fifo}
    (work / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)} signed startup comparisons and the FIFO fallback passed")


if __name__ == "__main__":
    main()
