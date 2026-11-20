#!/usr/bin/env python3
"""Measure an isolated Linux desktop binary or compare a matched pair of reports."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUTPUT = REPO / "artifacts/rust/performance"
FORMAT = 1


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(directory, paths=None):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*") if paths is None else paths):
        if path.is_file() and path.suffix not in (".pdb", ".xml"):
            digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
            digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def system_identity():
    cpu = next((row.split(":", 1)[1].strip() for row in Path("/proc/cpuinfo").read_text().splitlines()
                if row.startswith(("model name", "Hardware"))), "")
    identity_file = Path("/etc/machine-id")
    if not identity_file.is_file():
        identity_file = Path("/proc/sys/kernel/random/boot_id")
    host_key = hashlib.sha256(b"immich-folder-watch-rw02-local-pair\0" + identity_file.read_bytes()).hexdigest()
    return {"architecture": platform.machine(), "kernel": platform.release(), "cpu": cpu,
            "cpu_affinity": sorted(os.sched_getaffinity(0)), "clock_ticks": os.sysconf("SC_CLK_TCK"),
            "scratch_filesystem": subprocess.check_output(["stat", "-f", "-c", "%T", "/tmp"], text=True).strip(),
            "host_match_key": host_key}


def namespace(work, app, runtime):
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--ro-bind", "/usr", "/usr", "--dev", "/dev", "--proc", "/proc",
               "--tmpfs", "/tmp", "--dir", "/etc", "--bind", str(work), "/qa",
               "--ro-bind", str(HERE), "/driver", "--ro-bind", str(app), "/app"]
    for directory in ("/lib", "/lib64", "/bin"):
        path = Path(directory)
        if path.is_symlink():
            command += ["--symlink", os.readlink(path), directory]
        elif path.is_dir():
            command += ["--ro-bind", directory, directory]
    for path in ("/etc/fonts", "/etc/ld.so.cache", "/etc/localtime"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    private_etc = work / "etc"
    private_etc.mkdir()
    (private_etc / "passwd").write_text(f"benchmark:x:{os.getuid()}:{os.getgid()}:Synthetic user:/tmp/home:/bin/false\n")
    (private_etc / "group").write_text(f"benchmark:x:{os.getgid()}:\n")
    (private_etc / "machine-id").write_text("12a12a12a12a12a12a12a12a12a12a12\n")
    for path in private_etc.iterdir():
        command += ["--ro-bind", str(path), "/etc/" + path.name]
    if runtime:
        command += ["--dir", "/runtime"]
        for name in ("dotnet", "host", "shared"):
            command += ["--ro-bind", str(runtime / name), "/runtime/" + name]
        sdk_version = json.loads((REPO / "global.json").read_text())["sdk"]["version"]
        compiler = runtime / "sdk" / sdk_version / "Roslyn/bincore"
        references = [path for path in (runtime / "packs/Microsoft.NETCore.App.Ref").glob("*/ref/net10.0")
                      if (runtime / "shared/Microsoft.NETCore.App" / path.parents[1].name).is_dir()]
        if not (compiler / "csc.dll").is_file() or len(references) != 1:
            raise ValueError("Use the pinned SDK with a matching .NET 10 reference/runtime pack")
        command += ["--ro-bind", str(compiler), "/compiler", "--ro-bind", str(references[0]), "/reference-assemblies"]
    environment = {"HOME": "/tmp/home", "DISPLAY": ":93", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/session-bus",
                   "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin", "LIBGL_ALWAYS_SOFTWARE": "1",
                   "PYTHONDONTWRITEBYTECODE": "1", "DOTNET_ROOT": "/runtime",
                   "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    for key, value in environment.items():
        command += ["--setenv", key, value]
    return command + ["--chdir", "/qa", "--", "/usr/bin/python3", "/driver/session.py"]


def percentile(values, fraction):
    values = sorted(values)
    return values[math.ceil(len(values) * fraction) - 1]


def summarize(trials):
    summary = {"startup_ms": statistics.median(row["idle"]["startup_ms"] for row in trials)}
    for mode in ("shown", "hidden"):
        for metric in ("cpu_percent_one_core", "median_rss_mib", "damage_rectangles_per_second"):
            summary[f"{mode}_{metric}"] = statistics.median(row["idle"][mode][metric] for row in trials)
        if all("paint" in row for row in trials):
            summary[f"{mode}_render_passes_per_second"] = statistics.median(
                row["paint"][mode]["render_passes_per_second"] for row in trials)
    for kind in ("show", "close"):
        values = [[s["latency_ms"] for s in row["scan"]["input_samples"] if s["input"] == kind] for row in trials]
        if all(values):
            summary[f"scan_{kind}_p95_ms"] = statistics.median(percentile(run, .95) for run in values)
    return summary


def budgets(summary, seconds):
    limits = {}
    for key, value in summary.items():
        if "cpu_percent" in key:
            headroom = max(value * .20, 1.0)
        elif "rss_mib" in key:
            headroom = max(value * .10, 4.0)
        elif "rectangles" in key or "render_passes" in key:
            headroom = 1 / seconds
        else:
            headroom = max(value * .20, 10.0)
        limits[key] = math.ceil((value + headroom) * 1000) / 1000
    return limits


def eligible(report):
    if report["workload"]["files"] != 100_000 or report["workload"]["trials"] < 3:
        return False
    if report["workload"]["seconds"] < 10:
        return False
    for row in report["trials"]:
        for kind in ("close", "show"):
            if sum(s["input"] == kind for s in row["scan"]["input_samples"]) < 5:
                return False
    return True


def measure(args):
    entry = args.entry.resolve(strict=True)
    # Mount a build output directory. Do not expose source checkouts or home profiles.
    if not entry.is_file() or not entry.is_relative_to(REPO) or entry.parent == REPO or entry.parent.is_relative_to(REPO / ".git"):
        raise ValueError("Choose a built entrypoint in a project build directory")
    runtime = args.runtime_root.resolve(strict=True) if args.runtime_root else None
    if runtime and not ((runtime / "dotnet").is_file() and (runtime / "host/fxr").is_dir()):
        raise ValueError("Invalid .NET runtime root")
    if runtime and entry.suffix != ".dll":
        raise ValueError("Pass the Linux managed GUI DLL when supplying --runtime-root")
    if not shutil.which("bwrap"):
        raise RuntimeError("Linux bubblewrap is required")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.name):
        raise ValueError("Use a filename label for --name")
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("Use a full lower-case Git revision")
    if not 1 <= args.files <= 100_000 or not 1 <= args.trials <= 20 or not 1 <= args.seconds <= 300:
        raise ValueError("Use 1..100000 files, 1..20 trials and 1..300 seconds")
    if not 1 <= args.passes <= 10 or not args.start_marker.strip() or not args.finish_marker.strip():
        raise ValueError("Provide valid reconciliation markers and a positive pass count")
    result = OUTPUT / f"{args.name}.json"
    if result.exists():
        raise FileExistsError(f"Choose a fresh label; {result} already exists")
    workload = {"files": args.files, "trials": args.trials, "seconds": args.seconds,
                "profile": "offline-uploadNew-empty-idle-and-prefilled-scan",
                "display": "private-X11-1280x900x24-software"}
    harness_files = [*HERE.glob("*.py"), HERE / "StartupHook.cs"]
    harness_digest = fingerprint(HERE, harness_files)
    application_digest = fingerprint(entry.parent)
    entry_digest = sha256(entry)
    with tempfile.TemporaryDirectory(prefix="ifw-rust-perf-", dir="/tmp") as directory:
        work = Path(directory)
        spec = dict(workload, entry=entry.name, managed=runtime is not None, passes=args.passes,
                    measure_render_passes=bool(args.frame_counter or runtime),
                    start_marker=args.start_marker, finish_marker=args.finish_marker,
                    outer_namespaces={k: os.readlink(f"/proc/self/ns/{k}") for k in ("net", "mnt", "pid", "ipc", "user")})
        (work / "spec.json").write_text(json.dumps(spec))
        subprocess.run(namespace(work, entry.parent, runtime), check=True,
                       timeout=60 + args.trials * (600 + 4 * args.seconds))
        observed = json.loads((work / "results.json").read_text())
    if fingerprint(HERE, harness_files) != harness_digest:
        raise RuntimeError("Benchmark source changed during the run")
    if fingerprint(entry.parent) != application_digest:
        raise RuntimeError("Application build changed during the run")
    report = dict(observed, format=FORMAT, system=system_identity(), workload=workload,
                  harness_sha256=harness_digest, revision=args.revision, binary=entry.name,
                  server_sha256=sha256(Path(shutil.which(observed["xserver"]))),
                  build_output_sha256=application_digest, binary_sha256=entry_digest,
                  runtime_versions=sorted(p.name for p in (runtime / "shared/Microsoft.NETCore.App").iterdir()) if runtime else [],
                  scan_markers={"start": args.start_marker, "finish": args.finish_marker, "passes": args.passes})
    report["summary"] = summarize(report["trials"])
    report["eligible"] = eligible(report)
    if runtime and report["eligible"]:
        report["budget"] = budgets(report["summary"], args.seconds)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with result.open("x") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(f"{result} (eligible={report['eligible']})")
    print(json.dumps(report["summary"], indent=2))


def compare(args):
    baseline, candidate = [json.loads(path.read_text()) for path in (args.baseline, args.candidate)]
    if not baseline.get("budget") or not candidate["eligible"] or candidate["runtime_versions"]:
        raise ValueError("An eligible .NET reference and native candidate are required")
    for key in ("format", "system", "workload", "xserver", "xdamage", "server_sha256", "harness_sha256"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"Different {key}; run the reference and candidate in the same environment")
    failed = False
    for key, maximum in baseline["budget"].items():
        if key not in candidate["summary"]:
            print(f"{key}: missing native instrumentation")
            failed = True
            continue
        value = candidate["summary"][key]
        passed = value <= maximum
        print(f"{key}: {value:.3f} / {maximum:.3f} {'PASS' if passed else 'FAIL'}")
        failed |= not passed
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("measure")
    run.add_argument("--name", required=True)
    run.add_argument("--entry", type=Path, required=True)
    run.add_argument("--runtime-root", type=Path, help="Runtime directory for the C# reference only")
    run.add_argument("--revision", required=True)
    run.add_argument("--files", type=int, default=100_000)
    run.add_argument("--trials", type=int, default=3)
    run.add_argument("--seconds", type=int, default=15)
    run.add_argument("--passes", type=int, default=2)
    run.add_argument("--frame-counter", action="store_true", help="Count native render passes in a separate run")
    run.add_argument("--start-marker", default="Folder watcher started with 1 source(s).")
    run.add_argument("--finish-marker", default="Persistent reconciliation for uploadNew queued 0 changed file(s)")
    run.set_defaults(action=measure)
    diff = commands.add_parser("compare")
    diff.add_argument("baseline", type=Path)
    diff.add_argument("candidate", type=Path)
    diff.set_defaults(action=compare)
    args = parser.parse_args()
    return args.action(args)


if __name__ == "__main__":
    sys.exit(main())
