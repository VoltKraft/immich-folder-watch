"""Acquire audited private inputs, then build/run only filtered offline YAML sources.

Upload only --output, never the sibling private-cache/private-work directories.
The output contains a filtered source bundle; it never contains original .crate
archives, including the base64 archive that carries the excluded promotional logo.
"""

from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback
import uuid

from prepare import ROOT, HERE, bundle, file_digest, graph, prepare, write_json


SCOPE = ROOT / "artifacts/rust/yaml-assessment"


def isolated(path: Path, scope: Path = SCOPE) -> Path:
    path = path.resolve()
    if not path.is_relative_to(scope.resolve()) or path == scope.resolve():
        raise ValueError("path must be strictly below the synthetic assessment scope")
    return path


def record_sources(output: Path, fixtures: Path) -> None:
    paths = [ROOT / name for name in ["global.json", "Directory.Build.props", "NuGet.Config",
                                      "rust/toolchain-inputs.json", "tools/rust-qa/check-toolchain.py"]]
    for root in (HERE, ROOT / "src/ImmichFolderWatch.Core", fixtures):
        paths += [path for path in root.rglob("*") if path.is_file()
                  and not {"bin", "obj", "target", "__pycache__"}.intersection(path.relative_to(root).parts)]
    hashes = {}
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        destination = output / "first-party-sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        hashes[relative.as_posix()] = file_digest(path)
    write_json(output / "first-party-source-hashes.json", hashes)


def verify_encodings(profile: Path, cases: dict) -> None:
    encodings = {
        "utf8": ("utf-8", b"", 65001), "utf8-bom": ("utf-8", codecs.BOM_UTF8, 65001),
        "utf16le": ("utf-16-le", codecs.BOM_UTF16_LE, 1200), "utf16be": ("utf-16-be", codecs.BOM_UTF16_BE, 1201),
        "utf32le": ("utf-32-le", codecs.BOM_UTF32_LE, 12000), "utf32be": ("utf-32-be", codecs.BOM_UTF32_BE, 12001),
    }
    for label, (codec, bom, page) in encodings.items():
        name = "encoding-" + label
        case = cases[name]
        if (case["sourceCodePage"] != page or case["sourceHadDecodingErrors"] or not case["accepted"]
                or "\uFFFD" not in case["yaml"] or (profile / (name + ".yaml")).read_bytes() != bom + case["yaml"].encode(codec)):
            raise ValueError(f"Unexpected original bytes or decoder for {name}")

    # .NET replaces a trailing UTF-16 high surrogate and an odd byte separately.
    damaged = {
        "utf8-short": ("utf8", "e282", 1), "utf8-continuation": ("utf8-bom", "80", 1),
        "utf16le-high": ("utf16le", "00d8", 1), "utf16be-low": ("utf16be", "dc00", 1),
        "utf16le-odd": ("utf16le", "61", 1), "utf16be-high-odd": ("utf16be", "d80061", 2),
        "utf32le-invalid": ("utf32le", "00001100", 1), "utf32be-surrogate": ("utf32be", "0000d800", 1),
        "utf32le-short": ("utf32le", "610000", 1), "utf32be-short": ("utf32be", "0000", 1),
    }
    if {name for name, case in cases.items() if case["sourceHadDecodingErrors"]} != {"encoding-" + label for label in damaged}:
        raise ValueError("Incomplete malformed byte controls")
    for label, (encoding, suffix, replacements) in damaged.items():
        name = "encoding-" + label
        case = cases[name]
        codec, bom, page = encodings[encoding]
        prefix = case["yaml"][:-replacements]
        if (case["sourceCodePage"] != page or not case["accepted"] or not case["yaml"].endswith("Archive" + "\uFFFD" * replacements)
                or (profile / (name + ".yaml")).read_bytes() != bom + prefix.encode(codec) + bytes.fromhex(suffix)):
            raise ValueError(f"Unexpected original bytes or fallback for {name}")


def verify_file_inputs(reference: Path, rust_output: Path, exported: dict, rust: dict, csharp: dict) -> None:
    if (exported["format"] != "ifw-rw02-yaml-reference-v2" or rust["format"] != "ifw-rw02-yaml-result-v2"
            or csharp["format"] != "ifw-rw02-yaml-readback-v2"):
        raise ValueError("Expected the raw-file YAML comparison")
    inputs = {row["name"]: row for row in exported["cases"]}
    results = {row["name"]: row for row in rust["cases"]}
    if (len(inputs) != len(exported["cases"]) or len(results) != len(rust["cases"]) or inputs.keys() != results.keys()
            or csharp["preservedInputs"] != len(inputs) or rust["byteAssertions"] != 3 * len(inputs)):
        raise ValueError("Incomplete YAML input evidence")
    profile = reference / "profile"
    if {path.name for path in profile.iterdir()} != {name + ".yaml" for name in inputs}:
        raise ValueError("Original profile files differ from the exported cases")
    verify_encodings(profile, inputs)
    marked = inputs["saved-album-format-mark"]
    album = "\ufeffFoto"
    if (marked["editable"]["watch"]["sources"][0]["albumName"] != album
            or marked["runtime"]["watch"]["sources"][0]["albumName"] != album
            or f"albumName: {album}" not in [line.strip() for line in marked["written"].splitlines()]
            or (profile / "saved-album-format-mark.yaml").read_bytes() != codecs.BOM_UTF8 + marked["written"].encode("utf-8")):
        raise ValueError("The saved plain album or its file preamble differs")
    for name in ("anchor-skipped-only", "anchor-on-key", "alias-as-key", "unknown-alias"):
        if inputs[name]["accepted"]:
            raise ValueError("The shipping loader accepted a missing typed anchor or an alias key")
    for name, path, album, filters in (
        ("anchor-shadow", "Pictures", "Pictures", []),
        ("alias-in-skipped-map", "Pictures", "Pictures", []),
        ("anchor-known-reassigned", "Neu", "Pictures", ["Neu"]),
        ("anchor-separator-shadow", "Pictures", "Foto\u2028Nord", ["Foto\u2028Nord"]),
    ):
        source = inputs[name]["editable"]["watch"]["sources"][0]
        if (source["path"], source["albumName"], source["excludeDirectories"]) != (path, album, filters):
            raise ValueError("The shipping loader selected an unexpected anchor definition")
    if inputs["format-mark-in-key"]["editable"]["retry"]["maxAttempts"] != 7:
        raise ValueError("A key prefixed with U+FEFF replaced the ordinary key")
    for stem, separator in (("line", "\u2028"), ("paragraph", "\u2029")):
        name = f"saved-{stem}-separator"
        case = inputs[name]
        source = case["editable"]["watch"]["sources"][0]
        if (source["albumName"] != "Foto" + separator + "Nord"
                or source["path"] != "Pictures" + separator + "Nord"
                or source["excludeFileNames"] != ["Cover" + separator + "Nord.jpg"]
                or case["yaml"] != case["written"]
                or (profile / (name + ".yaml")).read_bytes() != case["written"].encode("utf-8")):
            raise ValueError(f"Shipping scalar save differs for {name}")
    if (inputs["separator-underindent"]["accepted"]
            or inputs["separator-folding"]["editable"]["watch"]["sources"][0]["albumName"] != "A\n\u2028B"
            or inputs["separator-escaped"]["editable"]["watch"]["sources"][0]["albumName"] != "Foto\u2028      Nord"
            or [s["albumName"] for s in inputs["separator-alias"]["editable"]["watch"]["sources"]] != ["Foto\u2028  Nord"] * 2):
        raise ValueError("The shipping block, escape or alias controls differ")
    for name, count, codec, bom in (
        ("folders-100-utf8", 100, "utf-8", b""),
        ("folders-300-utf8", 300, "utf-8", b""),
        ("folders-300-utf32", 300, "utf-32-le", codecs.BOM_UTF32_LE),
    ):
        case = inputs[name]
        paths = [source["path"] for source in case["editable"]["watch"]["sources"]]
        if (paths != [f"Albums/Archive-{i:03}" for i in range(1, count + 1)]
                or case["sourceHadDecodingErrors"] or not case["accepted"]
                or case["yaml"] != case["written"]
                or (profile / (name + ".yaml")).read_bytes() != bom + case["written"].encode(codec)):
            raise ValueError(f"Native saved folder list or source order differs: {name}")
    writable = {name for name, row in inputs.items() if row["accepted"] and not row["sourceHadDecodingErrors"]}
    expected_files = {name + suffix for name in writable for suffix in (".roundtrip.yaml", ".changed.yaml")}
    if {path.name for path in rust_output.iterdir()} != expected_files | {"result.json", "csharp-readback.json"}:
        raise ValueError("Unexpected or missing Rust output files")
    accepted = sum(row["accepted"] for row in inputs.values())
    if (rust["assertions"] != len(inputs) + 3 * accepted + 2 * len(writable) or csharp["assertions"] != 4 * len(writable)
            or csharp["readOnlyInputs"] != sum(row["sourceHadDecodingErrors"] for row in inputs.values())):
        raise ValueError("Incomplete Rust or C# YAML comparisons")
    for name, case in inputs.items():
        if not name or not all(char.isascii() and (char.isalnum() or char in ".-") for char in name):
            raise ValueError("Invalid raw YAML case name")
        path = profile / (name + ".yaml")
        row = results[name]
        if (file_digest(path) != case["sourceSha256"] or row["sourceBytes"] != path.stat().st_size
                or row["sourceCodePage"] != case["sourceCodePage"] or row["sourceHadDecodingErrors"] != case["sourceHadDecodingErrors"]
                or row["readOnlyOnDecodeError"] != case["sourceHadDecodingErrors"] or row["accepted"] != case["accepted"]
                or any((row.get(key) is True) != case["accepted"] for key in ("editingMatched", "runtimeMatched", "csharpWriterMatched"))):
            raise ValueError(f"Raw YAML file and reader observations differ: {name}")


def main() -> int:
    inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(inputs["target_graphs"]))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cargo-home", type=Path, default=SCOPE / "private-cache")
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    output = isolated(args.output or SCOPE / "runs" / f"{args.target}-{identity}")
    acquisition = isolated(args.cargo_home, ROOT / "artifacts/rust")
    if output.is_relative_to(acquisition) or acquisition.is_relative_to(output):
        raise ValueError("private acquisition cache and uploadable evidence must be separate")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = SCOPE / "private-work" / identity
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    dotnet = str(Path(args.dotnet).resolve()) if Path(args.dotnet).is_file() else args.dotnet
    native = "windows" if sys.platform == "win32" else "linux"
    fixtures = ROOT / "rust/tests/fixtures/legacy" / native
    env = os.environ.copy()
    removed = []
    for key in list(env):
        if key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"} or key.endswith("_RUSTFLAGS"):
            removed.append(key)
            del env[key]
    env.update({"CARGO_HOME": str(acquisition), "CARGO_TARGET_DIR": str(work / "target"),
                "IFW_ORACLE_EXPECT_ARCH": "arm64" if args.target.startswith("aarch64-") else "x64",
                "DOTNET_CLI_HOME": str(work / "dotnet-cli"), "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false"})
    result = {"format": "ifw-rw02-yaml-native-v1", "status": "running", "target": args.target,
              "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "modifiedSources": subprocess.check_output(["git", "status", "--porcelain", "--", str(HERE),
                  "src/ImmichFolderWatch.Core", "global.json", "Directory.Build.props", "NuGet.Config", "rust/tests/fixtures/legacy"], cwd=ROOT, text=True).splitlines(),
              "workflowRun": os.getenv("GITHUB_RUN_ID"), "operatingSystem": platform.platform(), "offlineAcquisition": args.offline,
              "removedBuildOverrideNames": sorted(removed), "steps": {}}

    def command(name: str, arguments: list[str]) -> None:
        print(f"YAML assessment: {name}", flush=True)
        log = output / f"{name}.log"
        with log.open("wb") as stream:
            try:
                code = subprocess.run(arguments, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1200).returncode
            except subprocess.TimeoutExpired:
                code = 124
                stream.write(b"Timed out after 1200 seconds.\n")
        result["steps"][name] = {"exitCode": code, "command": arguments, "log": log.name}
        write_json(output / "result.json", result)
        print(log.read_text(encoding="utf-8", errors="replace")[-4500:], end="", flush=True)
        if code:
            raise RuntimeError(f"{name} failed with exit code {code}")

    try:
        command("native-compiler", [sys.executable, str(ROOT / "tools/rust-qa/check-toolchain.py"), args.target])
        command("filter-tests", [sys.executable, str(HERE / "test_prepare.py")])
        if file_digest(HERE / "Cargo.lock") != inputs["lock_sha256"]:
            raise ValueError("generated YAML lockfile differs from reviewed inputs")
        manifest = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
        if manifest["SyntheticOnly"] is not True or manifest["Platform"] != native:
            raise ValueError("not the reviewed native synthetic corpus")
        for name, expected in manifest["Fixtures"].items():
            path = (fixtures / name).resolve()
            if not path.is_relative_to(fixtures.resolve()) or file_digest(path) != expected:
                raise ValueError("reviewed fixture checksum or path mismatch")
        record_sources(output, fixtures)
        cargo_manifest = ["--manifest-path", str(HERE / "Cargo.toml")]
        redirect = "import subprocess,sys; p=subprocess.run(sys.argv[2:],stdout=subprocess.PIPE); open(sys.argv[1],'wb').write(p.stdout); sys.exit(p.returncode)"
        acquisition_arguments = ["cargo", "metadata", *cargo_manifest, "--locked", "--format-version", "1"]
        if args.offline: acquisition_arguments.append("--offline")
        command("private-acquisition", [sys.executable, "-c", redirect, str(work / "private-metadata.json"), *acquisition_arguments])
        vendor = work / "vendor"
        filtered = prepare(acquisition, vendor, inputs)
        write_json(output / "source-filter.json", filtered)
        bundle(vendor, filtered, output / "filtered-sources.tar")
        if file_digest(output / "filtered-sources.tar") != inputs["filtered_bundle_sha256"]:
            raise ValueError("filtered source bundle is not byte reproducible")
        result["filteredBundleSha256"] = inputs["filtered_bundle_sha256"]
        result["originalArchiveCount"] = len(filtered["packages"])
        result["filteredSourceFiles"] = sum(len(package["files"]) for package in filtered["packages"])
        result["noticeFiles"] = sum(len(package["notices"]) for package in inputs["packages"])
        # This new empty Cargo home has neither original archives nor registry
        # sources. Every subsequent Cargo operation is frozen and directory-only.
        env["CARGO_HOME"] = str(work / "empty-offline-cargo")
        config = ["--config", 'source.crates-io.replace-with="ifw-reviewed"', "--config",
                  "source.ifw-reviewed.directory=" + json.dumps(str(vendor), ensure_ascii=False)]
        metadata_path = output / "offline-native-metadata.json"
        command("offline-native-graph", [sys.executable, "-c", redirect, str(metadata_path), "cargo", "metadata",
                *cargo_manifest, *config, "--frozen", "--format-version", "1", "--filter-platform", args.target])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if graph(metadata) != inputs["target_graphs"][args.target]:
            raise ValueError("native YAML graph differs from reviewed inputs")
        for package in metadata["packages"]:
            if package["source"] and not Path(package["manifest_path"]).resolve().is_relative_to(vendor.resolve()):
                raise ValueError("offline build resolved an unfiltered source")
        result["nativeGraphPackages"] = len(graph(metadata))
        command("format", ["cargo", "fmt", *cargo_manifest, "--", "--check"])
        common = [*cargo_manifest, *config, "--frozen", "--target", args.target]
        command("clippy", ["cargo", "clippy", *common, "--all-targets", "--", "-D", "warnings"])
        command("tests", ["cargo", "test", *common, "--", "--show-output"])
        command("release", ["cargo", "build", *common, "--release"])
        binary = work / "target" / args.target / "release" / ("ifw-yaml-assessment.exe" if os.name == "nt" else "ifw-yaml-assessment")
        result["rustExecutableSha256"] = file_digest(binary)
        project = HERE / "dotnet/YamlOracle.csproj"
        dotnet_common = [str(project), "--artifacts-path", str(work / "dotnet"), "-p:EnableWindowsTargeting=false"]
        restore = [dotnet, "restore", *dotnet_common]
        if args.offline: restore += ["--ignore-failed-sources", "-p:NuGetAudit=false"]
        command("csharp-restore", restore)
        command("csharp-build", [dotnet, "build", *dotnet_common, "--no-restore", "--configuration", "Release"])
        assembly = work / "dotnet/bin/YamlOracle/release/YamlOracle.dll"
        result["csharpAssemblySha256"] = file_digest(assembly)
        reference = output / "reference"
        original = work / "reference"
        command("csharp-reference", [dotnet, str(assembly), "export", str(fixtures), str(original)])
        # Replay the archived files after the producer's absolute directory has ceased to exist.
        shutil.move(original, reference)
        exported = json.loads((reference / "reference.json").read_text(encoding="utf-8"))
        if file_digest(reference / "casing.json") != exported["casingSha256"]:
            raise ValueError("native string reference checksum mismatch")
        command("rust-roundtrip", [str(binary), str(reference), str(output / "rust-output")])
        command("csharp-readback", [dotnet, str(assembly), "verify", str(reference), str(output / "rust-output")])
        result["rust"] = json.loads((output / "rust-output/result.json").read_text(encoding="utf-8"))
        result["csharp"] = json.loads((output / "rust-output/csharp-readback.json").read_text(encoding="utf-8"))
        verify_file_inputs(reference, output / "rust-output", exported, result["rust"], result["csharp"])
        if (result["rust"]["platform"] != native or result["rust"]["architecture"] != args.target.split("-")[0]
                or exported["corpusAssertions"] != 10):
            raise ValueError("incomplete native YAML results")
        result["status"] = "passed"
        print(f"YAML assessment passed; upload only: {output}", flush=True)
    except Exception as error:
        result["status"] = "failed"
        result["error"] = str(error)
        traceback.print_exc()
    finally:
        write_json(output / "result.json", result)
        write_json(output / "evidence-hashes.json", {path.relative_to(output).as_posix(): file_digest(path)
            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "evidence-hashes.json"})
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
