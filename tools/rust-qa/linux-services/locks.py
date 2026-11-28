"""Compare the actual .NET read lease and independent consenting writers across two mount views."""

from contextlib import contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys


FIXTURE = b"Synthetic upload fixture\n"


def native_lock(path, primitive, intent, hold):
    # This test writes only the known synthetic fixture, and only after taking an exclusive lock.
    if (os.environ.get("IFW_QA_ISOLATED") != "1" or path.name != "original.jpg" or path.parent.name != "album"
            or not (path.is_relative_to("/tmp/producer/source") or path.is_relative_to("/run/user/0/doc/by-app/org.example.IfwServices"))):
        raise ValueError("Unexpected native lock fixture")
    locking = {"flock": fcntl.flock, "posix": fcntl.lockf}[primitive]
    with path.open("r+b" if intent == "writer" else "rb") as fd:
        try:
            locking(fd, (fcntl.LOCK_EX if intent == "writer" else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except OSError as error:
            print(json.dumps({"acquired": False, "errno": error.errno, "wrote": False}), flush=True)
            return
        wrote = intent == "writer" and not hold
        if wrote:
            if fd.read(256) != FIXTURE:
                raise RuntimeError("Contending writer found unexpected fixture contents")
            fd.seek(0)
            fd.write(FIXTURE)
            fd.flush()
            os.fsync(fd.fileno())
        print(json.dumps({"acquired": True, "wrote": wrote}), flush=True)
        if hold and sys.stdin.readline().strip() != "release":
            raise RuntimeError("Holder lost its release control")


def lock_checks(backing, grant, expected):
    def command(root, *arguments):
        if root == grant:
            # Even the .NET reference and native grant-view contenders cannot see the producer.
            return ["bwrap", "--die-with-parent", "--bind", "/", "/", "--dev", "/dev",
                    "--tmpfs", "/tmp/producer", "--cap-drop", "ALL", "--", *arguments]
        return list(arguments)
    def writer(root, primitive="flock", intent="writer", hold=False):
        return command(root, sys.executable, "/app/locks.py", root / "album/original.jpg",
                       primitive, intent, "hold" if hold else "try")
    def managed(root, hold=False):
        return command(root, "/runtime/dotnet", "/oracle/PortalReference.dll", "hold" if hold else "read", root)
    def read_net(root):
        proc = subprocess.run(managed(root), text=True, capture_output=True, timeout=8)
        lines = proc.stdout.splitlines()
        if proc.returncode not in (0, 20) or len(lines) != 1:
            raise RuntimeError(f"Unexpected shipping reference result: {proc.stderr} {lines}")
        match = re.search(r"^REFUSED errno=(\d+) ", lines[0])
        return {"acquired": proc.returncode == 0 and lines[0].startswith("ACQUIRED runtime="),
                "errno": int(match[1]) if match else None, "detail": lines[0]}
    def attempt(root, primitive="flock"):
        return json.loads(subprocess.check_output(writer(root, primitive), text=True, timeout=8))
    @contextmanager
    def holding(args, managed_holder=False):
        child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, bufsize=1)
        try:
            if not select.select([child.stdout], [], [], 8)[0]:
                raise TimeoutError("No startup response from lock holder")
            line = child.stdout.readline().strip()
            if managed_holder:
                acquired = line.startswith("ACQUIRED runtime=")
                if not acquired and not line.startswith("REFUSED errno="):
                    raise RuntimeError(f"Shipping reference did not answer: {line}")
                observed = {"acquired": acquired, "detail": line}
            else:
                observed = json.loads(line)
                acquired = observed["acquired"]
            yield observed
            if acquired:
                child.stdin.write("release\n")
                child.stdin.flush()
            code = child.wait(timeout=8)
            if code not in (0, 20):
                raise RuntimeError(f"Lock holder failed: {child.stderr.read()}")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=4)
            child.stdout.close()
            child.stderr.close()
            child.stdin.close()

    report = {"dotnet_uncontended_backing": read_net(backing), "dotnet_uncontended_grant": read_net(grant)}
    with holding(managed(backing, True), True) as holder:
        if not holder["acquired"]:
            raise RuntimeError("The positive .NET backing control did not acquire its shared lease")
        report["dotnet_shared_backing"] = {"holder": holder, "backing_flock_writer": attempt(backing),
            "grant_flock_writer": attempt(grant), "backing_posix_writer": attempt(backing, "posix")}
    with holding(writer(backing, intent="writer", hold=True)) as holder:
        if not holder["acquired"]:
            raise RuntimeError("The backing exclusive control failed")
        report["exclusive_backing"] = {"holder": holder, "dotnet_backing": read_net(backing), "dotnet_grant": read_net(grant)}
    with holding(writer(grant, intent="writer", hold=True)) as holder:
        report["exclusive_grant"] = {"holder": holder, "dotnet_backing": read_net(backing), "dotnet_grant": read_net(grant)}
    with holding(managed(grant, True), True) as holder:
        report["dotnet_shared_grant"] = {"holder": holder, "backing_writer": attempt(backing),
            "grant_writer": attempt(grant)}
    for primitive in ("flock", "posix"):
        for root, view in ((backing, "backing"), (grant, "grant")):
            with holding(writer(root, primitive, "reader", True)) as holder:
                report[f"{primitive}_shared_{view}"] = {"holder": holder,
                    "backing_writer": attempt(backing, primitive), "grant_writer": attempt(grant, primitive)}
    report["released_backing_writer"] = attempt(backing)
    report["released_grant_writer"] = attempt(grant)
    report["released_net_backing"] = read_net(backing)
    report["released_net_grant"] = read_net(grant)
    output = Path("/qa/locks.json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    def refused(item, reason):
        return not item["acquired"] and not item.get("wrote") and item.get("errno") == reason
    def assert_state(condition, message):
        if not condition:
            raise RuntimeError(message)
    assert_state(refused(report["dotnet_shared_backing"]["backing_flock_writer"], errno.EAGAIN)
                 and refused(report["exclusive_backing"]["dotnet_backing"], errno.EAGAIN)
                 and report["released_backing_writer"]["wrote"] and report["dotnet_uncontended_backing"]["acquired"]
                 and report["released_net_backing"]["acquired"], "Positive backing controls failed")
    shared_backing = report["dotnet_shared_backing"]
    shared_grant = report["dotnet_shared_grant"]
    exclusive_grant = report["exclusive_grant"]
    if expected == "supported":
        assert_state(report["dotnet_uncontended_grant"]["acquired"] and shared_grant["holder"]["acquired"]
                     and exclusive_grant["holder"]["acquired"], "The portal did not grant an uncontended lease")
        assert_state(all(refused(r, errno.EAGAIN) for r in (
            shared_backing["grant_flock_writer"], shared_grant["backing_writer"], shared_grant["grant_writer"],
            report["exclusive_backing"]["dotnet_grant"], exclusive_grant["dotnet_backing"], exclusive_grant["dotnet_grant"])),
            "Independent backing and portal consumers failed to exclude a consenting writer or reader")
        assert_state(report["released_grant_writer"]["wrote"] and report["released_net_grant"]["acquired"],
                     "Released locks did not permit portal acquisition and an independent fixture write")
    else:
        assert_state(all(refused(r, errno.ENOSYS) for r in (report["dotnet_uncontended_grant"], shared_backing["grant_flock_writer"],
            report["exclusive_backing"]["dotnet_grant"], exclusive_grant["holder"], report["released_grant_writer"],
            report["released_net_grant"])), "Expected an actual ENOSYS capability refusal on the unsupported portal")
    return report


if __name__ == "__main__":
    native_lock(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4] == "hold")
