"""Run the Noble package, its exact source control and the private backport in separate sessions."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from build import pair
from inputs import ART, BASE, HERE, ROOT, VERSION, sha, source_inputs
from prepare import guest, observe_split_python, prepare

sys.path.insert(0, str(HERE.parent / "linux-services"))
from dotnet_build import reference_sdk


def record(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def run_probe(osroot, out, portal, reader, expected, binary_source):
    out.mkdir()
    sdk = reference_sdk(ART)
    reference = ART / "linux-services/dotnet"
    receipt = json.loads((reference / "inputs.json").read_text())
    oracle = reference / "bin/PortalReference/release"
    if any(sha(ROOT / name) != digest for name, digest in receipt["source"].items()):
        raise ValueError("Rebuild the existing C# oracle from the current sources")
    if any(sha(oracle / name) != digest for name, digest in receipt["output"].items()):
        raise ValueError("Unexpected compiled .NET oracle")
    marker = out / "machine-id"
    import uuid
    marker.write_text(uuid.uuid4().hex + "\n")
    (out / "passwd").write_text("root:x:0:0:Private Documents session:/tmp/home:/bin/false\n")
    (out / "group").write_text("root:x:0:\n")
    record(out / "input.json", dict(outerNamespaces={k: os.readlink("/proc/self/ns/" + k)
                                      for k in ("mnt", "user", "net", "pid", "ipc", "uts")},
           kernel=platform.release(), daemonSha256=sha(portal), storeSha256=sha(osroot / "usr/libexec/xdg-permission-store"),
           daemonSource=binary_source, oracle=sha(reference / "inputs.json"),
           oracleLibraries=receipt["output"], rustReaderSha256=sha(reader), expected=expected))
    cmd = guest(osroot, osroot / "usr", extra=["--uid", "0", "--gid", "0", "--cap-add", "CAP_SYS_ADMIN",
        "--dev-bind", "/dev/fuse", "/dev/fuse", "--dir", "/run/user/0", "--dir", "/probe",
        "--ro-bind", str(marker), "/etc/machine-id", "--ro-bind", str(out / "passwd"), "/etc/passwd",
        "--ro-bind", str(out / "group"), "/etc/group", "--ro-bind", str(portal), "/probe/portal",
        "--ro-bind", str(reader), "/probe/reader", "--ro-bind", str(HERE), "/recipe", "--ro-bind", str(oracle), "/oracle",
        "--bind", str(out), "/result", "--setenv", "XDG_RUNTIME_DIR", "/run/user/0",
        "--setenv", "DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/session-bus", "--setenv", "IFW_QA_ISOLATED", "1",
        "--setenv", "DOTNET_CLI_TELEMETRY_OPTOUT", "1", "--setenv", "DOTNET_ROOT", "/runtime"])
    for child in ("dotnet", "host", "shared"):
        cmd += ["--ro-bind", str(sdk / child), "/runtime/" + child]
    with (out / "probe.log").open("wb") as log:
        subprocess.run(cmd + ["--", "python3", "/recipe/observe.py", "observe", expected], stdout=log,
                       stderr=subprocess.STDOUT, timeout=170, check=True)
    result = json.loads((out / "observation.json").read_text())
    if result.get("status") != "passed" or not result["revoked"] or not result["contentUnchanged"]:
        raise ValueError("Incomplete native portal observation")
    return dict(daemon=sha(portal), operations=len(result["operations"]), grant=result["documentId"],
                observation=sha(out / "observation.json"), inputs=sha(out / "input.json"))


def main(hosted, download, split_python=False):
    if hosted:
        if split_python:
            raise ValueError("The layer-split control uses the local immutable Noble fixture")
        if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
            raise ValueError("Hosted mode requires a disposable native GitHub runner")
        osroot = aptroot = Path("/")
    else:
        osroot, aptroot = ART / "gui-noble-native/userspace", ART / "gui-noble-native/root"
    arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    if "VERSION_CODENAME=noble" not in (osroot / "etc/os-release").read_text():
        raise ValueError("Expected the Ubuntu 24.04 userspace")
    runs = BASE / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(dir=runs, prefix=arch + "-"))
    print(out, flush=True)
    facts = dict(status="running", release=VERSION, architecture=arch, results={},
                 revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                 drivers={p.name: sha(p) for p in sorted(HERE.glob("*")) if p.is_file()})
    start = time.monotonic()
    try:
        from verify import authenticate, check_control
        if not Path("/dev/fuse").is_char_device():
            raise ValueError("The private mount needs the real /dev/fuse device")
        cache = source_inputs(download)
        target = platform.machine() + "-unknown-linux-gnu"
        facts["rustc"] = subprocess.check_output([sys.executable, str(HERE.parent / "check-toolchain.py"), target,
            "--rustc", str(ART / "toolchain/bin/rustc")], text=True).strip()
        facts["apt"] = authenticate(aptroot, cache, download)
        dev = out / "development"
        dev.mkdir()
        prepare(osroot, aptroot, dev, arch, download)
        authentic = check_control(osroot, aptroot, arch, cache, download, out)
        facts["control"] = authentic
        build = out / "build"
        build.mkdir()
        if split_python:
            facts["splitPythonControl"] = observe_split_python(osroot, dev, build)
        facts["build"] = pair(osroot, dev, cache, build)
        for name, expect in (("packaged", "enosys"), ("unmodified", "enosys"), ("backport", "supported")):
            executable = (osroot / "usr/libexec/xdg-document-portal" if name == "packaged" else
                          build / name / "document-portal/xdg-document-portal")
            facts["results"][name] = run_probe(osroot, out / name, executable, build / "reader", expect, name)
            record(out / "result.json", facts)
        facts["status"] = "passed"
        return 0
    except Exception as error:
        facts.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        facts["seconds"] = round(time.monotonic() - start, 3)
        record(out / "result.json", facts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--hosted", action="store_true")
    group.add_argument("--local-noble", action="store_true")
    parser.add_argument("--download", action="store_true", help="Fetch checked public Ubuntu inputs into the private cache")
    parser.add_argument("--local-split-python", action="store_true",
                        help="Reproduce the hosted lower Python and upper Meson split in the private local view")
    args = parser.parse_args()
    raise SystemExit(main(args.hosted, args.download, args.local_split_python))
