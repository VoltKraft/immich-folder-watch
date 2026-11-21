"""Check cooperating readers and exclusively locking peers on a private, regular Documents grant."""
from contextlib import contextmanager, ExitStack
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time

APP = "org.example.IfwServices"
SERVICE = "org.freedesktop.portal.Documents"
OBJECT = "/org/freedesktop/portal/documents"
BACKING = Path("/tmp/producer/source")
MOUNT = Path("/run/user/0/doc")
FIXTURE = b"Synthetic upload fixture\n"


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n")


def native(root, intent, hold):
    if os.getenv("IFW_QA_ISOLATED") != "1" or root != BACKING and not (
            root.parent.parent == MOUNT / "by-app" / APP and root.name == "source"):
        raise ValueError("Expected the synthetic source or authorized app view")
    with (root / "album/original.jpg").open("rb" if intent == "shared" else "r+b") as fd:
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if intent == "shared" else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except OSError as error:
            print(f"REFUSED errno={error.errno}", flush=True)
            return 20
        if fd.read(64) != FIXTURE:
            raise ValueError("Unexpected contents after exclusive/shared acquisition")
        print(f"ACQUIRED dev={os.fstat(fd.fileno()).st_dev} inode={os.fstat(fd.fileno()).st_ino}", flush=True)
        if hold and sys.stdin.readline() != "release\n":
            raise ValueError("Holder lost its release control")
        fcntl.flock(fd, fcntl.LOCK_UN)
    return 0


def finish(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(3)


def require_result(line, expected_errno, kind):
    if expected_errno is None:
        if not line.startswith("ACQUIRED "):
            raise ValueError(f"Expected acquired lease, got {line}")
    elif kind == "rust" and expected_errno == errno.EAGAIN and line == "REFUSED kind=WouldBlock":
        return
    elif not re.match(rf"^REFUSED errno={expected_errno}( |$)", line):
        raise ValueError(f"Expected errno {expected_errno}, got {line}")


def start(stack, args, log):
    stream = stack.enter_context(Path(log).open("w"))
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
    stack.callback(finish, proc)
    return proc


def observe(expected):
    from gi.repository import Gio, GLib
    evidence = Path("/result")
    outer = json.loads((evidence / "input.json").read_text())
    if (os.environ.get("DBUS_SESSION_BUS_ADDRESS") != "unix:path=/tmp/session-bus"
            or Path.home() != Path("/tmp/home") or os.geteuid() != 0
            or any(os.readlink("/proc/self/ns/" + k) == v for k, v in outer["outerNamespaces"].items())):
        raise ValueError("A private namespaced home, bus, network and mapped UID are required")
    images = {Path("/probe/reader"): outer["rustReaderSha256"]}
    images.update({Path("/oracle") / name: value for name, value in outer["oracleLibraries"].items()})
    for path, digest in images.items():
        with path.open("rb") as image:
            if hashlib.file_digest(image, "sha256").hexdigest() != digest:
                raise ValueError("The Rust or managed reader differs from its build receipt")
    os.umask(0o077)
    Path("/run/user/0").chmod(0o700)
    config = Path("/tmp/bus.conf")
    config.write_text('<busconfig><type>session</type><listen>unix:path=/tmp/session-bus</listen><auth>EXTERNAL</auth>'
                      '<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
    result = dict(expected=expected, operations=[], contentSha256=hashlib.sha256(FIXTURE).hexdigest(),
                  uidMap=Path("/proc/self/uid_map").read_text().strip())
    backing_file = BACKING / "album/original.jpg"
    backing_file.parent.mkdir(parents=True)
    backing_file.write_bytes(FIXTURE)
    def observed(record):
        result["operations"].append(record)
        save(evidence / "observation.json", result)
    with ExitStack() as stack:
        bus_proc = start(stack, ["dbus-daemon", "--nofork", "--nopidfile", "--config-file", str(config)], evidence / "bus.log")
        end = time.monotonic() + 5
        while not Path("/tmp/session-bus").is_socket():
            if bus_proc.poll() is not None or time.monotonic() >= end:
                raise TimeoutError("Private D-Bus startup failed")
            time.sleep(.01)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        store = start(stack, ["/usr/libexec/xdg-permission-store", "-v"], evidence / "store.log")
        daemon = start(stack, ["/probe/portal", "-v"], evidence / "portal.log")
        def call(name, args=None):
            return bus.call_sync(SERVICE, OBJECT, SERVICE, name, args, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
        end = time.monotonic() + 10
        while True:
            try:
                raw_mount, = call("GetMountPoint")
                break
            except GLib.Error:
                if store.poll() is not None or daemon.poll() is not None or time.monotonic() >= end:
                    raise RuntimeError("Private Documents service failed to mount")
                time.sleep(.025)
        mount = Path(os.fsdecode(bytes(raw_mount).removesuffix(b"\0")))
        for proc, key in ((daemon, "daemonSha256"), (store, "storeSha256")):
            with Path(f"/proc/{proc.pid}/exe").open("rb") as image:
                if hashlib.file_digest(image, "sha256").hexdigest() != outer[key]:
                    raise ValueError("The running portal service differs from the selected binary")
        found = [line for line in Path("/proc/self/mountinfo").read_text().splitlines() if line.split()[4] == str(mount)]
        if mount != MOUNT or len(found) != 1 or " - fuse.portal " not in found[0]:
            raise ValueError("The private Documents service did not mount its FUSE filesystem")
        fd = os.open(BACKING, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            fds = Gio.UnixFDList.new()
            handle = fds.append(fd)
            reply, _ = bus.call_with_unix_fd_list_sync(SERVICE, OBJECT, SERVICE, "AddFull",
                GLib.Variant("(ahusas)", ([handle], 8, APP, ["read", "write"])), None, Gio.DBusCallFlags.NONE, 5000, fds, None)
        finally:
            os.close(fd)
        (token,), _ = reply.unpack()
        if not re.fullmatch("[0-9a-fA-F]+", token):
            raise ValueError("Expected one opaque Documents ID")
        stack.callback(call, "Delete", GLib.Variant("(s)", (token,)))
        grant = MOUNT / "by-app" / APP / token / "source"
        result.update(mount=found[0], grant=str(grant), documentId=token, backing=str(BACKING),
                      runningDaemon=outer["daemonSha256"], permissionStore=outer["storeSha256"])
        def command(view, kind, hold):
            path = grant if view == "grant" else BACKING
            if kind == "dotnet":
                args = ["/runtime/dotnet", "/oracle/PortalReference.dll", "hold" if hold else "read", str(path)]
            elif kind == "rust":
                args = ["/probe/reader", "hold" if hold else "read", str(path)]
            else:
                args = ["/usr/bin/python3", "/recipe/observe.py", "native", str(path), kind, "hold" if hold else "read"]
            if view == "grant":
                args = ["bwrap", "--die-with-parent", "--bind", "/", "/", "--dev", "/dev", "--tmpfs", "/tmp/producer",
                        "--cap-drop", "ALL", "--", "/usr/bin/python3", "/recipe/observe.py", "grant-consumer", *args]
            return args
        @contextmanager
        def lease(view, kind, hold, expected_errno):
            proc = subprocess.Popen(command(view, kind, hold), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, bufsize=1)
            try:
                if not select.select([proc.stdout], [], [], 8)[0]:
                    raise TimeoutError("No response from the cooperating participant")
                line = proc.stdout.readline().strip()
                observed(dict(view=view, operation=kind, mode="hold" if hold else "try", expectedErrno=expected_errno,
                              detail=line, **({"stderr": proc.stderr.read(2048)} if proc.poll() is not None else {})))
                require_result(line, expected_errno, kind)
                yield
                if hold and expected_errno is None:
                    proc.stdin.write("release\n")
                    proc.stdin.flush()
                rc = proc.wait(timeout=5)
                if rc != (0 if expected_errno is None else 20):
                    raise RuntimeError(f"Unexpected participant exit {rc}")
            finally:
                finish(proc)
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    pipe.close()
        def check(view, kind, reason=None):
            with lease(view, kind, False, reason):
                pass
        for view in ("backing", "grant"):
            unsupported = expected == "enosys" and view == "grant"
            for reader in ("rust", "dotnet"):
                with lease(view, reader, True, errno.ENOSYS if unsupported else None):
                    if not unsupported:
                        for contender in ("backing", "grant"):
                            reason = errno.ENOSYS if expected == "enosys" and contender == "grant" else None
                            check(contender, "shared", reason)
                            check(contender, "exclusive", reason or errno.EAGAIN)
                check(view, "exclusive", errno.ENOSYS if unsupported else None)
            with lease(view, "exclusive", True, errno.ENOSYS if unsupported else None):
                if not unsupported:
                    for contender in ("backing", "grant"):
                        reason = errno.ENOSYS if expected == "enosys" and contender == "grant" else errno.EAGAIN
                        for reader in ("rust", "dotnet", "exclusive"):
                            check(contender, reader, reason)
            for reader in ("rust", "dotnet"):
                check(view, reader, errno.ENOSYS if unsupported else None)
        call("RevokePermissions", GLib.Variant("(ssas)", (token, APP, ["read", "write"])))
        if grant.exists() or backing_file.read_bytes() != FIXTURE:
            raise ValueError("Revocation or final known-file readback failed")
        result.update(revoked=True, contentUnchanged=True)
    result["status"] = "passed"
    save(evidence / "observation.json", result)


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "grant-consumer":
        if BACKING.exists() or not re.search(r"^CapEff:\s*0+$", Path("/proc/self/status").read_text(), re.M):
            raise SystemExit("The grant participant sees the producer or retained capabilities")
        os.execv(args[0], args)
    elif mode == "native":
        raise SystemExit(native(Path(args[0]), args[1], args[2] == "hold"))
    elif mode == "observe" and args in (["enosys"], ["supported"]):
        observe(args[0])
    else:
        raise SystemExit(2)
