"""Check per-user file output and query real native logging services using synthetic profiles."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CRATE = ROOT / "rust/crates/desktop-platform-log"
NAMESPACES = ("mnt", "pid", "user", "ipc", "net")
LEVELS = ("Trace", "Debug", "Information", "Warning", "Error", "Critical")
PRIORITIES = (7, 7, 6, 4, 3, 2)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_file(binary, profile, nonce):
    timestamp = "2000-01-02 03:04:05.006 +00:00"
    expected = "".join(f"{timestamp} [{level}] Desktop.Fixture: Grüße 二 {nonce} {i}\nFortsetzung{os.linesep}"
                       for i, level in enumerate(LEVELS)).encode()
    log = profile / "synthetic.log"
    with log.open("xb") as seed:
        seed.write(b"previous session\n")
    for count in (1, 2):
        subprocess.run([binary, "file", nonce], cwd=profile, check=True, timeout=8)
        if log.read_bytes() != b"previous session\n" + count * expected:
            raise RuntimeError("Appending or reopening changed file records")
    return {"records": 12, "previousSessionPreserved": True, "sha256": digest(log)}


def inside():
    profile = Path("/qa")
    nonce = (profile / ".ifw-native-log").read_text().strip()
    outer = json.loads((profile / "namespaces.json").read_text())
    if os.getuid() != 0 or any(os.readlink("/proc/self/ns/" + k) == outer[k] for k in NAMESPACES):
        raise RuntimeError("Private journal requires isolated Linux namespaces")
    cgroup = Path("/sys/fs/cgroup")
    if cgroup.exists() and (os.readlink("/proc/self/ns/cgroup") == outer["cgroup"]
                            or not os.statvfs(cgroup).f_flag & os.ST_RDONLY):
        raise RuntimeError("The private journal requires a read-only cgroup view in its own namespace")
    for directory in ("/run/systemd/journal", "/run/log/journal", "/etc/systemd", "/var/log", "/tmp/home"):
        Path(directory).mkdir(parents=True, exist_ok=True)
    Path("/etc/machine-id").write_text(nonce + "\n")
    Path("/etc/passwd").write_text("root:x:0:0:Fixture:/tmp/home:/bin/false\n")
    Path("/etc/group").write_text("root:x:0:\nsystemd-journal:x:190:\n")
    Path("/etc/systemd/journald.conf").write_text(
        "[Journal]\nStorage=volatile\nReadKMsg=no\nForwardToSyslog=no\nForwardToKMsg=no\n"
        "ForwardToConsole=no\nForwardToWall=no\nRateLimitIntervalSec=0\nMaxLevelStore=debug\n")
    private_journal = Path("/run/log/journal") / nonce
    identifier = "ifw-qa-" + nonce
    with (profile / "daemon.log").open("wb") as log:
        daemon = subprocess.Popen(["/usr/lib/systemd/systemd-journald"], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 8
            while not Path("/run/systemd/journal/stdout").is_socket():
                if daemon.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("The private journald stream did not become available")
                time.sleep(.035)
            subprocess.run(["setpriv", "--no-new-privs", "--inh-caps=-all", "--ambient-caps=-all",
                            "systemd-cat", "--identifier", identifier, "--level-prefix=yes",
                            "/subject", "journal", nonce], cwd=profile, env=dict(os.environ, IFW_QA_LOG_IDENTITY="1"),
                           check=True, timeout=8)
            identity = dict(line.split() for line in (profile / "journal-process").read_text().splitlines())
            if int(identity["CapEff:"], 16) or identity["NoNewPrivs:"] != "1":
                raise RuntimeError("The journal writer must run without effective capabilities and with no new privileges")
            deadline = time.monotonic() + 8
            rows = []
            while daemon.poll() is None and time.monotonic() < deadline:
                if private_journal.is_dir():
                    data = subprocess.run(["journalctl", "--directory", private_journal, "--output=json",
                                           "--no-pager", "--quiet", f"SYSLOG_IDENTIFIER={identifier}"],
                                          stdout=subprocess.PIPE, stderr=log, check=True, timeout=5)
                    rows = [json.loads(line) for line in data.stdout.splitlines()]
                    if len(rows) >= len(LEVELS):
                        break
                time.sleep(.05)
            observed = [(int(r["PRIORITY"]), r["_TRANSPORT"], r["MESSAGE"]) for r in rows]
            expected = [(priority, "stdout", f"Desktop.Fixture[{i + 100}] Grüße 二 {nonce} {i} Fortsetzung")
                        for i, priority in enumerate(PRIORITIES)]
            if observed != expected:
                raise RuntimeError(f"Expected six ordered native journal records, observed {observed!r}")
            write_json(profile / "journal.json", {
                "systemd": subprocess.check_output(["journalctl", "--version"], text=True).splitlines()[0],
                "machineIdMatched": all(r["_MACHINE_ID"] == nonce for r in rows),
                "readOnlyCgroupView": cgroup.is_dir(),
                "processEffectiveCapabilities": identity["CapEff:"], "noNewPrivileges": True,
                "records": [{"priority": p, "transport": transport, "message": msg} for p, transport, msg in observed]})
            if not all(r["_MACHINE_ID"] == nonce for r in rows):
                raise RuntimeError("The records were not attributed to the private machine")
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=6)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=3)


def current_cgroup():
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        if line.startswith("0::/"):
            member = Path(line[3:])
            if ".." in member.parts:
                return None
            directory = Path("/sys/fs/cgroup") / member.relative_to("/")
            if (directory / "cgroup.controllers").is_file():
                return directory
    return None


def check_journal(binary, profile, output, system_root=Path("/")):
    groups = current_cgroup()
    spaces = (*NAMESPACES, "cgroup") if groups else NAMESPACES
    write_json(profile / "namespaces.json", {k: os.readlink("/proc/self/ns/" + k) for k in spaces})
    cmd = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--uid", "0", "--gid", "0",
           "--ro-bind", str(system_root / "usr"), "/usr", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
           "--tmpfs", "/etc", "--tmpfs", "/run", "--tmpfs", "/var", "--bind", str(profile), "/qa",
           "--ro-bind", str(binary), "/subject", "--ro-bind", str(Path(__file__).resolve()), "/tools/rust-qa/platform-logs/observe.py",
           "--setenv", "HOME", "/tmp/home", "--setenv", "PATH", "/usr/bin:/usr/sbin", "--setenv", "LANG", "C.UTF-8"]
    # systemd 255 needs the cgroup filesystem type to resolve PID 1 at initialization.
    # The only exposed subtree is the launching process's own membership, mounted read-only.
    if groups:
        cmd.extend(["--ro-bind", str(groups), "/sys/fs/cgroup"])
    for name in ("bin", "sbin", "lib", "lib64"):
        path = system_root / name
        if path.is_symlink():
            cmd.extend(["--symlink", os.readlink(path), "/" + name])
        elif path.is_dir():
            cmd.extend(["--ro-bind", str(path), "/" + name])
    try:
        subprocess.run([*cmd, "/usr/bin/python3", "-B", "/tools/rust-qa/platform-logs/observe.py", "--inside"],
                       check=True, timeout=35)
    finally:
        if (profile / "daemon.log").is_file():
            shutil.copyfile(profile / "daemon.log", output / "daemon.log")
    return json.loads((profile / "journal.json").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal-system-root", type=Path, help="use an extracted native Linux distribution for the private journal")
    args = parser.parse_args()
    if args.journal_system_root and sys.platform != "linux":
        parser.error("The journal userspace option requires native Linux")
    if os.name == "nt" and any(os.getenv(k) != v for k, v in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "VoltKraft/immich-folder-watch", "GITHUB_REF": "refs/heads/rewrite/rust"}.items()):
        parser.error("Windows Event Log assessment requires a disposable native rewrite job")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "artifacts/rust"):
        parser.error("Select a fresh result under artifacts/rust")
    output.mkdir(parents=True, exist_ok=False)
    toolchain = ROOT / "artifacts/rust/toolchain/bin"
    target_dir = ROOT / "artifacts/rust/platform-log-build"
    env = dict(os.environ, PATH=str(toolchain) + os.pathsep + os.environ["PATH"],
               CARGO_HOME=str(ROOT / "artifacts/rust/cargo-home"), CARGO_TARGET_DIR=str(target_dir))
    compiler = subprocess.check_output(["rustc", "-vV"], env=env, text=True)
    pin = json.loads((ROOT / "rust/toolchain-inputs.json").read_text())
    if args.target not in pin["targets"] or f"host: {args.target}\n" not in compiler:
        parser.error("The compiler host must match the native target")
    report = {"target": args.target, "system": platform.platform(), "passed": False,
              "git": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(
                  [*HERE.glob("*.py"), *HERE.glob("*.ps1"), *HERE.glob("*.mc"), *HERE.glob("*.cs*"), *CRATE.rglob("*.rs"),
                   CRATE / "Cargo.toml", ROOT / "rust/Cargo.lock"])}}
    try:
        subprocess.run([sys.executable, ROOT / "tools/rust-qa/check-toolchain.py", args.target],
                       check=True, env=env, cwd=ROOT, timeout=15)
        subprocess.run(["cargo", "build", "--frozen", "--release", "--manifest-path", "rust/Cargo.toml",
                        "-p", "desktop-platform-log", "--example", "native_record"], cwd=ROOT, env=env, check=True,
                       timeout=120)
        binary = target_dir / "release/examples" / ("native_record.exe" if os.name == "nt" else "native_record")
        report["binarySha256"] = digest(binary)
        nonce = secrets.token_hex(16)
        with tempfile.TemporaryDirectory(prefix="ifw-logs-", dir=os.getenv("RUNNER_TEMP") if os.name == "nt" else None) as temp:
            from reference import compare
            profile = Path(temp)
            (profile / ".ifw-native-log").write_text(nonce + "\n", encoding="ascii")
            report["file"] = check_file(binary, profile, nonce)
            report["dotnetReference"] = compare(ROOT, HERE, profile, binary, nonce)
            if os.name == "nt":
                subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-File", HERE / "observe-event.ps1",
                                "-ProfilePath", profile, "-Binary", binary, "-OutputFile", output / "event.json"],
                               cwd=profile, env=env, check=True, timeout=75)
                report["eventLog"] = json.loads((output / "event.json").read_text(encoding="utf-8-sig"))
                if not report["eventLog"]["passed"]:
                    raise RuntimeError("Windows did not verify the messages and private log removal")
            else:
                system_root = (args.journal_system_root or Path("/")).resolve(strict=True)
                report["journal"] = check_journal(binary, profile, output, system_root)
                report["journal"]["daemonSha256"] = digest(system_root / "usr/lib/systemd/systemd-journald")
                report["journal"]["distributionUserspace"] = [
                    line for line in (system_root / "usr/lib/os-release").read_text().splitlines()
                    if line.startswith(("ID=", "VERSION_ID=", "BUILD_ID="))]
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        write_json(output / "result.json", report)


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        inside()
    else:
        main()
