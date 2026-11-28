"""Replay a complete installed WPF primary trial or just its evidence saved before requesting Quit."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import INSTALLED, TARGETS, read, sha, verify_source_inputs
from msi_evidence import payload_details, verify, verify_build, verify_transactions
from reverse.evidence import verify_prequit
import private_desktop


def replay(out, before_quit, expect_private=False):
    report = read(out / "result.json")
    if (report.get("desktopMode") not in (None, private_desktop.MODE)
            or expect_private != (report.get("desktopMode") == private_desktop.MODE)):
        raise ValueError("The requested and recorded activation desktop modes differ")
    if report.get("direction") != "wpf-primary":
        raise ValueError("Expected a separate installed WPF primary trial")
    verify_source_inputs(report["inputs"], report["revision"], True)
    if before_quit:
        build = verify_build(out, report)
        installed = read(out / "installed.json")
        target, machine = TARGETS[report["target"]]
        release = read(INSTALLED / "release.json")
        payload = read(out / "payload-installed.json")
        if (installed["format"] != "ifw-installed-msi-interop-v1" or installed["target"] != report["target"]
                or installed["sourceCommit"] != report["revision"] or str(installed["workflowRun"]) != report["run"]
                or installed["releaseCommit"] != release["commit"] or installed["package"] != release["assets"][target]
                or installed["exeSha256"] != payload_details(payload, target) or installed["payloadSha256"] != payload["sha256"]
                or installed["peMachine"]["ImmichFolderWatch.exe"] != machine or not installed["state"]["installDirectory"]
                or installed["state"]["appProcesses"] != 0 or installed["state"]["packageCode"] != installed["identity"]["packageCode"]
                or installed["configSha256"] != report["wpfProfile"]["configSha256"]):
            raise ValueError("The executable or installed package differs from the release and original runner")
        tx = installed["installTransaction"]
        verify_transactions(out, {"install.log":tx}, [tx["operation"]], installed["identity"], target, install_only=True)
        return verify_prequit(out, report, build, installed)
    files = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "result.json"}
    if report["status"] != "observed" or report["files"] != files or report["checks"] != verify(out, report):
        raise ValueError("The full original MSI, window, worker or cleanup evidence changed")
    return report["checks"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--before-quit", action="store_true", help="Replay the activation saved before the menu and cleanup")
    parser.add_argument("--private-input-desktop", action="store_true", help="Require the separate private ARM64 observation")
    opts = parser.parse_args()
    print(json.dumps(replay(opts.output, opts.before_quit, opts.private_input_desktop), indent=2))
