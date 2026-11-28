"""Reconstruct the private Flatpak AT-SPI trial from the original source-bound editor."""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent
QA = HERE.parents[1]
ROOT = QA.parents[1]
AREA = ROOT / "artifacts/rust"
STOCK = AREA / "combined-profile/editor-language-replay-verified"
VENDOR = AREA / "combined-profile/editor-language-clean-vendor-01/registry/src/reviewed"
SCOPE = AREA / "flatpak-accessibility"
RECEIPT = "bfde3d81b0948a70d55221591ec3b57d3a7707a497d889d3758ccbdfbfd1fac0"
CRATE = "accesskit_unix-0.24.1"
CURRENT_RECEIPT = "b01ed1ba88ee393d4184426e1697b7cc5f8bf4c25914ed8b10f0cb55187b58b0"
ARCHIVE = "30d5192871228c54f1b0fb4a85cef000e11a3804f25d2165f14afa0daa67f3f6"
PATCH = HERE / "application-bus.patch"
PRIVATE = "artifacts/accesskit_unix"
TARGET = "x86_64-unknown-linux-gnu"
sys.path[:0] = [str(HERE), str(QA), str(QA / "combined-profile")]
import accesskit_source
from gui.compiler_inputs import linux_project_sources, verify_gui_units
from sources import locked, read, sha256, source_config, source_profile, write
from gui.startup import vendor as supply


def check_stock(stock):
    record = read(stock / "native.json")
    if (sha256(stock / "native.json") != RECEIPT or record["target"] != TARGET
            or sha256(stock / "compiler.jsonl") != record["unitsSha256"]
            or sha256(stock / "supply.json") != record["supplySha256"]
            or source_profile.historical_text_profile_sha256("c63d91c42eae9f71f07a2d1816214a1e16609ef8")
            != record["textAndFontProfileSha256"]):
        raise ValueError("The original language GUI inputs differ from the measured native compiler receipt")
    for name, digest in record["sources"].items():
        if sha256(stock / "project" / name) != digest:
            raise ValueError(f"Original source differs for {name}")
    return record


@dataclass(frozen=True)
class Original:
    root: Path
    units: Path
    sources: dict
    receipt_sha: str


def original(stock):
    if (stock / "native.json").is_file():
        data = check_stock(stock)
        return Original(stock / "project", stock / "compiler.jsonl", data["sources"], RECEIPT)
    binary = stock / "release/native-gui-assessment"
    receipt = binary.with_suffix(".inputs.json")
    if sha256(receipt) != CURRENT_RECEIPT:
        raise ValueError("Expected the reviewed ordinary Fedora x64 editor compiler receipt")
    data = read(receipt)
    stream, graph = stock / "gui-compiler.jsonl", stock / "gui-graph.json"
    source_hashes = {p.relative_to(ROOT).as_posix(): sha256(p) for p in linux_project_sources(ROOT)}
    fonts = ROOT / "rust/assets/fonts"
    if (data["target"] != TARGET or sha256(binary) != data["binary_sha256"]
            or sha256(stream) != data["compilerStreamSha256"] or sha256(graph) != data["graphSha256"]
            or sha256(stock / "gui-registry-sources.json") != supply.RECEIPT_SHA256
            or data["registryReceiptSha256"] != supply.RECEIPT_SHA256 or data["sources"] != source_hashes
            or {p.name: sha256(p) for p in fonts.glob("*.ttf")} != data["fonts"]
            or sha256(fonts / "OFL-1.1.txt") != data["font_notice"]):
        raise ValueError("The ordinary upstream editor, compiler inputs or feature report changed")
    features = {p["name"] + " v" + p["version"]: p["featureSets"] for p in read(graph)["packages"]}
    if verify_gui_units(stream, features) != data["compilerUnits"]:
        raise ValueError("The ordinary compiler has a different set of units")
    return Original(ROOT, stream, source_hashes, CURRENT_RECEIPT)


def stage(stock, directory, out):
    project = out / "project"
    for name, digest in stock.sources.items():
        dest = project / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stock.root / name, dest)
        if sha256(dest) != digest:
            raise ValueError(f"Original source differs for {name}")
    gui = project / "tools/rust-qa/gui"
    approved = source_profile.validate()
    for name, expected in approved["trees"].items():
        relative = Path("tools/rust-qa/gui/artifacts/text") / name
        original = stock.root / relative
        if source_profile.tree_info(original) != expected:
            raise ValueError(f"Original text source differs for {name}")
        shutil.copytree(original, project / relative)
    inventory = directory.parents[2] / "registry-sources.json"
    if sha256(inventory) != supply.RECEIPT_SHA256:
        raise ValueError("Expected the source-bound GUI and YAML directory registry")
    selected = locked(gui)
    catalog = read(inventory)
    if {name + "-" + version for name, version in selected} != set(catalog):
        raise ValueError("The composed GUI lock must select the complete reviewed registry")
    supply.verify_sources(directory, selected, catalog)
    archive = directory.parents[1] / "cache/reviewed" / (CRATE + ".crate")
    adapter = accesskit_source.reconstruct(archive, gui / PRIVATE, out / "notices")
    with (gui / "Cargo.toml").open("a", encoding="utf-8", newline="\n") as manifest:
        manifest.write(f'accesskit_unix = {{ path = "{PRIVATE}" }}\n')
    write(out / "adapter.json", {**adapter, "originalReceiptSha256": stock.receipt_sha,
                                 "vendorReceiptSha256": sha256(inventory)})
    return gui


def check_lock(original, candidate):
    before = tomllib.loads(original.read_text())
    selected, = [row for row in before["package"] if row["name"] == "accesskit_unix"]
    if (selected.pop("source") != "registry+https://github.com/rust-lang/crates.io-index"
            or selected.pop("checksum") != ARCHIVE or before != tomllib.loads(candidate.read_text())):
        raise ValueError("Only the source of the original adapter may change in the private GUI lock")


def units(path, candidate):
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    if rows[-1] != {"reason": "build-finished", "success": True}:
        raise ValueError("Expected a complete native compiler stream")
    result = Counter()
    private = "/project/tools/rust-qa/gui/" + PRIVATE
    stock = "/vendor/" + CRATE
    for item in rows:
        if item["reason"] != "compiler-artifact":
            continue
        target = item["target"]
        identity = item["package_id"]
        manifest = item["manifest_path"]
        source = target["src_path"]
        if target["name"] == "native-gui-assessment" and target["kind"] == ["bin"]:
            if item["executable"] != "/build/release/native-gui-assessment" or (candidate and item["fresh"]):
                raise ValueError("Expected the final native editor executable from the candidate relink")
        if target["name"] == "accesskit_unix" and candidate:
            if ((manifest, source, identity) != (private + "/Cargo.toml", private + "/src/lib.rs",
                                                 "path+file://" + private + "#0.24.1")
                    or item["fresh"]):
                raise ValueError("The candidate compiler did not rebuild the private adapter")
            identity = "registry+https://github.com/rust-lang/crates.io-index#accesskit_unix@0.24.1"
            manifest, source = stock + "/Cargo.toml", stock + "/src/lib.rs"
        result[identity, manifest, source, target["name"], tuple(target["kind"]), tuple(sorted(item["features"]))] += 1
    return result


def verify_candidate(binary, receipt, expected_sha):
    """Bind the observer's chosen native receipt, ELF, compiler inputs and modified source tree."""
    binary, receipt = binary.resolve(strict=True), receipt.resolve(strict=True)
    out = receipt.parent
    if (not out.is_relative_to(SCOPE) or receipt.name != "native.json"
            or binary != out / "target/release/native-gui-assessment" or sha256(receipt) != expected_sha):
        raise ValueError("Use the measured private Flatpak editor binary and compiler receipt")
    native = read(receipt)
    adapter = read(out / "adapter.json")
    gui = out / "project/tools/rust-qa/gui"
    pins = read(accesskit_source.REVIEW)
    if (native["target"] != TARGET or native["originalReceiptSha256"] not in (RECEIPT, CURRENT_RECEIPT)
            or adapter != {**pins, "originalReceiptSha256": native["originalReceiptSha256"],
                           "vendorReceiptSha256": supply.RECEIPT_SHA256}
            or sha256(binary) != native["binarySha256"] or sha256(out / "compiler.jsonl") != native["unitsSha256"]
            or sha256(out / "adapter.json") != native["adapterSha256"] or sha256(PATCH) != adapter["patchSha256"]
            or source_profile.tree_info(gui / PRIVATE) != adapter["compilerTree"]
            or any(sha256(out / "project" / name) != digest for name, digest in native["sources"].items())
            or any(sha256(out / "notices" / name) != digest for name, digest in adapter["notices"].items())):
        raise ValueError("The private binary, compiler evidence or staged adapter source has changed")
    return binary, receipt, native["sources"]


def build(stock, directory, out, seed, jobs):
    stock = original(stock)
    gui = stage(stock, directory, out)
    toolchain = AREA / "toolchain/bin"
    compiler = subprocess.check_output([sys.executable, QA / "check-toolchain.py", TARGET, "--rustc",
                                        toolchain / "rustc"], text=True).strip()
    target = out / "target"
    target.mkdir()
    if seed:
        subprocess.run(["cp", "-a", "--reflink=auto", str(seed / "release"), str(target)], check=True)
    home = out / "cargo-home"
    home.mkdir()
    env = {**os.environ, "CARGO_HOME": str(home), "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": str(out / "layout"),
           "PATH": str(toolchain) + os.pathsep + os.environ["PATH"]}
    subprocess.run([toolchain / "cargo", "metadata", "--format-version", "1", "--offline",
                    *source_config(directory)], cwd=gui, env=env, stdout=subprocess.DEVNULL, check=True)
    check_lock(stock.root / "tools/rust-qa/gui/Cargo.lock", gui / "Cargo.lock")
    cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--ro-bind", "/usr", "/usr",
           "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/cargo", "--dir", "/test-home"]
    for name in ("/bin", "/lib", "/lib64", "/etc/alternatives", "/etc/ld.so.cache"):
        p = Path(name)
        if p.is_symlink():
            cmd += ["--symlink", str(p.readlink()), name]
        elif p.exists():
            cmd += ["--ro-bind", name, name]
    (out / "passwd").write_text(f"qa:x:{os.getuid()}:{os.getgid()}:Synthetic GUI:/test-home:/bin/false\n")
    (out / "group").write_text(f"qa:x:{os.getgid()}:\n")
    for local, mount in ((out / "project", "/project"), (directory, "/vendor"), (toolchain.parent, "/toolchain"),
                         (ROOT / "rust/assets/fonts", "/fonts"), (source_profile.FONTS, "/fallback-fonts"),
                         (out / "passwd", "/etc/passwd"), (out / "group", "/etc/group")):
        cmd += ["--ro-bind", str(local), mount]
    for key, value in {"PATH": "/toolchain/bin:/usr/bin", "CARGO_HOME": "/cargo", "HOME": "/test-home",
                       "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": "/build", "IFW_QA_FONT_DIR": "/fonts",
                       "IFW_QA_FALLBACK_DIR": "/fallback-fonts"}.items():
        cmd += ["--setenv", key, value]
    cmd += ["--bind", str(target), "/build", "--chdir", "/project/tools/rust-qa/gui", "--", "/toolchain/bin/cargo"]
    with (out / "compiler.jsonl").open("xb") as output:
        subprocess.run([*cmd, "build", "--release", "--frozen", "--jobs", str(jobs), "--message-format=json-render-diagnostics",
                        *source_config("/vendor")], stdout=output, check=True)
    native_units = units(out / "compiler.jsonl", True)
    if native_units != units(stock.units, False):
        raise ValueError("Compiler inputs or active features outside the private adapter changed")
    binary = target / "release/native-gui-assessment"
    sources = {name: sha256(out / "project" / name) for name in stock.sources}
    write(out / "native.json", {"target": TARGET, "compiler": compiler, "binarySha256": sha256(binary),
          "adapterSha256": sha256(out / "adapter.json"), "originalReceiptSha256": stock.receipt_sha,
          "unitsCount": native_units.total(), "unitsSha256": sha256(out / "compiler.jsonl"), "sources": sources})
    print(binary, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=STOCK)
    parser.add_argument("--vendor", type=Path, default=VENDOR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1)
    parser.add_argument("--seed-target", type=Path, help="Copy the original measured build cache into the private trial")
    args = parser.parse_args()
    out = args.output.resolve()
    if platform.machine() != "x86_64" or not out.is_relative_to(SCOPE) or out == SCOPE or out.exists():
        parser.error("Use a fresh output below artifacts/rust/flatpak-accessibility on the native Linux x64 host")
    seed = args.seed_target.resolve(strict=True) if args.seed_target else None
    if seed and not seed.is_relative_to(AREA):
        parser.error("Use only an existing private build cache below artifacts/rust")
    out.mkdir(parents=True)
    build(args.stock.resolve(strict=True), args.vendor.resolve(strict=True), out, seed, args.jobs)
