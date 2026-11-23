"""Rebuild the private Documents portal test package from the signed Noble source record."""
import argparse
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
NOBLE = HERE.parents[1]
sys.path.insert(0, str(NOBLE))
from build import AFTER, BEFORE, C_FILE, FUSE, LICENSES
from inputs import ORIGINALS, PATCH, PATCH_SHA, SOURCE, VERSION, sha
from verify import authenticate

QA_VERSION = VERSION + "+ifwqa1"
PATCH_NAME = "ifwqa-forward-flock.patch"
NOBLE_PATCH_SHA = "194650d5d80976d9f0cdca343184003f69fb95820420d34b78d3e9bf86d0d87c"
UPSTREAM_HANDLER = "345be9c752b5b7dc8d99044ee59f2adab03bd65eb3b94f085577e2bc6c61a9c4"
PREFIX = f"{SOURCE}_{QA_VERSION}"
PATCH_INFO = b"""Description: Forward flock on the open Documents portal file descriptor
Author: Sebastian Wick
Origin: upstream, https://github.com/flatpak/xdg-desktop-portal/commit/caa5ae9e21e44c70c0cf3e7fa78de557acd3ea57
Forwarded: not-needed
Last-Update: 2026-11-23

"""
CHANGELOG = f"""{SOURCE} ({QA_VERSION}) UNRELEASED; urgency=medium

  * Private Immich Folder Watch feasibility build. Backport the upstream
    Documents file lock handler and supply the system declaration for flock.

 -- Immich Folder Watch QA <qa@example.invalid>  Mon, 23 Nov 2026 00:00:00 +0000

"""
BUILD_FLAGS = b"export DEB_CPPFLAGS_MAINT_APPEND = -D_GNU_SOURCE=1 -include sys/file.h\n"


def run(log, cmd, cwd, env=None):
    with log.open("xb") as stream:
        result = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{cmd[0]} exited {result.returncode}; see {log}")


def sources(tree, runtime=False):
    """Record quilt sources or the full paths, modes and bytes of a packaged runtime."""
    manifest = {}
    for p in sorted(tree.rglob("*")):
        rel = p.relative_to(tree)
        if not runtime and rel.parts[0] == ".pc":
            continue  # dpkg-source's quilt bookkeeping differs between extraction and a local push.
        if p.is_symlink():
            value = ["link", os.readlink(p)]
        elif p.is_file():
            mode = p.stat().st_mode
            value = ["file", stat.S_IMODE(mode) if runtime else bool(mode & stat.S_IXUSR), sha(p)]
        elif p.is_dir():
            if not runtime:
                continue
            value = ["directory", stat.S_IMODE(p.stat().st_mode)]
        else:
            raise ValueError(f"Unexpected source entry {rel}")
        manifest[rel.as_posix()] = value
    return manifest


def authenticate_tree(tree, expected):
    if sha(tree / C_FILE) != expected or any(sha(tree / name) != digest for name, digest in LICENSES.items()):
        raise ValueError("The original Ubuntu patch series, upstream source or notices differ")
    if expected == AFTER:
        match = re.search(br"^static void\nxdp_fuse_flock \(.*?^\}\n",
                          (tree / C_FILE).read_bytes(), re.MULTILINE | re.DOTALL)
        if not match or hashlib.sha256(match[0]).hexdigest() != UPSTREAM_HANDLER:
            raise ValueError("The complete Documents handler differs from the reviewed upstream function")


def prepare_metadata(tree):
    patch = NOBLE / "flock.patch"
    if sha(patch) != NOBLE_PATCH_SHA or sha(PATCH) != PATCH_SHA:
        raise ValueError("Unexpected reviewed Documents backport inputs")
    package = tree / "debian"
    series = package / "patches/series"
    if not series.read_bytes().endswith(b"\n"):
        raise ValueError("Expected a complete Ubuntu series file")
    with (package / "patches" / PATCH_NAME).open("xb") as target:
        target.write(PATCH_INFO + patch.read_bytes())
    with series.open("ab") as target:
        target.write((PATCH_NAME + "\n").encode())
    changelog = package / "changelog"
    changelog.write_bytes(CHANGELOG.encode() + changelog.read_bytes())
    rules = package / "rules"
    original = rules.read_bytes()
    needle = b"export DEB_BUILD_MAINT_OPTIONS = hardening=+all\n"
    if original.count(needle) != 1:
        raise ValueError("Unexpected original Ubuntu hardening rules")
    rules.write_bytes(original.replace(needle, needle + BUILD_FLAGS))


def check_source_delta(before, after):
    expected = {C_FILE, "debian/changelog", "debian/rules", "debian/patches/series", "debian/patches/" + PATCH_NAME}
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    if changed != expected:
        raise ValueError(f"Unexpected source-package delta: {sorted(changed)}")


def source_package(inputs, out):
    signed = authenticate(Path("/"), inputs, False)
    for name, digest in ORIGINALS.items():
        path = inputs / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError(f"Ubuntu source object differs from its signed index: {name}")
        if ".orig" in name:
            shutil.copyfile(path, out / name)
    tree = out / "source"
    run(out / "unpack-original.log", ["dpkg-source", "--no-check", "-x", inputs / f"{SOURCE}_{VERSION}.dsc", tree], out)
    authenticate_tree(tree, BEFORE)
    before = sources(tree)
    prepare_metadata(tree)
    run(out / "apply.log", ["dpkg-source", "--before-build", tree], out)
    authenticate_tree(tree, AFTER)
    modified = sources(tree)
    check_source_delta(before, modified)
    run(out / "make-source.log", ["dpkg-source", "-b", tree], out)
    dsc = out / (PREFIX + ".dsc")
    rebuilt = out / "reconstructed"
    run(out / "reconstruct-source.log", ["dpkg-source", "--no-check", "-x", dsc, rebuilt], out)
    if sources(rebuilt) != modified:
        raise ValueError("The source package did not reconstruct the complete reviewed tree")
    files = [dsc, *out.glob(PREFIX + ".debian.tar.*"), *(out / name for name in ORIGINALS if ".orig" in name)]
    if len(files) != 4:
        raise ValueError("Expected the full two-component Noble source package")
    return rebuilt, {"verifiedUbuntuSource": signed, "inputs": ORIGINALS, "licenses": LICENSES,
                     "originalVersion": VERSION, "version": QA_VERSION,
                     "originalFile": BEFORE, "changedFile": AFTER, "handlerSha256": UPSTREAM_HANDLER,
                     "noblePatch": NOBLE_PATCH_SHA, "upstreamPatch": PATCH_SHA,
                     "sourcePackage": {p.name: sha(p) for p in files},
                     "reconstructedTreeSha256": hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()}


def verify_services(payload):
    """Follow both activation declarations supplied by the built runtime package."""
    from configparser import ConfigParser
    result = {}
    for bus, image in (("org.freedesktop.portal.Documents", "xdg-document-portal"),
                       ("org.freedesktop.impl.portal.PermissionStore", "xdg-permission-store")):
        executable = "/usr/libexec/" + image
        location = payload / executable[1:]
        unit = image + ".service"
        files = (payload / f"usr/share/dbus-1/services/{bus}.service", payload / f"usr/lib/systemd/user/{unit}")
        entries = []
        for path, section in zip(files, ("D-BUS Service", "Service"), strict=True):
            cfg = ConfigParser(interpolation=None)
            cfg.optionxform = str
            cfg.read_string(path.read_text())
            entries.append(cfg[section])
        dbus, service = entries
        if ((dbus["Name"], dbus["Exec"], dbus["SystemdService"]) != (bus, executable, unit)
                or (service["BusName"], service["ExecStart"], service["Type"]) != (bus, executable, "dbus")
                or not location.is_file() or location.is_symlink() or not os.access(location, os.X_OK)):
            raise ValueError(f"Unexpected package activation of {bus}")
        result[bus] = {p.relative_to(payload).as_posix(): sha(p) for p in (*files, location)}
    return result


def native_image(image, arch):
    header = subprocess.check_output(["readelf", "-hW", image], text=True)
    machine = re.search(r"^\s*Machine:\s+(.+)$", header, re.MULTILINE)
    expected = {"amd64": "Advanced Micro Devices X86-64", "arm64": "AArch64"}[arch]
    if not machine or machine[1] != expected:
        raise ValueError(f"The packaged ELF machine differs from {arch}")
    notes = subprocess.check_output(["readelf", "-nW", image], text=True)
    ids = re.findall(r"Build ID: ([a-f0-9]+)", notes)
    if len(ids) != 1:
        raise ValueError(f"Expected a single native build ID in {image.name}")
    return ids[0]


def check_runtime(out, tree, payload, arch):
    staged = tree / "debian" / SOURCE
    expected = {p: v for p, v in sources(staged, runtime=True).items() if p.split("/")[0] != "DEBIAN"}
    packaged = sources(payload, runtime=True)
    if not packaged or packaged != expected:
        raise ValueError("Runtime package contents differ from the native Debian staging tree")
    manifest = out / "runtime-files.json"
    manifest.write_text(json.dumps(packaged, sort_keys=True, indent=2) + "\n")
    if sha(payload / "usr/share/doc" / SOURCE / "copyright") != LICENSES["debian/copyright"]:
        raise ValueError("Runtime package copyright differs from the authenticated source")
    services = verify_services(payload)
    installed = payload / "usr/libexec/xdg-document-portal"
    builds = list(tree.glob("obj-*/document-portal/xdg-document-portal"))
    build_id = native_image(installed, arch)
    if len(builds) != 1 or native_image(builds[0], arch) != build_id:
        raise ValueError("The installed Documents daemon differs from the linked native build")
    syms = subprocess.check_output(["readelf", "--dyn-syms", "--wide", installed], text=True)
    if not re.search(r"\bUND\s+flock@GLIBC_[0-9.]+\b", syms):
        raise ValueError("The packaged Documents daemon does not import flock from libc")
    return {"runtimeEntries": len(packaged), "runtimeManifestSha256": sha(manifest),
            "activationFiles": services, "documentDaemonBuildId": build_id}


def package_checksums(path, required):
    record = Parser().parsestr(path.read_text())
    if record.get_all("Version") != [QA_VERSION] or record.get_all("Source") != [SOURCE]:
        raise ValueError(f"Wrong source package in {path.name}")
    sections = record.get_all("Checksums-Sha256", [])
    if len(sections) != 1:
        raise ValueError(f"Missing or duplicate SHA-256 section in {path.name}")
    observed = set()
    for row in sections[0].strip().splitlines():
        digest, size, name = row.split()
        if name in observed or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+~-]+", name):
            raise ValueError(f"Unexpected package record member in {path.name}")
        member = path.parent / name
        if member.is_symlink() or member.stat().st_size != int(size) or sha(member) != digest:
            raise ValueError(f"Original {name} differs from {path.name}")
        observed.add(name)
    if not required <= observed:
        raise ValueError(f"Missing native packages in {path.name}")


def binary_packages(out, tree, arch, skip_tests):
    env = {**os.environ, "DEB_BUILD_OPTIONS": "parallel=4" + (" nocheck" if skip_tests else ""),
           "LC_ALL": "C.UTF-8", "DEB_BUILD_PROFILES": ""}
    run(out / "build-dependencies.log", ["dpkg-checkbuilddeps"], tree, env)
    if any(sha(Path("/usr") / p) != digest for p, digest in FUSE.items()):
        raise ValueError("The native FUSE development headers or notices differ from the reviewed build")
    run(out / "build-binary.log", ["dpkg-buildpackage", "--build=binary", "--no-sign", "-j4"], tree, env)
    packages = {}
    runtime = None
    for p in sorted([*out.glob("*.deb"), *out.glob("*.ddeb")]):
        name, version, machine = subprocess.check_output(
            ["dpkg-deb", "-W", "--showformat=${Package} ${Version} ${Architecture}", p], text=True).split()
        if (name in packages or name not in {SOURCE, SOURCE + "-dev", SOURCE + "-tests",
                                              SOURCE + "-dbgsym", SOURCE + "-tests-dbgsym"}
                or version != QA_VERSION or machine != ("all" if name == SOURCE + "-dev" else arch)):
            raise ValueError(f"Unexpected binary package {p.name}")
        packages[name] = {"file": p.name, "sha256": sha(p), "version": version, "architecture": machine}
        if name == SOURCE:
            runtime = p
    if not {SOURCE, SOURCE + "-dev", SOURCE + "-tests"} <= packages.keys():
        raise ValueError("Missing Ubuntu runtime, development or installed-tests package")
    payload = out / "runtime-payload"
    run(out / "read-package.log", ["dpkg-deb", "-x", runtime, payload], out)
    runtime_evidence = check_runtime(out, tree, payload, arch)
    required = {p["file"] for p in packages.values()}
    logs = {}
    for ext in ("buildinfo", "changes"):
        path = out / f"{PREFIX}_{arch}.{ext}"
        package_checksums(path, required)
        logs[path.name] = sha(path)
        required.add(path.name)
    return {"packages": packages, **runtime_evidence, "fuseInputs": FUSE, "buildRecords": logs,
            "buildOptions": env["DEB_BUILD_OPTIONS"], "distributionBuildTestsRequested": not skip_tests}


def main(args):
    os.environ["LC_ALL"] = "C.UTF-8"
    osinfo = Path("/usr/lib/os-release").read_text().splitlines()
    if "VERSION_CODENAME=noble" not in osinfo or "ID=ubuntu" not in osinfo:
        raise ValueError("Use an isolated Ubuntu Noble guest")
    arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    if {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine()) != arch:
        raise ValueError("Expected a native x64 or ARM64 Ubuntu package build")
    for a, b in [(VERSION, QA_VERSION), (QA_VERSION, "1.18.4-1ubuntu2.24.04.4")]:
        subprocess.run(["dpkg", "--compare-versions", a, "lt", b], check=True)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    record = {"architecture": arch, "status": "failed"}
    try:
        tree, results = source_package(args.inputs.resolve(strict=True), out)
        record.update(results)
        if not args.source_only:
            record.update(binary_packages(out, tree, arch, args.skip_build_tests))
        record["status"] = "source-reconstructed" if args.source_only else "native-packages-built"
    except Exception as error:
        record["error"] = str(error)
        raise
    finally:
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="read-only signed four-object source and index directory")
    parser.add_argument("--output", type=Path, required=True, help="new build directory in the isolated guest")
    parser.add_argument("--source-only", action="store_true", help="prepare and verify the reconstructable source package only")
    parser.add_argument("--skip-build-tests", action="store_true", help="set Debian nocheck, recorded in result.json")
    main(parser.parse_args())
