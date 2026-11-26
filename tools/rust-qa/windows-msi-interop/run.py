"""Run one argument-free cross-version activation with a freshly installed WPF executable."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from common import AREA, HERE, INSTALLED, ROOT, TARGETS, inputs, launcher, module, read, sha, verify_source_inputs, write
from msi_subject import build


def run(target, package, *, wpf_primary=False):
    launch = launcher()
    release = module("ifw_shipping_package", INSTALLED / "run.py")
    if (not launch.recorder.hosted() or release.native_target() != TARGETS[target][0]
            or os.environ.get("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"
            or os.environ.get("GITHUB_REF") != "refs/heads/rewrite/rust"
            or release.git("rev-parse", release.RELEASE["tag"] + "^{commit}").decode().strip() != release.RELEASE["commit"]):
        raise ValueError("Use the matching disposable native rewrite runner and original release tag")
    out = (AREA / "reverse" if wpf_primary else AREA) / target
    out.mkdir(parents=True)
    record = dict(target=target, status="incomplete", revision=os.environ["GITHUB_SHA"],
                  run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"], inputs=inputs(wpf_primary))
    if wpf_primary:
        record["direction"] = "wpf-primary"
        verify_source_inputs(record["inputs"], record["revision"], True)
    try:
        ordinary = {}
        with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"], prefix="ifw-msi-") as raw:
            work = Path(raw).resolve()
            with launch.native_subject(target, out, ordinary, subject="retained") as (api, _, gui, inventory, _):
                build(target, work, out, ordinary, gui, inventory, wpf_primary=wpf_primary)
            asset = release.prepare_package(TARGETS[target][0], work, package)
            media = work / "wpf-media"
            media.mkdir()
            api.ensure_no_primary(launch.recorder.sid())
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as offline:
                offline.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                offline.bind(("127.0.0.1", 0))
                endpoint = "http://127.0.0.1:" + str(offline.getsockname()[1])
                env = dict(os.environ, HTTP_PROXY=endpoint, HTTPS_PROXY=endpoint, ALL_PROXY=endpoint,
                           NO_PROXY="127.0.0.1,localhost,::1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
                with launch.recorder.wpf_profile(media, endpoint) as profile:
                    marker, = tuple(profile.glob(".rw02-owned-*"))
                    record["wpfProfile"] = dict(configSha256=sha(profile / "config.yaml"), endpoint=endpoint, media=str(media))
                    write(out / "result.json", record)
                    args = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(HERE / "install.ps1"),
                            "-Package", str(asset), "-Evidence", str(out), "-Work", str(work), "-Target", target,
                            "-Profile", str(profile), "-Marker", str(marker), "-ConfigSha256", record["wpfProfile"]["configSha256"],
                            "-Python", sys.executable]
                    if wpf_primary:
                        args.append("-WpfPrimary")
                    invocation = subprocess.run(args, cwd=ROOT, env=env)
                    if wpf_primary and invocation.returncode and (out / "installed.json").is_file():
                        # Preserve the owned KnownFolder if the supervisor could not verify
                        # that the installed primary has gone away on this disposable VM.
                        outcome = out / "msi-result.json"
                        transaction = read(outcome) if outcome.is_file() else {}
                        if (transaction.get("cleanup", {}).get("msiRemoved") is not True
                                or transaction.get("checkpoints", {}).get("after", {}).get("appProcesses") != 0):
                            raise launch.recorder.CleanupUnconfirmed("Cannot confirm the installed WPF primary was reaped")
                    if invocation.returncode == 0:
                        record["msiTransactions"] = {
                            name: dict(sha256=sha(out / name), nativePath=str(out / name))
                            for name in ("install.log", "uninstall.log")
                        }
                if profile.exists():
                    raise ValueError("The owned WPF profile remained after cleanup")
                record["wpfProfile"]["removed"] = True
                invocation.check_returncode()
        if work.exists() or read(out / "msi-result.json")["status"] != "passed":
            raise ValueError("Missing scratch or installed product cleanup")
        record["scratchRemoved"] = True
        from msi_evidence import verify
        record["checks"] = verify(out, record)
        record["files"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "result.json"}
        record["status"] = "observed"
    finally:
        write(out / "result.json", record)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("target", choices=TARGETS)
    args.add_argument("--package", type=Path)
    args.add_argument("--wpf-primary", action="store_true", help="Start the installed WPF application first in a separate fresh trial")
    opts = args.parse_args()
    run(opts.target, opts.package, wpf_primary=opts.wpf_primary)
