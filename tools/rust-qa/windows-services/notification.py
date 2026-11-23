"""Reobserve a single silent Shell notification late in the original disposable Windows job."""
import argparse
import hashlib
import json
import os
import sys

from service_sources import HERE, ROOT, service_files, verify_checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    targets = {"X64": "x86_64-pc-windows-msvc", "ARM64": "aarch64-pc-windows-msvc"}
    parser.add_argument("target", choices=list(targets.values()))
    target = parser.parse_args().target
    if (sys.platform != "win32" or os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_OS") != "Windows"
            or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted" or os.getenv("GITHUB_REF") != "refs/heads/rewrite/rust"
            or targets.get(os.getenv("RUNNER_ARCH")) != target or os.getenv("GITHUB_REPOSITORY") != "VoltKraft/immich-folder-watch"):
        parser.error("Use the native disposable rewrite runner")
    out = ROOT / "artifacts/rust/windows-services" / ("notification-" + target)
    out.mkdir(exist_ok=False)
    result = dict(status="failed", target=target, head=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
                  attempt=os.environ["GITHUB_RUN_ATTEMPT"], checkoutVerified=False)
    try:
        result["observerInputs"] = verify_checkout(ROOT, service_files(), result["head"], HERE)
        result["checkoutVerified"] = True
        from activation import paths
        from notification_probe import READ, bind_build, measure
        exe, original = paths(target)
        bind_build(target, exe, original, result)
        try:
            result["status"] = measure(target, exe, original, out, result)
        finally:
            if (out / "native.txt").is_file():
                result["native"] = READ(out / "native.txt")
    except Exception as exc:
        causes = []
        while exc is not None:
            causes.append(dict(type=type(exc).__name__, message=str(exc)))
            exc = exc.__cause__ or exc.__context__
        result["error"], result["causes"] = causes[0], causes[1:]
        result["status"] = "failed"
    finally:
        result["evidenceFiles"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["status"], result.get("error") or result.get("reason") or "")
    return {"passed": 0, "unavailable": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
