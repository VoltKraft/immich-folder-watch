"""Check cooperating readers and exclusively locking peers on a private, regular Documents grant."""
from contextlib import contextmanager, ExitStack
import errno
import fcntl
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
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
    pending = path.with_name(path.name + ".new")
    pending.write_text(json.dumps(obj, indent=2) + "\n")
    pending.replace(path)


@contextmanager
def retry_peer(pid, proc, expected_image):
    """Bind procfs observations to this child's executable and both private control pipes."""
    handle = os.open(f"/proc/{pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        peer = Path(f"/proc/self/fd/{handle}")
        for number, pipe in ((0, proc.stdin), (1, proc.stdout)):
            actual = (peer / "fd" / str(number)).stat()
            if not stat.S_ISFIFO(actual.st_mode) or not os.path.samestat(actual, os.fstat(pipe.fileno())):
                raise ValueError("The retry reader does not own the launched participant's control pipes")
        with (peer / "exe").open("rb") as image:
            if hashlib.file_digest(image, "sha256").hexdigest() != expected_image:
                raise ValueError("The retry peer is not the selected Rust reader")
        yield peer
    finally:
        os.close(handle)


def fd_sample(peer, number, paths):
    """Read metadata for a selected descriptor. Never persist an unknown link target."""
    fd = peer / "fd" / str(number)
    row = {"fd": number}
    try:
        target = os.readlink(fd)
        row["link"] = next((role for role, path in paths.items() if target == str(path)), "other")
        if row["link"] == "other":
            row["link"] = next((role + "-deleted" for role, path in paths.items()
                                if target == str(path) + " (deleted)"), "other")
    except OSError as error:
        row["linkErrno"] = error.errno
    try:
        item = fd.stat()
        kind = {stat.S_IFDIR: "directory", stat.S_IFREG: "regular"}.get(stat.S_IFMT(item.st_mode), "other")
        row.update(device=item.st_dev, inode=item.st_ino, fileType=kind, typeBits=stat.S_IFMT(item.st_mode))
    except OSError as error:
        row["statErrno"] = error.errno
    try:
        info = (peer / "fdinfo" / str(number)).read_text()
        flags = re.search(r"^flags:\s+([0-7]+)$", info, re.M)
        mount = re.search(r"^mnt_id:\s+([0-9]+)$", info, re.M)
        if flags:
            row["flags"] = flags[1]
            value = int(flags[1], 8)
            row["openFlags"] = dict(readOnly=value & os.O_ACCMODE == os.O_RDONLY, directory=bool(value & os.O_DIRECTORY),
                                    noFollow=bool(value & os.O_NOFOLLOW), closeOnExec=bool(value & os.O_CLOEXEC))
        if mount:
            row["mountId"] = int(mount[1])
    except OSError as error:
        row["fdinfoErrno"] = error.errno
    return row


def original_fds(peer, paths, before):
    return {role: fd_sample(peer, before[str(path)]["fd"], paths) for role, path in paths.items()}


def named_fds(peer, paths, evidence):
    """Preserve the original exact link, flags and uniqueness checks for both directories."""
    known = {str(path): role for role, path in paths.items()}
    rows = evidence["named"] = {role: [] for role in paths}
    for fd in (peer / "fd").iterdir():
        role = known.get(os.readlink(fd))
        if role:
            rows[role].append(fd_sample(peer, int(fd.name), paths))
    if any(len(items) != 1 for items in rows.values()):
        raise ValueError("The Rust reader did not retain both authorized directories unambiguously")
    required = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    found = {}
    for role, (row,) in rows.items():
        flags = int(row.get("flags", "0"), 8)
        if (row.get("link") != role or row.get("fileType") != "directory" or flags & required != required
                or flags & os.O_ACCMODE != os.O_RDONLY):
            raise ValueError("The retained directory descriptor is missing or has unexpected flags")
        found[str(paths[role])] = {key: row[key] for key in ("fd", "device", "inode", "flags")}
    return found


def retained_fds(peer, paths, evidence, before=None):
    if before is not None:
        # These numbered slots remain diagnosable if a pathname no longer matches.
        evidence["originals"] = original_fds(peer, paths, before)
    current = named_fds(peer, paths, evidence)
    if before is not None and current != before:
        raise ValueError("The retry peer's original directory descriptors changed")
    return current


def request_attempt(pipe, number, peer, paths, before, result, file):
    trace = result["retryObservation"]
    trace["phase"] = f"verify directories before attempt {number}"
    current = original_fds(peer, paths, before)
    trace["beforeAttempts"].append(dict(attempt=number, phase=trace["phase"], lastVerified=trace["lastVerified"],
                                        originals=current))
    save(file, result)
    for role, path in paths.items():
        row, original = current[role], before[str(path)]
        if (row.get("link") != role or row.get("fileType") != "directory"
                or any(row.get(key) != original[key] for key in ("fd", "device", "inode", "flags"))):
            raise ValueError("The original authorized directory descriptor changed before a retry")
    trace.update(lastVerified=trace["phase"], phase=f"attempt {number}")
    save(file, result)
    pipe.write("attempt\n")
    pipe.flush()


def retry_failed(file, result, error, peer, paths, before):
    result["status"] = "failed"
    trace = result["retryObservation"]
    trace["failure"] = dict(phase=trace["phase"], lastVerified=trace["lastVerified"],
                            type=type(error).__name__, errno=getattr(error, "errno", None))
    if before is not None:
        trace["failure"]["originals"] = original_fds(peer, paths, before)
    save(file, result)


@contextmanager
def record_grant_at_refusal(grant, lookup, result, file):
    """Read names and exporter permissions only after a required descriptor observation failed."""
    try:
        yield
    except (OSError, ValueError) as primary:
        trace = result["retryObservation"]
        state = trace["grantAtRefusal"] = {"phase": trace["phase"], "names": {}}
        names = state["names"]
        try:
            fd = os.open(grant, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as error:
            names.update(grant={"errno": error.errno}, album={"parentUnavailable": True})
        else:
            try:
                for role, read in (("grant", lambda: os.fstat(fd)),
                                   ("album", lambda: os.stat("album", dir_fd=fd, follow_symlinks=False))):
                    try:
                        info = read()
                        names[role] = dict(typeBits=stat.S_IFMT(info.st_mode), device=info.st_dev, inode=info.st_ino)
                    except OSError as error:
                        names[role] = {"errno": error.errno}
            finally:
                try:
                    os.close(fd)
                except OSError as error:
                    state["closeErrno"] = error.errno
        try:
            backing, applications = lookup()
            permissions = applications.get(APP, ())
            state["documentInfo"] = dict(expectedBacking=bytes(backing).removesuffix(b"\0") == os.fsencode(BACKING),
                                         read="read" in permissions, write="write" in permissions)
        except Exception as error:
            state["documentInfo"] = dict(errorType=type(error).__name__, code=getattr(error, "code", None))
        try:
            save(file, result)
        except OSError as error:
            primary.add_note(f"Could not persist the grant observation (errno {error.errno})")
        raise


def revoke_grant(call, args, grant, backing, result, file, _kind, primary, _traceback):
    """Attempt all three independent checks, leaving an earlier exception active during unwind."""
    record = result["revocation"] = dict(callReturned=False, grantAbsent=None, backingRead=False,
                                         backingUnchanged=None, failures={})
    if primary is not None:
        result["status"] = "failed"
        result["primaryFailure"] = dict(type=type(primary).__name__, errno=getattr(primary, "errno", None),
                                        phase=result.get("retryObservation", {}).get("phase", "ordinary lock matrix"))
    def revoke():
        call("RevokePermissions", args)
        return True
    def absent():
        try:
            grant.lstat()
        except FileNotFoundError:
            return True
        return False
    def known_bytes():
        content = backing.read_bytes()
        record["backingRead"] = True
        return content == FIXTURE
    first = None
    def checkpoint():
        nonlocal first
        try:
            save(file, result)
        except OSError as error:
            result["status"] = "failed"
            record["failures"]["persistEvidence"] = dict(type=type(error).__name__, errno=error.errno)
            if first is None:
                first = error
            (primary if primary is not None else first).add_note(f"Could not save revocation evidence: errno {error.errno}")
    for stage, action in (("callReturned", revoke), ("grantAbsent", absent), ("backingUnchanged", known_bytes)):
        try:
            record[stage] = action()
            if not record[stage]:
                raise ValueError(f"Revocation readback failed at {stage}")
        except Exception as error:
            result["status"] = "failed"
            record["failures"][stage] = dict(type=type(error).__name__, errno=getattr(error, "errno", None))
            if first is None:
                first = error
        checkpoint()
    if first is None:
        result.update(revoked=True, contentUnchanged=True)
        checkpoint()
    if first is not None and primary is None:
        raise first


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
    elif kind == "rust":
        outcomes = {errno.ENOSYS: ("UnsupportedFileLock", "CheckPortalFileLockSupport"),
                    errno.EOPNOTSUPP: ("UnsupportedFileLock", "CheckPortalFileLockSupport"),
                    errno.EAGAIN: ("FileBusy", "RetryAfterWriterRelease"),
                    errno.EACCES: ("AccessDenied", "RestoreAuthorizedAccess"),
                    errno.EPERM: ("AccessDenied", "RestoreAuthorizedAccess")}
        outcome, action = outcomes.get(expected_errno, ("ReadLeaseUnavailable", "InspectNativeError"))
        native = [f"errno={expected_errno}"]
        if expected_errno == errno.EAGAIN:
            native.append("kind=WouldBlock")
        if line not in [f"REFUSED {value} operation=ReadLease outcome={outcome} action={action}" for value in native]:
            raise ValueError(f"Expected classified Rust refusal for errno {expected_errno}, got {line}")
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
        # Revoke this exact grant before Delete, including after a failed retry observation.
        stack.push(partial(revoke_grant, call, GLib.Variant("(ssas)", (token, APP, ["read", "write"])),
                           grant, backing_file, result, evidence / "observation.json"))
        def command(view, kind, hold, retry=False):
            path = grant if view == "grant" else BACKING
            if kind == "dotnet":
                args = ["/runtime/dotnet", "/oracle/PortalReference.dll", "hold" if hold else "read", str(path)]
            elif kind == "rust":
                args = ["/probe/reader", "retry" if retry else "hold" if hold else "read", str(path)]
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
        # A single reader keeps the original grant and album descriptors alive
        # across an unavailable attempt and the later explicit retry. Never
        # restart the portal or replace the grant to manufacture recovery.
        proc = subprocess.Popen(command("grant", "rust", False, retry=True), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        trace = result["retryObservation"] = dict(lastVerified="ordinary lock matrix", beforeAttempts=[])
        paths = {"grant": grant, "album": grant / "album"}
        peer = before_fds = None
        def diagnosed():
            return record_grant_at_refusal(grant, lambda: call("Info", GLib.Variant("(s)", (token,))),
                                           result, evidence / "observation.json")
        def phase(name):
            trace["phase"] = name
            save(evidence / "observation.json", result)
        def verified():
            trace["lastVerified"] = trace["phase"]
            save(evidence / "observation.json", result)
        try:
            phase("identify retry reader")
            def response():
                if not select.select([proc.stdout], [], [], 8)[0]:
                    raise TimeoutError("No bounded retry response from the Rust reader")
                return proc.stdout.readline().strip()
            ready = response()
            match = re.fullmatch(r"READY pid=([1-9][0-9]*) attempts=3", ready)
            if match is None:
                raise ValueError(f"Expected a retained grant reader, got {ready}")
            pid = int(match.group(1))
            peer = stack.enter_context(retry_peer(pid, proc, outer["rustReaderSha256"]))
            trace["peer"] = dict(pid=pid, imageSha256=outer["rustReaderSha256"], controlPipesVerified=True)
            verified()
            def identities(record):
                entries = record["identities"] = {}
                failure = None
                for name, path in (("grant", grant), ("album", grant / "album"), ("backingFile", backing_file)):
                    try:
                        item = path.stat()
                        entries[name] = dict(device=item.st_dev, inode=item.st_ino)
                    except OSError as error:
                        entries[name] = {"errno": error.errno}
                        failure = error
                if failure:
                    raise failure
                return entries
            phase("verify original directories")
            before = trace["before"] = {}
            with diagnosed():
                before_ids = identities(before)
                before_fds = retained_fds(peer, paths, before)
                for name, path in paths.items():
                    if any(before_ids[name][key] != before_fds[str(path)][key] for key in ("device", "inode")):
                        raise ValueError("The retained directories differ from the authorized grant")
            verified()
            attempts = []
            def attempt(reason):
                number = len(attempts) + 1
                with diagnosed():
                    request_attempt(proc.stdin, number, peer, paths, before_fds, result, evidence / "observation.json")
                line = response()
                attempts.append(line)
                observed(dict(view="grant", operation="rust", mode="retained-retry", attempt=len(attempts),
                              expectedErrno=reason, detail=line))
                require_result(line, reason, "rust")
                verified()
            unsupported = expected == "enosys"
            attempt(errno.ENOSYS if unsupported else None)
            phase("acquire backing writer")
            with lease("backing", "exclusive", True, None):
                verified()
                attempt(errno.ENOSYS if unsupported else errno.EAGAIN)
                phase("release backing writer")
            verified()
            attempt(errno.ENOSYS if unsupported else None)
            phase("verify directories after attempts")
            after = trace["after"] = {}
            with diagnosed():
                after_ids = identities(after)
                after_fds = retained_fds(peer, paths, after, before_fds)
                if (before_ids != after_ids or before_fds != after_fds or backing_file.read_bytes() != FIXTURE
                        or attempts[0] != attempts[2]):
                    raise ValueError("Retry changed the grant, held directories, file identity, contents or final outcome")
            verified()
            result["rustRetry"] = dict(ready=ready, documentId=token, attempts=attempts,
                directoryDescriptorsBefore=before_fds, directoryDescriptorsAfter=after_fds,
                identitiesBefore=before_ids, identitiesAfter=after_ids, contentUnchanged=True,
                outcome="UnsupportedFileLockRemains" if unsupported else "FileBusyRecovered",
                contentSha256=hashlib.sha256(backing_file.read_bytes()).hexdigest())
            phase("stop retry reader")
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            if proc.wait(timeout=5) != 0:
                raise RuntimeError("The bounded Rust retry peer failed")
            verified()
        except Exception as error:
            retry_failed(evidence / "observation.json", result, error, peer, paths, before_fds)
            raise
        finally:
            finish(proc)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                pipe.close()
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
