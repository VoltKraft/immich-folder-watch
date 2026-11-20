"""Run the Linux service assessment in isolated offline build and live service namespaces."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import tomllib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
ART = ROOT / "artifacts/rust"
BASE = ART / "linux-services"


def sha(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()

def gui_reference():
    """Resolve only the original GUI manifests used to approve the service package/feature subset."""
    revision = "6c953e32c0b2710bfe06b19805214946653480af"
    source = ROOT / "tools/rust-qa/gui"
    destination = BASE / "source-reference"
    destination.mkdir(parents=True, exist_ok=True)
    for name, digest in (("Cargo.toml", "41e0bf2c09e9401d3743ecc05dfab9e7308f2e2bd4f8f4d6a455146cbed971f4"),
                         ("Cargo.lock", "3d266972f104fae3eb992e8198d25eace401f5c9fe1ed282aa180612fe12cc4a")):
        path = destination / name
        if path.is_file() and sha(path) == digest:
            continue
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            data = subprocess.check_output(["git", "show", f"{revision}:tools/rust-qa/gui/{name}"], cwd=ROOT)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Changed historical GUI {name}")
        with tempfile.TemporaryDirectory(dir=destination) as work:
            temp = Path(work) / name
            temp.write_bytes(data)
            temp.replace(path)
    return destination


def checked_sources(command, target, locked):
    sys.path.insert(0, str(ROOT / "tools/rust-qa"))
    from storage.evidence import verify_archive
    def features(manifest):
        tree = subprocess.check_output(command + ["tree", "--frozen", "--manifest-path", manifest, "--target", target,
            "--edges", "normal,build", "--prefix", "none", "--format", "{p}|{f}"], text=True)
        result = {}
        for row in tree.splitlines():
            if "|" not in row:
                continue
            package, flags = row.removesuffix(" (*)").split("|", 1)
            name, version, *_ = package.split()
            result.setdefault((name, version.removeprefix("v")), set()).add(frozenset(filter(None, flags.split(","))))
        return result
    reference = gui_reference()
    command = list(command)
    index = command.index("--chdir")
    for name in ("Cargo.toml", "Cargo.lock"):
        command[index:index] = ["--ro-bind", str(reference / name), "/project/tools/rust-qa/gui/" + name]
    existing = features("/project/tools/rust-qa/gui/Cargo.toml")
    active = features("Cargo.toml")
    records = []
    registry = ART / "assessment-cache/registry"
    for key, sets in sorted(active.items()):
        if key not in locked:
            continue
        name, version = key
        if not all(any(flags <= reviewed for reviewed in existing.get(key, [])) for flags in sets):
            raise RuntimeError(f"Unassessed source or features: {name} {version}")
        archive, = (registry / "cache").glob(f"*/{name}-{version}.crate")
        source = registry / "src" / archive.parent.name / f"{name}-{version}"
        records.append({"name": name, "version": version, "sha256": locked[key],
                        "unpacked_files": verify_archive(archive, source, locked[key]),
                        "features": sorted(sorted(flags) for flags in sets)})
    return records


def build(lint):
    target = f"{platform.machine()}-unknown-linux-gnu"
    toolchain = ART / "toolchain"
    info = subprocess.check_output([sys.executable, ROOT / "tools/rust-qa/check-toolchain.py", target,
                                    "--rustc", toolchain / "bin/rustc"], text=True)
    def locked(path):
        return {(p["name"], p["version"]): p["checksum"] for p in tomllib.loads(path.read_text())["package"] if "source" in p}
    graph = locked(HERE / "Cargo.lock")
    reviewed = locked(gui_reference() / "Cargo.lock")
    if any(reviewed.get(k) != value for k, value in graph.items()):
        raise RuntimeError("The service fixture added an unassessed archive or digest")
    output = BASE / "build"
    output.mkdir(parents=True, exist_ok=True)
    command = ["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--dir", "/test-home", "--dir", "/cargo", "--ro-bind", str(toolchain), "/toolchain",
               "--ro-bind", str(ART / "assessment-cache/registry"), "/cargo/registry",
               "--ro-bind", str(ROOT / "rust"), "/project/rust", "--ro-bind", str(HERE), "/project/tools/rust-qa/linux-services",
               "--ro-bind", str(ROOT / "tools/rust-qa/gui"), "/project/tools/rust-qa/gui",
               "--bind", str(output), "/build"]
    for name in ("bin", "lib", "lib64"):
        path = Path("/") / name
        if path.is_symlink():
            command += ["--symlink", str(path.readlink()), str(path)]
        elif path.is_dir():
            command += ["--ro-bind", str(path), str(path)]
    for path in ("/etc/alternatives", "/etc/ld.so.cache"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    command += ["--setenv", "HOME", "/test-home", "--setenv", "PATH", "/toolchain/bin:/usr/bin",
                "--setenv", "CARGO_HOME", "/cargo", "--setenv", "CARGO_TARGET_DIR", "/build",
                "--chdir", "/project/tools/rust-qa/linux-services", "--", "/toolchain/bin/cargo"]
    sources = checked_sources(command, target, graph)
    if lint:
        subprocess.run(command + ["clippy", "--frozen", "--all-targets", "--", "-D", "warnings"], check=True)
        return
    subprocess.run(command + ["build", "--frozen"], check=True)
    files = [HERE / "Cargo.toml", HERE / "Cargo.lock", *sorted((HERE / "src").rglob("*.rs")), ROOT / "rust/Cargo.toml"]
    for name in ("desktop-lifecycle", "safe-fs"):
        crate = ROOT / "rust/crates" / name
        files += [crate / "Cargo.toml", *sorted((crate / "src").rglob("*.rs"))]
    (BASE / "inputs.json").write_text(json.dumps({"compiler": info.strip(), "target": target,
        "archive_count": len(graph), "active_registry_inputs": sources, "source": {str(p.relative_to(ROOT)): sha(p) for p in files},
        "binaries": {name: sha(output / "debug" / name) for name in ("grant", "tray")}}, indent=2) + "\n")


def launch(part, portal=None, expectation=None):
    if portal:
        portal = portal.resolve(strict=True)
        if part != "documents" or not portal.is_relative_to((ART / "portal-reference-build").resolve()) or not portal.is_file():
            raise ValueError("Alternative portal must be a file in artifacts/rust/portal-reference-build for the documents trial")
    sys.path.insert(0, str(ROOT / "tools/rust-qa/performance"))
    from linux import namespace
    BASE.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{part}-", dir=BASE))
    print("Isolated evidence directory", work, flush=True)
    specs = {"outer_namespaces": {k: os.readlink(f"/proc/self/ns/{k}") for k in ("net", "mnt", "ipc", "pid", "user")},
             "build": json.loads((BASE / "inputs.json").read_text()),
             "drivers": {str(p.relative_to(ROOT)): sha(p) for p in [*sorted(HERE.glob("*.py")),
                 *(ROOT / "tools/rust-qa/performance" / name for name in ("linux.py", "session.py", "x11.py"))]}}
    for name, digest in specs["build"]["source"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError(f"Rebuild after changes to {name}")
    (work / "inputs.json").write_text(json.dumps(specs, indent=2) + "\n")
    command = namespace(work, HERE, None)
    end = command.index("--chdir")
    additions = ["--dir", "/probe"]
    for name in specs["build"]["binaries"]:
        additions += ["--ro-bind", str(BASE / "build/debug" / name), "/probe/" + name]
    if part == "documents":
        if not Path("/dev/fuse").is_char_device():
            raise RuntimeError("A real /dev/fuse and permission to use it in a private user namespace are required")
        # Namespace root maps exclusively to the invoking host user. Only this private mount is managed.
        additions += ["--uid", "0", "--gid", "0", "--cap-add", "CAP_SYS_ADMIN", "--dev-bind", "/dev/fuse", "/dev/fuse"]
        (work / "etc/passwd").write_text("root:x:0:0:Synthetic portal user:/tmp/home:/bin/false\n")
        (work / "etc/group").write_text("root:x:0:\n")
        runtime = "/run/user/0"
        from dotnet_build import reference_sdk
        sdk = reference_sdk(ART)
        additions += ["--dir", "/runtime"]
        for entry in ("dotnet", "host", "shared"):
            additions += ["--ro-bind", str(sdk / entry), f"/runtime/{entry}"]
        additions += ["--ro-bind", str(BASE / "dotnet/bin/PortalReference/release"), "/oracle"]
        specs["dotnet_oracle"] = json.loads((BASE / "dotnet/inputs.json").read_text())
        if any(sha(ROOT / name) != digest for name, digest in specs["dotnet_oracle"]["source"].items()):
            raise RuntimeError("Rebuild the .NET oracle after source changes")
        daemon = portal or Path("/usr/libexec/xdg-document-portal")
        additions += ["--ro-bind", str(daemon), "/probe/xdg-document-portal"]
        specs["documents_daemon_sha256"] = sha(daemon)
        specs["daemon_origin"] = str(portal.relative_to(ROOT)) if portal else "distro"
        specs["expected_lock"] = expectation or ("supported" if portal else "enosys")
        specs["kernel"] = platform.release()
        (work / "inputs.json").write_text(json.dumps(specs, indent=2) + "\n")
    else:
        binary = ART / "gui-build/release/native-gui-assessment"
        additions += ["--ro-bind", str(binary), "/probe/native-gui-assessment"]
        specs["gui_binary_sha256"] = sha(binary)
        (work / "inputs.json").write_text(json.dumps(specs, indent=2) + "\n")
        runtime = f"/run/user/{os.getuid()}"
    command[end:] = [*additions, "--dir", "/run", "--dir", "/run/user", "--dir", runtime,
        "--setenv", "XDG_RUNTIME_DIR", runtime, "--setenv", "IFW_QA_ISOLATED", "1",
        "--setenv", "GSETTINGS_BACKEND", "memory", "--chdir", "/qa", "--",
        "/usr/bin/python3", "/app/native.py", part, "--inside"]
    return subprocess.run(command).returncode


def inside(part):
    sys.path.insert(0, "/driver")
    from session import private_session
    inputs = json.loads(Path("/qa/inputs.json").read_text())
    if (Path.home() != Path("/tmp/home") or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or not all(os.readlink(f"/proc/self/ns/{k}") != s for k, s in inputs["outer_namespaces"].items())):
        raise RuntimeError("A private assessment home, session bus and namespaces are required")
    if any(sha(Path("/probe") / name) != value for name,value in inputs["build"]["binaries"].items()):
        raise RuntimeError("Native binary differs from its bound Rust sources")
    if part == "tray" and sha(Path("/probe/native-gui-assessment")) != inputs["gui_binary_sha256"]:
        raise RuntimeError("Native GUI differs from its recorded binary")
    os.umask(0o077)
    Path.home().mkdir()
    Path(os.environ["XDG_RUNTIME_DIR"]).chmod(0o700)
    with ExitStack() as stack:
        display, _ = private_session(stack)
        if part == "documents":
            from documents import probe
            if sha(Path("/probe/xdg-document-portal")) != inputs["documents_daemon_sha256"] or any(
                sha(Path("/oracle") / n) != digest for n, digest in inputs["dotnet_oracle"]["output"].items()):
                raise RuntimeError("Native portal or compiled shipping reference differs from its recorded input")
            probe(stack, inputs["expected_lock"])
        else:
            from desktop import probe
            probe(stack, display)
    print(f"{part} passed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("build", "lint", "oracle", "documents", "tray"))
    parser.add_argument("--portal-binary", type=Path, help="An explicitly supplied Documents daemon below artifacts/rust/portal-reference-build")
    parser.add_argument("--expect-lock", choices=("supported", "enosys"), help="Required independent lock semantics for this daemon")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.part in ("build", "lint"):
        build(args.part == "lint")
    elif args.part == "oracle":
        from dotnet_build import build_reference
        build_reference(ROOT, HERE, ART, BASE, sha)
    else:
        sys.exit(inside(args.part) if args.inside else launch(args.part, args.portal_binary, args.expect_lock))
