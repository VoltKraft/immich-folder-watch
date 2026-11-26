"""Install the original release, return a live Rust SQLite backup, then uninstall."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

from shared import AREA, HERE, INSTALLED, ROOT, TARGETS, configuration, module, observer_sources, read, require, sha, write
from common import launcher
from private_desktop import ARM, MODE


def exclusive_port():
    stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        stream.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        stream.bind(("127.0.0.1", 0))
        return stream
    except BaseException:
        stream.close()
        raise


@contextmanager
def scratch(recorder):
    work = Path(tempfile.mkdtemp(prefix="ifw-msi-", dir=os.environ["RUNNER_TEMP"])).resolve()
    try:
        yield work
    except BaseException as exc:
        if not recorder.CleanupUnconfirmed.in_chain(exc):
            shutil.rmtree(work)
        raise
    else:
        shutil.rmtree(work)


def run(target, package, build, private=False):
    from backup_build import stage_backup
    launch = launcher()
    release = module("ifw_upload_release", INSTALLED / "run.py")
    require(launch.recorder.hosted() and release.native_target() == TARGETS[target][0]
            and os.getenv("GITHUB_REPOSITORY") == "VoltKraft/immich-folder-watch"
            and os.getenv("GITHUB_REF") == "refs/heads/rewrite/rust"
            and release.git("rev-parse", release.RELEASE["tag"] + "^{commit}").decode().strip() == release.RELEASE["commit"],
            "Use the matching disposable native rewrite runner and original release tag")
    require(not private or target == ARM and os.getenv("TRIAL_VARIANT") == "arm64-private-input",
            "The separate private input trial requires its own native ARM64 runner")
    out = AREA / "upload" / target
    out.mkdir(parents=True)
    revision = os.environ["GITHUB_SHA"]
    record = dict(format="ifw-installed-wpf-upload-v1", status="incomplete", target=target, revision=revision,
                  run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    if private:
        record["desktopMode"] = MODE
    try:
        record["observerSources"] = observer_sources(out, revision, freeze=True)
        with scratch(launch.recorder) as work:
            record["backupBuild"] = stage_backup(build, work, out, target, revision)
            asset = release.prepare_package(TARGETS[target][0], work, package)
            media = work / "wpf-media"
            media.mkdir()
            launch.recorder.Win32().ensure_no_primary(launch.recorder.sid())
            with exclusive_port() as proxy:
                blocked = "http://127.0.0.1:" + str(proxy.getsockname()[1])
                with exclusive_port() as reserved:
                    endpoint = "http://127.0.0.1:" + str(reserved.getsockname()[1])
                # The child must bind this exact port exclusively before it can launch either WPF.
                env = dict(os.environ, HTTP_PROXY=blocked, HTTPS_PROXY=blocked, ALL_PROXY=blocked,
                           NO_PROXY="127.0.0.1,localhost,::1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
                with launch.recorder.wpf_profile(media, blocked) as profile:
                    marker, = profile.glob(".rw02-owned-*")
                    config = profile / "config.yaml"
                    config.write_text(configuration(media, endpoint), encoding="utf-8")
                    (out / "shipping-upload.yaml").write_bytes(config.read_bytes())
                    record["profile"] = dict(configSha256=sha(config), endpoint=endpoint, proxy=blocked,
                                             media=str(media), directory=str(profile), marker=marker.name)
                    write(out / "result.json", record)
                    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", HERE / "install.ps1", "-Package", asset,
                           "-Evidence", out, "-Work", work, "-Target", target, "-Profile", profile, "-Marker", marker,
                           "-ConfigSha256", sha(config), "-Python", sys.executable, "-Upload"]
                    result = subprocess.run(cmd, env=env, cwd=ROOT)
                    if result.returncode and (out / "installed.json").is_file():
                        transaction = read(out / "msi-result.json") if (out / "msi-result.json").is_file() else {}
                        if (transaction.get("cleanup", {}).get("msiRemoved") is not True
                                or transaction.get("checkpoints", {}).get("after", {}).get("appProcesses") != 0):
                            raise launch.recorder.CleanupUnconfirmed("Owned installed WPF cleanup could not be confirmed")
                record["profileRemoved"] = not profile.exists()
        record["scratchRemoved"] = not work.exists()
        record["msiTransactions"] = {name: dict(nativePath=str(out / name), sha256=sha(out / name))
                                     for name in ("install.log", "uninstall.log") if (out / name).is_file()}
        result.check_returncode()
        from upload.readback import verify
        record["checks"] = verify(out, record, False)
        record["status"] = "observed"
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record["files"] = release.evidence_hashes(out)
        record["files"].pop("result.json", None)
        write(out / "result.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--rust-backup", required=True, type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--private-input-desktop", action="store_true")
    args = parser.parse_args()
    run(args.target, args.package, args.rust_backup, args.private_input_desktop)
