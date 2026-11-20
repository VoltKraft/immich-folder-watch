#!/usr/bin/env python3
"""Build a private 1.22.1 Documents portal with the upstream flock hunk only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = REPO / "artifacts/rust/portal-reference-build"
SDK_COMMIT = "a1b744b072d9f55d061e35382547ae80dad8d92abecc1da7dc1818de2daabfd3"
SDK = Path("/var/lib/flatpak/runtime/org.freedesktop.Sdk/x86_64/26.08") / SDK_COMMIT / "files"
SOURCE_NAME = "xdg-desktop-portal-1.22.1"
PATCH_SHA256 = "5d7a386866288358b46621e85cbb68e9f008a19f669acc18859cd82f82f7fc5b"
INPUTS = {
    "xdg-desktop-portal-1.22.1.tar.xz": {
        "sha256": "d4879ddb3d65ff1a8f19187497e6f13dc5d267bcac404a5d501218be355753d3",
        "url": "https://github.com/flatpak/xdg-desktop-portal/releases/download/1.22.1/xdg-desktop-portal-1.22.1.tar.xz",
    },
    "fuse3-devel-3.18.3-1.fc45.x86_64.rpm": {
        "sha256": "2118daa7274b5a426eea52b47f795f2d0409289cda1320a982730c97374dfeac",
        "url": "https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Everything/x86_64/os/Packages/f/fuse3-devel-3.18.3-1.fc45.x86_64.rpm",
    },
    "fuse3-libs-3.18.3-1.fc45.x86_64.rpm": {
        "sha256": "ff4cfeae51ccec5ba95b47bec09727a592d96a038721068bf8c2064696027978",
        "url": "https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Everything/x86_64/os/Packages/f/fuse3-libs-3.18.3-1.fc45.x86_64.rpm",
    },
}
OPTIONS = [
    "--wrap-mode=nodownload", "--buildtype=release",
    "-Dc_args=-D_GNU_SOURCE=1 -include sys/file.h",
    "-Dtests=disabled", "-Ddocumentation=disabled", "-Dman-pages=disabled",
    "-Dflatpak-interfaces=disabled", "-Dgeoclue=disabled", "-Dgudev=disabled",
    "-Dsystemd=disabled", "-Dinstalled-tests=false",
]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = "symlink:" + os.readlink(path)
        elif path.is_file():
            result[str(path.relative_to(root))] = sha(path)
    return result


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: list[str], log: Path, *, cwd: Path | None = None, data: bytes | None = None) -> None:
    with log.open("wb") as stream:
        result = subprocess.run(args, cwd=cwd, input=data, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def sandbox(output: Path) -> list[str]:
    return [
        "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
        "--ro-bind", str(SDK), "/usr", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind", str(SDK / "etc"), "/etc", "--bind", str(output), "/work",
        "--ro-bind", str(output / "stage"), "/fuse",
        "--ro-bind", str(output / "stage/fuse3-sdk.pc"), "/fuse/usr/lib64/pkgconfig/fuse3.pc",
        "--ro-bind", "/usr/bin/bwrap", "/tools/bwrap", "--clearenv",
        "--setenv", "PATH", "/tools:/usr/bin", "--setenv", "HOME", "/tmp",
        "--setenv", "LC_ALL", "C.UTF-8", "--setenv", "XDG_DATA_HOME", "/tmp/data",
        "--setenv", "XDG_CONFIG_HOME", "/tmp/config", "--setenv", "XDG_CACHE_HOME", "/tmp/cache",
        "--setenv", "PKG_CONFIG_PATH", "/fuse/usr/lib64/pkgconfig",
        "--setenv", "CCACHE_DISABLE", "1", "--chdir", "/work", "--",
    ]


def runtime_inventory(output: Path) -> None:
    """Record actual host library bytes and RPM ownership from loader output."""
    paths = set(re.findall(r"(/[A-Za-z0-9_./+-]+) ", (output / "host-loader.log").read_text()))
    records = []
    for name in sorted(paths):
        path = Path(name).resolve(strict=True)
        metadata = subprocess.run(
            ["rpm", "-qf", "--qf", "%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n%{LICENSE}\n", str(path)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout.splitlines()
        records.append({"loader_path": name, "resolved_path": str(path), "sha256": sha(path), "rpm": metadata})
    write_json(output / "host-runtime-inputs.json", records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory below artifacts/rust/portal-reference-build")
    parser.add_argument("--cache", type=Path, default=ROOT)
    parser.add_argument("--download", action="store_true", help="Acquire missing pinned public inputs; compilation remains offline")
    parser.add_argument("--unpatched-control", action="store_true", help="Build the identical pristine release as an ENOSYS control")
    args = parser.parse_args()
    output = args.output.resolve()
    cache = args.cache.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output == ROOT.resolve():
        raise SystemExit("Output must be a new child of artifacts/rust/portal-reference-build")
    if not cache.is_relative_to(ROOT.resolve()):
        raise SystemExit("Input cache must remain in artifacts/rust/portal-reference-build")
    output.mkdir(parents=True, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=True)
    state = {
        "status": "preparing", "sdk_commit": SDK_COMMIT, "inputs": INPUTS, "options": OPTIONS,
        "release_commit": "1d20fadc304f6601452b5db65ed91197dba77041",
        "fix_commit": "caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57",
        "unpatched_control": args.unpatched_control,
    }
    try:
        if not SDK.is_dir():
            raise RuntimeError("The exact installed freedesktop SDK is required; see README.md")
        for name, pin in INPUTS.items():
            path = cache / name
            if not path.exists():
                if not args.download:
                    raise RuntimeError(f"Missing pinned input {path}; use --download for acquisition")
                with urllib.request.urlopen(pin["url"], timeout=60) as response:
                    data = response.read(16 * 1024 * 1024 + 1)
                if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != pin["sha256"]:
                    raise RuntimeError(f"Invalid downloaded input: {name}")
                path.write_bytes(data)
            if sha(path) != pin["sha256"]:
                raise RuntimeError(f"Checksum mismatch: {name}")
        run(["rpmkeys", "--checksig", *[str(cache / name) for name in INPUTS if name.endswith(".rpm")]], output / "rpm-signatures.log")
        with tarfile.open(cache / (SOURCE_NAME + ".tar.xz")) as archive:
            for member in archive.getmembers():
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or path.parts[0] != SOURCE_NAME:
                    raise RuntimeError("Unsafe source archive member")
            archive.extractall(output, filter="data")
        source = output / SOURCE_NAME
        before = manifest(source)
        patch = HERE / "flock-upstream.patch"
        if sha(patch) != PATCH_SHA256:
            raise RuntimeError("The reviewed original upstream patch changed")
        if not args.unpatched_control:
            run(["patch", "--batch", "--fuzz=0", "--no-backup-if-mismatch", "-p1", "-i", str(patch)], output / "patch.log", cwd=source)
        after = manifest(source)
        changed = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
        expected = [] if args.unpatched_control else ["document-portal/document-portal-fuse.c"]
        if changed != expected:
            raise RuntimeError(f"Unexpected source changes: {changed}")
        write_json(output / "source-original-sha256.json", before)
        write_json(output / "source-patched-sha256.json", after)
        state["patch_sha256"] = sha(patch)
        state["source_changes"] = {name: {"before": before[name], "after": after[name]} for name in changed}
        stage = output / "stage"
        stage.mkdir()
        for name in INPUTS:
            if not name.endswith(".rpm"):
                continue
            data = subprocess.run(["rpm2cpio", str(cache / name)], check=True, stdout=subprocess.PIPE).stdout
            run(["cpio", "-idm", "--no-absolute-filenames"], output / (name + ".extract.log"), cwd=stage, data=data)
        pc = (stage / "usr/lib64/pkgconfig/fuse3.pc").read_text()
        if pc.count("prefix=/usr\n") != 1:
            raise RuntimeError("Unexpected fuse3 pkg-config prefix")
        (stage / "fuse3-sdk.pc").write_text(pc.replace("prefix=/usr\n", "prefix=/fuse/usr\n"))
        write_json(output / "staged-inputs-sha256.json", manifest(stage))
        state["host_bwrap_sha256"] = sha(Path("/usr/bin/bwrap"))
        state["status"] = "building"
        recipe = output / "recipe"
        recipe.mkdir()
        for path in sorted(HERE.iterdir()):
            if path.is_file():
                shutil.copyfile(path, recipe / path.name)
        write_json(output / "result.json", state)
        commands = [
            ["meson", "setup", "build", SOURCE_NAME, *OPTIONS],
            ["meson", "compile", "-C", "build", "xdg-document-portal"],
        ]
        write_json(output / "build-commands.json", [sandbox(output) + command for command in commands])
        for name, command in zip(("configure", "compile"), commands):
            run(sandbox(output) + command, output / (name + ".log"))
        binary = output / "build/document-portal/xdg-document-portal"
        run(["readelf", "-l", "-d", "-V", str(binary)], output / "elf.log")
        # Loader --list resolves dependencies without invoking daemon startup.
        run(["/lib64/ld-linux-x86-64.so.2", "--list", str(binary)], output / "host-loader.log")
        run([str(binary), "--version"], output / "version.log")
        runtime_inventory(output)
        state["status"] = "passed"
        state["binary"] = str(binary.relative_to(REPO))
        state["binary_sha256"] = sha(binary)
        state["recipe_sha256"] = manifest(recipe)
        state["runtime_acceptance"] = "Separate real FUSE harness required; no system installation"
        print(state["binary"])
        print(state["binary_sha256"])
    except Exception as error:
        state["status"] = "failed"
        state["error"] = str(error)
        raise
    finally:
        write_json(output / "result.json", state)


if __name__ == "__main__":
    main()
