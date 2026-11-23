"""Exercise the normal installed Flatpak's Documents grant in the disposable Noble guest."""
import argparse
from contextlib import contextmanager, ExitStack
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import select
import subprocess
import tempfile
import time

APP = "org.example.IfwPortalLease"
DOCUMENTS = "org.freedesktop.portal.Documents"
STORE = "org.freedesktop.impl.portal.PermissionStore"
OBJECT = "/org/freedesktop/portal/documents"
DBUS = "org.freedesktop.DBus"
FIXTURE = b"Synthetic upload fixture\n"
RIGHTS = ["read", "write"]
VERSION = "1.18.4-1ubuntu2.24.04.3"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def guard(phase):
    uid = os.getuid()
    runtime = Path(f"/run/user/{uid}")
    if (uid == 0 or uid != os.geteuid() or pwd.getpwuid(uid).pw_name != "ifwqa"
            or Path.home() != Path("/home/ifwqa")
            or os.environ.get("XDG_RUNTIME_DIR") != str(runtime)
            or os.environ.get("DBUS_SESSION_BUS_ADDRESS") != f"unix:path={runtime}/bus"
            or not (runtime / "bus").is_socket() or runtime.stat().st_uid != uid
            or Path("/sys/class/dmi/id/product_name").read_text().strip() != "IFW-Noble-Portal-QA"):
        raise ValueError("Expected the disposable Noble VM and its regular test user's session")
    seed = Path("/mnt/ifw")
    mounts = [line.split() for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    if not any(row[4] == str(seed) and "ro" in row[5].split(",") and row[row.index("-") + 1] == "iso9660"
               for row in mounts):
        raise ValueError("Expected the read-only guest input disk")
    trial = (seed / "trial-id").read_text().strip()
    stage = (seed / "stage").read_text().strip()
    if not re.fullmatch("[0-9a-f]{32}", trial) or not (stage == "lease" or (stage == "lease-stock" and phase == "stock")):
        raise ValueError("Expected the installed lease trial seed")
    return trial, runtime


def reader_reply(lines, expected, uid):
    if len(lines) != 2 or not re.fullmatch(rf"SANDBOX uid={uid} mount=fuse.portal direct_errno=(2|13)", lines[0]):
        raise ValueError(f"Missing sandbox or direct-access evidence: {lines!r}")
    patterns = {"acquired": (r"ACQUIRED bytes=" + str(len(FIXTURE)) + r" identity=FileIdentity \{ volume: \d+, file: \d+ \}", 0),
                "unsupported": (r"REFUSED lease=errno=(38|95)", 20),
                "busy": (r"REFUSED lease=contended", 20),
                "revoked": (r"NO_GRANT root_errno=(2|13)", 21),
                "lock-unsupported": (r"LOCK_CONTROL errno=(38|95)", 0),
                "lock-acquired": (r"LOCK_CONTROL acquired", 0)}
    pattern, status = patterns[expected]
    if not re.fullmatch(pattern, lines[1]):
        raise ValueError(f"Expected {expected} from the ordinary Flatpak, received {lines[1]!r}")
    return status


@contextmanager
def reader(token, phase, expected, result, hold=False):
    mode = "lock-control" if expected.startswith("lock-") else ("hold" if hold else "read")
    command = ["flatpak", "run", "--user", "--branch=test", "--env=IFW_QA_ISOLATED=1",
               APP, mode, token, phase]
    record = {"expected": expected, "mode": command[-3], "lines": []}
    result["operations"].append(record)
    with tempfile.TemporaryFile() as errors, subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, bufsize=0) as proc:
        try:
            deadline = time.monotonic() + 25
            for _ in range(2):
                if not select.select([proc.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                    raise TimeoutError("Timed out awaiting the installed reader")
                line = proc.stdout.readline(4096)
                if not line:
                    break
                record["lines"].append(line.decode().rstrip("\n"))
            status = reader_reply(record["lines"], expected, os.getuid())
            yield
            if hold:
                proc.stdin.write(b"release\n")
            record["exit"] = proc.wait(timeout=12)
            if record["exit"] != status or proc.stdout.read(1000):
                raise ValueError("Unexpected ordinary reader output or exit status")
        finally:
            if proc.poll() is None:
                proc.stdin.close()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            record["exit"] = proc.returncode
            errors.seek(0)
            record["stderr"] = errors.read(4096).decode(errors="replace")


def check_lock(token, phase, backing, result):
    with reader(token, phase, "lock-acquired" if phase == "candidate" else "lock-unsupported", result):
        pass
    with backing.open("r+b", buffering=0) as writer:
        if phase != "candidate":
            with reader(token, phase, "unsupported", result):
                pass
            fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with reader(token, phase, "unsupported", result):
                    pass
            finally:
                fcntl.flock(writer, fcntl.LOCK_UN)
            with reader(token, phase, "unsupported", result):
                pass
            return
        with reader(token, phase, "acquired", result, hold=True):
            try:
                fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                if error.errno != errno.EAGAIN:
                    raise
                result["backingWriterRefusalErrno"] = error.errno
            else:
                raise RuntimeError("The backing writer acquired the installed Flatpak's held file")
        fcntl.flock(writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result["writerAcquiredAfterReaderRelease"] = True
        try:
            with reader(token, phase, "busy", result):
                pass
        finally:
            fcntl.flock(writer, fcntl.LOCK_UN)
        with reader(token, phase, "acquired", result):
            pass
        result["readerReacquiredAfterWriterRelease"] = True


def observe(phase, payload, runtime, result):
    from gi.repository import Gio, GLib

    version = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Version}", "xdg-desktop-portal"], text=True)
    result["dpkg"] = version
    if version != "ii  " + VERSION + ("+ifwqa1" if phase == "candidate" else ""):
        raise ValueError(f"Unexpected installed package: {version!r}")
    info = ["flatpak", "--user", "info"]
    appref = APP + "//test"
    location = Path(subprocess.check_output([*info, "--show-location", appref], text=True).strip())
    result["app"] = {"id": appref, "readerSha256": sha(location / "files/bin/reader"),
                     "commit": subprocess.check_output([*info, "--show-commit", appref], text=True).strip(),
                     "runtimeCommit": subprocess.check_output(
                         [*info, "--show-commit", "org.freedesktop.Platform//26.08"], text=True).strip(),
                     "permissions": subprocess.check_output([*info, "--show-permissions", appref], text=True)}
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(dest, path, interface, method, args=None):
        return bus.call_sync(dest, path, interface, method, args, None, Gio.DBusCallFlags.NONE, 12000, None).unpack()

    def daemon_call(method, signature, values):
        return call(DBUS, "/org/freedesktop/DBus", DBUS, method, GLib.Variant(signature, values))[0]

    def document(method, signature=None, values=None):
        return call(DOCUMENTS, OBJECT, DOCUMENTS, method, GLib.Variant(signature, values) if signature else None)

    def service(name, binary):
        unique = daemon_call("GetNameOwner", "(s)", (name,))
        pid = daemon_call("GetConnectionUnixProcessID", "(s)", (unique,))
        owner_uid = daemon_call("GetConnectionUnixUser", "(s)", (unique,))
        installed = Path("/usr/libexec") / binary
        proc = Path(f"/proc/{pid}/exe")
        expected = sha(payload / installed.relative_to("/"))
        if (owner_uid != os.getuid() or proc.readlink() != installed or not proc.samefile(installed)
                or sha(proc) != expected or sha(installed) != expected
                or daemon_call("GetNameOwner", "(s)", (name,)) != unique):
            raise ValueError(f"Unexpected installed executable or D-Bus owner for {name}")
        return {"name": name, "unique": unique, "pid": pid, "uid": owner_uid, "exe": str(installed), "sha256": expected}

    mount = Path(os.fsdecode(bytes(document("GetMountPoint")[0]).removesuffix(b"\0")))
    if mount != runtime / "doc" or not any(line.split()[4] == str(mount) and " - fuse.portal " in line
                                           for line in Path("/proc/self/mountinfo").read_text().splitlines()):
        raise ValueError("The activated service returned an unexpected Documents mount")
    daemon_call("StartServiceByName", "(su)", (STORE, 0))
    def owners():
        return [service(DOCUMENTS, "xdg-document-portal"), service(STORE, "xdg-permission-store")]
    result["services"] = owners()
    work = Path.home() / ("ifw-portal-" + phase)
    work.mkdir(mode=0o700)
    root = work / "source"
    backing = root / "album/original.jpg"
    backing.parent.mkdir(parents=True)
    backing.write_bytes(FIXTURE)
    with ExitStack() as stack:
        original = stack.enter_context(backing.open("rb"))
        flags = os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC
        anchor = os.open(root, flags | os.O_NOFOLLOW)
        stack.callback(os.close, anchor)
        # Noble refuses O_PATH descriptors carrying O_NOFOLLOW. Reopen the
        # already pinned directory as a portal-compatible descriptor.
        fd = os.open(f"/proc/self/fd/{anchor}", flags)
        try:
            if not os.path.samestat(os.fstat(anchor), os.fstat(fd)):
                raise ValueError("The exported directory differs from its original descriptor")
            handles = Gio.UnixFDList.new()
            idx = handles.append(fd)
            reply, _ = bus.call_with_unix_fd_list_sync(
                DOCUMENTS, OBJECT, DOCUMENTS, "AddFull", GLib.Variant("(ahusas)", ([idx], 8, APP, RIGHTS)),
                None, Gio.DBusCallFlags.NONE, 12000, handles, None)
        finally:
            os.close(fd)
        (token,), _ = reply.unpack()
        if not re.fullmatch(r"[a-f0-9]{1,32}", token):
            raise ValueError("Missing the opaque Documents grant ID")
        result["documentId"] = token
        args = (token, APP, RIGHTS)
        def cleanup():
            try:
                document("Delete", "(s)", (token,))
                try:
                    document("Info", "(s)", (token,))
                except GLib.Error as error:
                    remote = Gio.DBusError.get_remote_error(error)
                    unknown = (remote == "org.freedesktop.portal.Error.InvalidArgument"
                               and "Invalid ID passed" in error.message)
                    if remote != "org.freedesktop.portal.Error.NotFound" and not unknown:
                        raise
                    docs, = document("List", "(s)", ("",))
                    if token in docs:
                        raise ValueError("The deleted document remains in the service listing")
                    result["deleted"] = remote
                else:
                    raise ValueError("The deleted guest document still exists")
            finally:
                if (not os.path.samestat(os.fstat(original.fileno()), backing.stat())
                        or original.read(len(FIXTURE) + 1) != FIXTURE or backing.read_bytes() != FIXTURE):
                    raise ValueError("The original synthetic file changed")
                result["backingSha256"] = sha(backing)
                metadata = os.fstat(original.fileno())
                result["originalBacking"] = {"device": metadata.st_dev, "inode": metadata.st_ino,
                                             "size": metadata.st_size, "sha256": result["backingSha256"]}
        stack.callback(cleanup)

        def inspect(granted):
            source, perms = document("Info", "(s)", (token,))
            found = sorted(perms.get(APP, []))
            if bytes(source).removesuffix(b"\0") != os.fsencode(root) or found != (sorted(RIGHTS) if granted else []):
                raise ValueError("The service returned a different source or application permission set")
            return found

        def revoke():
            document("RevokePermissions", "(ssas)", args)
            result["revokedRights"] = inspect(False)
            with reader(token, phase, "revoked", result):
                pass
        stack.callback(revoke)
        result["grantedRights"] = inspect(True)
        check_lock(token, phase, backing, result)
    if owners() != result["services"]:
        raise ValueError("An installed service changed owner during the phase")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("stock", "candidate", "restored"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    trial, runtime = guard(args.phase)
    result = {"trial": trial, "phase": args.phase, "status": "failed", "operations": []}
    with args.output.open("x") as out:
        try:
            observe(args.phase, args.payload.resolve(strict=True), runtime, result)
            result["status"] = "passed"
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
            context = error.__context__
            if context is not None:
                result["earlierError"] = f"{type(context).__name__}: {context}"
            raise
        finally:
            out.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
