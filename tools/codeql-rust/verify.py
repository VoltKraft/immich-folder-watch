"""Bind Rust CodeQL results to the selected Git sources, target cfg and security suite."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
CFG_SKIPPED = {
    "x86_64-unknown-linux-gnu": {"crates/desktop-platform-log/src/windows.rs", "crates/safe-fs/src/windows.rs"},
    "x86_64-pc-windows-msvc": {"crates/safe-fs/src/linux.rs"},
}
# The bundle's resolved security-extended suite. Hash its sorted 20 alert IDs followed
# by the sorted 40 relative BQRS names, each with a trailing LF.
SUITE_SHA256 = "b60a8777ab8b6076087574aa3181ec5eca9248018fd1b122415ce02e2572ec31"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify(work, revision, target, bundle_digest):
    out = work / "results"
    tree = git("rev-parse", revision + ":rust").decode().strip()
    tracked = {name for name in git("ls-tree", "-r", "-z", "--name-only", tree).decode().split("\0")
               if name.endswith(".rs")}
    if not tracked or not CFG_SKIPPED[target] <= tracked:
        raise ValueError("The Rust tree is missing the reviewed target-specific sources")
    with (out / "coverage.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    coverage = {row["path"]: row["status"] for row in rows}
    expected = {name: "cfg-skipped" if name in CFG_SKIPPED[target] else "active" for name in tracked}
    if len(rows) != len(tracked) or coverage != expected:
        raise ValueError(f"Rust extraction differs from the expected {target} semantic coverage. See coverage.csv")
    hashes = {}
    with ZipFile(work / "db/src.zip") as archive:
        prefix = (work / "source").as_posix().lstrip("/") + "/"
        for name in sorted(tracked):
            extracted = archive.read(prefix + name)
            if extracted != git("cat-file", "blob", tree + ":" + name):
                raise ValueError(f"CodeQL archived different source bytes for {name}")
            hashes[name] = sha256(extracted)

    sarif = (out / "results.sarif").read_bytes()
    document = json.loads(sarif)
    run, = document["runs"]
    invocation, = run["invocations"]
    driver = run["tool"]["driver"]
    packs = {ext["name"]: ext["semanticVersion"].partition("+")[0] for ext in run["tool"]["extensions"]}
    if (document["version"] != "2.1.0" or driver["name"] != "CodeQL" or driver["semanticVersion"] != "2.27.5"
            or packs.get("codeql/rust-queries") != "0.1.47" or packs.get("codeql/rust-all") != "0.2.26"
            or invocation["executionSuccessful"] is not True):
        raise ValueError("The expected Rust CodeQL packs did not complete the analysis")
    rules = sorted(rule["id"] for rule in driver["rules"] if "security" in rule["properties"].get("tags", []))
    queries = sorted(path.relative_to(work / "db/results").as_posix()
                     for path in (work / "db/results/codeql/rust-queries").rglob("*.bqrs"))
    if sha256(("\n".join(rules + queries) + "\n").encode()) != SUITE_SHA256:
        raise ValueError("The pinned Rust security-extended suite did not produce all expected queries and rules")
    notifications = invocation["toolExecutionNotifications"]
    extracted_files = {
        unquote(loc["physicalLocation"]["artifactLocation"]["uri"]) for notice in notifications
        if notice.get("descriptor", {}).get("id") == "rust/diagnostics/successfully-extracted-files"
        for loc in notice["locations"]
    }
    metrics = {m["ruleId"]: m["value"] for m in run["properties"]["metricResults"]}
    if (extracted_files != tracked or metrics.get("rust/summary/number-of-successfully-extracted-files") != len(tracked)
            or metrics.get("rust/summary/number-of-files-extracted-with-errors") != 0
            or metrics.get("rust/summary/lines-of-user-code", 0) <= 0):
        raise ValueError("The Rust SARIF extraction diagnostics do not cover the Git source inventory")
    levels = Counter(notice.get("level", "warning") for notice in notifications)
    low_quality = any(n.get("descriptor", {}).get("id") == "rust/diagnostic/database-quality" for n in notifications)
    alerts = Counter(result["ruleId"] for result in run["results"])
    report = {
        "revision": revision, "rustTree": tree, "target": target, "bundleSha256": bundle_digest,
        "cliVersion": driver["semanticVersion"], "packs": packs, "analysisCompleted": True,
        "sourceSha256": hashes, "semanticCoverage": coverage, "lowDatabaseQuality": low_quality, "executedQueries": queries,
        "securityRules": rules, "suiteSha256": SUITE_SHA256, "alerts": dict(alerts), "notificationLevels": dict(levels),
        "linesOfUserCode": metrics["rust/summary/lines-of-user-code"], "sarifSha256": sha256(sarif),
    }
    (out / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{target}: {len(tracked)} verified sources, {len(queries)} queries, "
          f"{len(rules)} security rules, {alerts.total()} alerts, {levels['error']} analysis errors")
    if alerts or levels["error"] or low_quality:
        raise SystemExit("Review the findings and diagnostics in results.sarif")


if __name__ == "__main__":
    directory, head, cfg, bundle = sys.argv[1:]
    verify(Path(directory).resolve(), head, cfg, bundle)
