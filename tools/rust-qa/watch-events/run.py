"""Compare native watch wakeups with independent, complete synthetic inventories."""

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import secrets
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = ROOT / "artifacts/rust/watch-events"
TOOLCHAIN = ROOT / "artifacts/rust/toolchain/bin"
PIN = ROOT / "rust/toolchain-inputs.json"
CHECK = HERE.parent / "check-toolchain.py"
REFERENCE = "19dcbaf63be583c4cf9071302abeb9ccdc2bd3dc"
KEYS = ("generation", "acknowledged", "reasons", "requiresRegistration", "queued", "peakQueued", "coalesced")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def machine(binary, target):
    arch = target.split("-", 1)[0]
    with binary.open("rb") as stream:
        header = stream.read(64)
        if target.endswith("windows-msvc"):
            require(header.startswith(b"MZ"), "Expected a native PE image")
            stream.seek(struct.unpack_from("<I", header, 60)[0])
            require(stream.read(4) == b"PE\0\0", "Missing PE signature")
            value, = struct.unpack("<H", stream.read(2))
            expected = {"x86_64": 0x8664, "aarch64": 0xaa64}
        else:
            require(header.startswith(b"\x7fELF\x02\x01"), "Expected a native little-endian ELF64 image")
            value, = struct.unpack_from("<H", header, 18)
            expected = {"x86_64": 62, "aarch64": 183}
    require(value == expected[arch], "Executable machine differs from the native OS and compiler host")
    return hex(value)


class Subject:
    def __init__(self, binary, work, token, mode, capacity):
        self.diagnostics = tempfile.TemporaryFile()
        self.process = subprocess.Popen([binary, mode, str(capacity)], cwd=work,
                                        env={**os.environ, "IFW_WATCH_FIXTURE": token, "IFW_WATCH_DIAGNOSTICS": "1"},
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.diagnostics,
                                        text=True, encoding="utf-8")
        self.lines = queue.Queue()

        def read():
            try:
                for line in self.process.stdout:
                    self.lines.put(line.rstrip("\r\n"))
            finally:
                self.lines.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def line(self):
        value = self.lines.get(timeout=10)
        if value is None:
            self.diagnostics.seek(0)
            detail = self.diagnostics.read(2048).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"The watch subject exited before its observation: {detail}")
        return value

    def command(self, text):
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()
        return self.line()

    def snapshot(self, command=None):
        line = self.command(command) if command else self.line()
        label, *values = line.split()
        expected = "READY" if not command or command == "ARM" else "BEGIN" if command == "BEGIN" else "STATE"
        require(label == expected, "Unexpected watch response " + line)
        return dict(zip(KEYS, map(int, values), strict=True))

    def changed(self, before):
        state = self.snapshot(f"WAIT {before['generation']} 5000")
        require(state["generation"] > before["generation"] and state["reasons"] & 2, "Missing native change indication")
        return state

    def settle(self):
        state = self.snapshot("STATE")
        for _ in range(8):
            next_state = self.snapshot(f"WAIT {state['generation']} 100")
            if next_state["generation"] == state["generation"]:
                return
            state = next_state
        raise RuntimeError("The synthetic source did not settle before the next independent mutation")

    def finish(self, partial=False):
        response = self.command("END partial" if partial else "END complete")
        require(response in ("END 0", "END 1"), "Invalid acknowledgement " + response)
        return response == "END 1"

    def stop(self, *, keep_process=False):
        label, micros = self.command("JOIN" if keep_process else "STOP").split()
        require(label == "STOPPED" and int(micros) < 5_000_000, "Native watch did not drain within five seconds")
        if keep_process:
            require(self.process.poll() is None, "The process exited while its joined watch was under observation")
        else:
            require(self.process.wait(timeout=5) == 0, "Watch teardown failed")
        return int(micros)

    def completed_diagnostics(self):
        require(self.process.poll() is not None, "Read native diagnostics only after the subject exits")
        self.diagnostics.seek(0)
        data = self.diagnostics.read(2_200_001)
        require(len(data) <= 2_200_000, "Native diagnostics exceeded their bounded evidence size")
        return data.decode("utf-8")

    def close(self):
        try:
            self.process.stdin.close()
            if self.process.poll() is None:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.reader.join(timeout=5)
            self.process.stdout.close()
            self.diagnostics.close()


@contextmanager
def observe(binary, work, mode="tree", capacity=8, before_arm=None):
    subject = Subject(binary, work, (work / "owner").read_text(encoding="ascii"), mode, capacity)
    try:
        if before_arm:
            require(subject.line() == "CAPTURED 1", "The synthetic pre-registration directory set differs")
            before_arm()
            ready = subject.snapshot("ARM")
        else:
            ready = subject.snapshot()
        require(ready["reasons"] & 1, "Missing initial inventory requirement")
        yield subject, ready
    finally:
        subject.close()


def fixture(area, name):
    work = area / name
    (work / "source/nested").mkdir(parents=True)
    (work / "owner").write_text(secrets.token_hex(16), encoding="ascii")
    return work


def inventory(root, limit=64, recursive=True, before_directory=None):
    """Walk the private fixture. Every stat, directory enumeration and read must succeed."""
    files = {}
    visited = []
    pending = [(root, root.stat(follow_symlinks=False))]
    while pending:
        directory, expected = pending.pop()
        if before_directory:
            before_directory(directory)
        actual = directory.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(actual.st_mode) or not os.path.samestat(expected, actual)
                or getattr(actual, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise OSError("The selected synthetic directory changed before enumeration")
        visited.append((directory, actual))
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                # Windows DirEntry can omit device and inode. Query the actual object.
                attrs = path.stat(follow_symlinks=False)
                if getattr(attrs, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise OSError("Unexpected reparse point inside the synthetic inventory")
                if stat.S_ISDIR(attrs.st_mode):
                    if recursive:
                        if len(pending) + len(visited) >= 1024:
                            return files, False
                        pending.append((path, attrs))
                elif stat.S_ISREG(attrs.st_mode):
                    if len(files) >= limit:
                        return files, False
                    with path.open(encoding="utf-8") as stream:
                        if not os.path.samestat(os.fstat(stream.fileno()), attrs):
                            raise OSError("Synthetic file identity changed before reading")
                        files[path.relative_to(root).as_posix()] = stream.read()
                    if not os.path.samestat(path.stat(follow_symlinks=False), attrs):
                        raise OSError("Synthetic file disappeared during enumeration")
                else:
                    raise OSError("Unexpected object inside the synthetic inventory")
    for directory, observed in visited:
        if not os.path.samestat(directory.stat(follow_symlinks=False), observed):
            raise OSError("Synthetic directory identity changed during enumeration")
    return files, True


def scan(subject, root, expected=None, **options):
    token = subject.snapshot("BEGIN")
    try:
        files, full = inventory(root, **options)
        if full and expected is not None:
            require(files == expected, "Independent complete inventory differs")
    except (OSError, ValueError, RuntimeError):
        require(not subject.finish(partial=True), "A failed inventory was acknowledged")
        raise
    accepted = subject.finish(partial=not full)
    require(full or not accepted, "A partial inventory was acknowledged")
    return token, files, accepted


def complete(subject, root, expected, recursive=True):
    for _ in range(8):
        token, _, accepted = scan(subject, root, expected, recursive=recursive)
        if accepted:
            return token
    raise RuntimeError("Native changes repeatedly overtook the independent inventory")


def cancelled_periodic_scan(binary, area, rows):
    work = fixture(area, "cancel-periodic")
    root = work / "source"
    with observe(binary, work) as (subject, _):
        complete(subject, root, {})
        clean = subject.snapshot("BEGIN")
        require(clean["generation"] == clean["acknowledged"] and clean["reasons"] == 0,
                "The periodic scan did not start from a clean source")
        require(subject.command("CANCEL") == "CANCELLED", "The subject did not abandon the periodic scan")
        retry = complete(subject, root, {})
        require(retry["generation"] > clean["generation"] and retry["reasons"] & 128,
                "Cancelling a clean periodic scan lost the required full rescan")
        rows["cancelled-periodic-scan"] = {"before": clean, "retry": retry, "stopMicros": subject.stop()}


def mutation_cases(binary, area, rows):
    for name in ("create", "modify", "rename", "delete", "nested-create"):
        work = fixture(area, name)
        source = work / "source"
        sample = source / "original.jpg"
        if name in ("modify", "rename", "delete"):
            sample.write_text("first", encoding="utf-8")
        with observe(binary, work) as (subject, ready):
            if name == "create":
                sample.write_text("first", encoding="utf-8")
            elif name == "modify":
                sample.write_text("second-content", encoding="utf-8")
            elif name == "rename":
                sample.rename(source / "renamed.jpg")
            elif name == "delete":
                sample.unlink()
            else:
                (source / "nested/item.jpg").write_text("nested", encoding="utf-8")
            expected = {
                "create": {"original.jpg": "first"}, "modify": {"original.jpg": "second-content"},
                "rename": {"renamed.jpg": "first"}, "delete": {},
                "nested-create": {"nested/item.jpg": "nested"},
            }[name]
            state = subject.changed(ready)
            complete(subject, source, expected)
            rows[name] = {"state": state, "inventory": expected, "stopMicros": subject.stop()}
    direct_scope(binary, area, rows)


def direct_scope(binary, area, rows):
    work = fixture(area, "direct-scope")
    source = work / "source"
    (source / "nested/item.jpg").write_text("original", encoding="utf-8")
    with observe(binary, work, "direct") as (subject, _):
        subject.settle()
        complete(subject, source, {}, recursive=False)
        before = subject.snapshot("STATE")
        require(before["reasons"] == 0 and before["generation"] == before["acknowledged"],
                "The flat subscription did not start with a clean inventory")
        (source / "nested/item.jpg").write_text("nested", encoding="utf-8")
        subject.snapshot(f"WAIT {before['generation']} 350")
        subject.settle()
        nested = subject.snapshot("STATE")
        require(not nested["requiresRegistration"] and nested["reasons"] in (0, 2),
                "The flat subscription lost coverage during the nested mutation")
        complete(subject, source, {}, recursive=False)
        (source / "flat.jpg").write_text("direct", encoding="utf-8")
        subject.changed(nested)
        subject.settle()
        direct = subject.snapshot("STATE")
        require(not direct["requiresRegistration"] and direct["reasons"] == 2,
                "The flat subscription lost its direct-child change")
        complete(subject, source, {"flat.jpg": "direct"}, recursive=False)
        row = rows["direct-scope"] = {"before": before, "nestedMutation": nested, "directChild": direct,
                                       "nestedMutationInventory": {}, "inventory": {"flat.jpg": "direct"},
                                       "stopMicros": subject.stop()}
        if os.name == "nt":
            from windows_control import flat_notification_evidence
            row["rawNotificationTrace"] = subject.completed_diagnostics()
            row["nativeNotifications"] = flat_notification_evidence(
                row["rawNotificationTrace"], before["generation"], nested["generation"], direct["generation"])
        else:
            require(nested["generation"] == before["generation"], "A flat inotify subscription changed for a nested file")


def queue_and_inventory(binary, area, rows):
    work = fixture(area, "pressure")
    source = work / "source"
    expected = {}
    with observe(binary, work, capacity=1) as (subject, state):
        for i in range(5):
            filename = f"{i}.jpg"
            expected[filename] = "fixture"
            (source / filename).write_text("fixture", encoding="utf-8")
            state = subject.changed(state)
        subject.settle()
        pressure = subject.snapshot("BEGIN")
        require(pressure["queued"] == pressure["peakQueued"] == 1 and pressure["coalesced"] > 0
                and pressure["reasons"] & 4, "The full queue did not preserve an independent rescan signal")
        (source / "late.jpg").write_text("late", encoding="utf-8")
        expected["late.jpg"] = "late"
        newer = subject.changed(pressure)
        require(not subject.finish(), "A stale scan acknowledged a later native generation")
        _, partial, accepted = scan(subject, source, limit=1)
        require(len(partial) == 1 and not accepted, "Truncated scan was accepted")
        current = complete(subject, source, expected)
        require(current["reasons"] & 128, "Incomplete inventory signal was lost")
        rows["queue-pressure"] = {"pressure": pressure, "lateChange": newer, "partialCount": len(partial),
                                  "fullInventory": expected, "currentScan": current, "stopMicros": subject.stop()}


def topology(binary, area, rows):
    work = fixture(area, "coverage")
    root = work / "source"
    with observe(binary, work, "partial") as (old, ready):
        require(ready["requiresRegistration"] and ready["reasons"] & 32, "Missing partial coverage signal")
        (root / "added").mkdir()
        state = old.snapshot(f"WAIT {ready['generation']} 5000")
        require(state["generation"] > ready["generation"], "Native directory creation produced no hint")
        if sys.platform == "linux":
            require(state["reasons"] & 64, "New Linux directory did not request watch registration")
        with observe(binary, work, "expanded") as (new, expanded):
            require(not expanded["requiresRegistration"], "New complete watch set was marked partial")
            complete(new, root, {})
            old.stop()
            (root / "added/new.jpg").write_text("newly covered", encoding="utf-8")
            new_state = new.changed(expanded)
            complete(new, root, {"added/new.jpg": "newly covered"})
            rows["reestablished-coverage"] = {"partial": ready, "topologyChange": state,
                                              "newRegistration": new_state, "stopMicros": new.stop()}


def failed_scan(subject, root, **options):
    before = subject.snapshot("STATE")
    try:
        scan(subject, root, **options)
    except OSError as error:
        after = subject.snapshot("STATE")
        require(after["acknowledged"] == before["acknowledged"] and after["reasons"] & 128
                and after["generation"] > after["acknowledged"], "A failed native inventory cleared the last baseline")
        return {"errno": error.errno, "winError": getattr(error, "winerror", None), "before": before, "after": after}
    raise RuntimeError("An unavailable source was accepted as a complete inventory")


def missing_subtree(binary, area, rows):
    work = fixture(area, "unavailable-child")
    root = work / "source"
    branch = root / "nested"
    (branch / "original.jpg").write_text("retained", encoding="ascii")
    with observe(binary, work, "direct") as (subject, _):
        expected = {"nested/original.jpg": "retained"}
        complete(subject, root, expected)

        def move_after_parent_enumeration(directory):
            if directory == branch:
                branch.rename(work / "temporarily-unavailable")

        failure = failed_scan(subject, root, before_directory=move_after_parent_enumeration)
        require(failure["errno"] == 2, "Expected a missing child during its actual enumeration")
        (work / "temporarily-unavailable").rename(branch)
        complete(subject, root, expected)
        rows["missing-subdirectory-during-scan"] = {**failure, "recoveredInventory": expected, "stopMicros": subject.stop()}


@contextmanager
def windows_open(path, access, share, flags):
    from ctypes import WinDLL, WinError, c_void_p, get_last_error
    from ctypes import wintypes as w
    api = WinDLL("kernel32", use_last_error=True)
    create = api.CreateFileW
    create.argtypes = (w.LPCWSTR, w.DWORD, w.DWORD, c_void_p, w.DWORD, w.DWORD, w.HANDLE)
    create.restype = w.HANDLE
    api.CloseHandle.argtypes = (w.HANDLE,)
    api.CloseHandle.restype = w.BOOL

    handle = create(str(path), access, share, None, 3, flags, None)
    if handle == c_void_p(-1).value:
        raise WinError(get_last_error())
    try:
        yield
    finally:
        if not api.CloseHandle(handle):
            raise WinError(get_last_error())


def windows_sharing_error(path, access, flags):
    try:
        with windows_open(path, access, 7, flags):
            raise RuntimeError("The original object allowed a conflicting access")
    except OSError as denial:
        require(denial.winerror == 32, "Original object returned an unexpected sharing result")
        return denial.winerror


def windows_notification_lease(binary, area, rows):
    work = fixture(area, "notification-handle-lease")
    root = work / "source"
    sibling = work / "sibling"
    sibling.mkdir()
    identity = root.stat()
    delete_access, directory_flag = 0x10000, 0x02000000
    with windows_open(root, delete_access, 7, directory_flag):
        pass
    with observe(binary, work) as (subject, _):
        require(subject.command("RELEASE_INPUT_HANDLES") == "INPUT_HANDLES_RELEASED",
                "The Rust subject retained the caller's directory handles")
        complete(subject, root, {})
        denial = windows_sharing_error(root, delete_access, directory_flag)
        baseline = subject.snapshot("STATE")
        (sibling / "media.jpg").write_text("outside the source", encoding="ascii")
        quiet = subject.snapshot(f"WAIT {baseline['generation']} 350")
        require(quiet["generation"] == baseline["generation"], "A sibling directory woke the isolated watch")
        expected = {"nested/media.jpg": "inside the source"}
        (root / "nested/media.jpg").write_text("inside the source", encoding="ascii")
        changed = subject.changed(quiet)
        complete(subject, root, expected)
        stopped = subject.stop(keep_process=True)
        with windows_open(root, delete_access, 7, directory_flag):
            pass
        released = work / "released"
        root.rename(released)
        require(os.path.samestat(released.stat(), identity), "The released directory changed identity")
        require(inventory(released) == (expected, True), "The released original directory has unexpected contents")
        subject.snapshot("STATE")  # The process and joined Watch still exist after the successful rename.
        subject.stop()
    rows["windows-notification-handle-lease"] = {"deleteAccessBeforeWatch": True, "deleteAccessError": denial,
                                                "quietAfterSiblingWrite": quiet, "nativeChange": changed,
                                                "deleteAccessAfterJoin": True, "renamedWhileSubjectAlive": True,
                                                "inventory": expected, "stopMicros": stopped}


def windows_sharing(binary, area, rows):
    work = fixture(area, "native-sharing")
    root = work / "source"
    identity = root.stat()
    sample = root / "original.jpg"
    sample.write_text("original", encoding="ascii")
    expected = {"original.jpg": "original"}
    with observe(binary, work) as (subject, _):
        complete(subject, root, expected)
        delete_error = windows_sharing_error(root, 0x10000, 0x02000000)  # DELETE, directory semantics
        try:
            root.rename(work / "renamed")
        except OSError as denial:
            rename_error = denial.winerror
            require(rename_error in (5, 32), "Unexpected native rename denial")
        else:
            raise RuntimeError("The watch-root lease allowed its own original directory to be renamed")
        require(os.path.samestat(root.stat(), identity), "The held original directory identity changed")
        with windows_open(sample, 0x80000000, 0, 0):  # GENERIC_READ, exclusive sharing
            read_error = windows_sharing_error(sample, 0x80000000, 0)
            failure = failed_scan(subject, root)
            # The CRT used by open() may surface EACCES without the raw Win32 status.
            require(failure["winError"] == 32 or (failure["winError"] is None and failure["errno"] == errno.EACCES),
                    "Expected a read denial on the same exclusively shared file")
        complete(subject, root, expected)
        stopped = subject.stop()
    with windows_open(root, 0x10000, 7, 0x02000000):
        pass
    root.rename(work / "renamed")
    require(os.path.samestat((work / "renamed").stat(), identity), "Original identity changed after lease release")
    rows["windows-original-sharing"] = {"deleteAccessError": delete_error, "renameError": rename_error,
                                        "readAccessError": read_error, "inventoryError": failure,
                                        "recoveredInventory": expected, "renameAfterRelease": True, "stopMicros": stopped}


def linux_overflow_and_loss(binary, area, rows):
    work = fixture(area, "linux-rejected-child")
    (work / "source/regular.jpg").write_text("regular", encoding="ascii")
    with observe(binary, work, "rejected-child") as (subject, ready):
        require(ready["requiresRegistration"] and ready["reasons"] & 32, "Missing OS registration refusal")
        (work / "source/nested/still-watched.jpg").write_text("still watched", encoding="ascii")
        state = subject.changed(ready)
        complete(subject, work / "source", {"regular.jpg": "regular", "nested/still-watched.jpg": "still watched"})
        rows["native-registration-refusal"] = {"state": state, "stopMicros": subject.stop()}
    work = fixture(area, "linux-loss")
    (work / "source/original.jpg").write_text("original", encoding="ascii")
    with observe(binary, work) as (subject, ready):
        complete(subject, work / "source", {"original.jpg": "original"})
        (work / "source").rename(work / "displaced")
        loss = subject.snapshot(f"WAIT {ready['generation']} 5000")
        require(loss["requiresRegistration"] and loss["reasons"] & 16, "Missing moved-root indication")
        failure = failed_scan(subject, work / "source")
        require(failure["errno"] == 2, "Expected the missing configured root to fail its inventory")
        require(inventory(work / "displaced") == ({"original.jpg": "original"}, True), "Displaced original differs")
        rows["native-root-move"] = {"state": loss, "missingRoot": failure, "stopMicros": subject.stop()}
    limit = int(Path("/proc/sys/fs/inotify/max_queued_events").read_text())
    if not 1 <= limit <= 32_768:
        rows["native-kernel-overflow"] = {"status": "unavailable", "hostQueueLimit": limit}
        return
    work = fixture(area, "linux-overflow")
    a, b = work / "source/a", work / "source/b"
    a.write_text("one", encoding="ascii")
    with observe(binary, work, capacity=1) as (subject, ready):
        subject.process.send_signal(signal.SIGSTOP)
        try:
            deadline = time.monotonic() + 3
            status = Path(f"/proc/{subject.process.pid}/status")
            while not re.search(r"^State:\s+T\b", status.read_text(), re.MULTILINE):
                require(time.monotonic() < deadline, "The owned fixture did not stop consuming native events")
                time.sleep(.005)
            for _ in range(limit // 2 + 16):
                a.rename(b)
                b.rename(a)
        finally:
            subject.process.send_signal(signal.SIGCONT)
        deadline = time.monotonic() + 8
        state = ready
        while not state["reasons"] & 8:
            require(time.monotonic() < deadline, "Real inotify overflow marker was not delivered")
            state = subject.snapshot(f"WAIT {state['generation']} 500")
        require(state["requiresRegistration"] and state["queued"] == 1, "Native overflow recovery was not requested")
        complete(subject, work / "source", {"a": "one"})
        rows["native-kernel-overflow"] = {"state": state, "hostQueueLimit": limit, "stopMicros": subject.stop()}


def registration_gap(binary, area, rows):
    work = fixture(area, "pre-registration-change")
    root = work / "source"
    nested = root / "nested"
    original = nested.stat()

    def change_before_arm():
        nested.rename(work / "old-nested")
        nested.mkdir()
        require(not os.path.samestat(original, nested.stat()), "The new directory inherited the retained identity")

    with observe(binary, work, "registration-gap", before_arm=change_before_arm) as (old, initial):
        require(initial["requiresRegistration"], "Linux declared its pre-arm snapshot complete")
        old.snapshot("BEGIN")
        require(not old.finish(), "A Linux inventory was acknowledged before the post-arm identity comparison")
        require(old.command("CONFIRM") == "CONFIRMED 0", "The identifier of the new same-name directory was missed")
        invalid = old.snapshot("STATE")
        require(invalid["requiresRegistration"] and invalid["reasons"] & 32, "The old registration remained eligible")
        (nested / "first.jpg").write_text("found by scan", encoding="utf-8")
        unchanged = old.snapshot(f"WAIT {invalid['generation']} 250")
        require(unchanged["generation"] == invalid["generation"], "The expected uncovered interval was not observed")
        expected = {"nested/first.jpg": "found by scan"}
        complete(old, root, expected)
        require(old.snapshot("STATE")["requiresRegistration"], "A file inventory silently validated stale directory watches")
        with observe(binary, work) as (new, fresh):
            require(not fresh["requiresRegistration"], "Fresh post-arm directory confirmation did not pass")
            complete(new, root, expected)
            old.stop()
            (nested / "next.jpg").write_text("observed natively", encoding="utf-8")
            changed = new.changed(fresh)
            expected["nested/next.jpg"] = "observed natively"
            complete(new, root, expected)
            replacement = nested.stat()
            rows["post-arm-directory-identities"] = {
                "oldIdentity": [original.st_dev, original.st_ino], "newIdentity": [replacement.st_dev, replacement.st_ino],
                "beforeConfirmation": initial, "mismatch": invalid, "uncoveredInterval": unchanged,
                "replacement": fresh, "nativeChangeAfterRenewal": changed, "fullInventory": expected,
                "stopMicros": new.stop()}


def module_inventory(subject):
    line = subject.command("MODULES")
    modules = {}
    bases = [Path(os.environ["SystemRoot"]).resolve()] if os.name == "nt" else [
        Path(p).resolve() for p in ("/usr/lib", "/usr/lib64", "/lib", "/lib64")]
    while line != "MODULES_DONE":
        require(line.startswith("MODULE "), "Unexpected runtime module inventory")
        path = Path(line[7:]).resolve(strict=True)
        require(any(path.is_relative_to(base) for base in bases), "Runtime module outside the OS library roots")
        modules[path.name] = sha(path)
        line = subject.line()
    names = {s.lower() for s in modules}
    require({"kernel32.dll", "ntdll.dll"} <= names if os.name == "nt" else "libc.so.6" in names,
            "The expected host API provider was not loaded")
    return modules


def library_test_program(messages, build, target):
    programs = []
    for line in messages.splitlines():
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        if (item["reason"] == "compiler-artifact" and item["executable"] and item["profile"]["test"]
                and item["target"]["kind"] == ["lib"] and item["target"]["name"] == "native_watch_hints"
                and Path(item["target"]["src_path"]).resolve() == HERE / "src/lib.rs"
                and Path(item["manifest_path"]).resolve() == HERE / "Cargo.toml"
                and item["executable"] in item["filenames"]):
            programs.append(Path(item["executable"]).resolve(strict=True))
    require(len(programs) == 1 and programs[0].is_file() and programs[0].is_relative_to(build / target / "debug"),
            "Expected the single native watch library test executable in the owned build")
    return programs[0]


def windows_loss_trial(program, target, scratch, env, test, report):
    from windows_control import native_loss_evidence

    record = {"programSha256": sha(program), "machine": machine(program, target)}
    require(record == report["libraryTestProgram"], "Native watch test program changed after compilation")
    report["nativeLossTest"] = record
    # The test owns threads only. Python kills and waits for this exact child on timeout
    # before TemporaryDirectory can remove the fixture and the compiled test program.
    outcome = subprocess.run([program, test, "--exact", "--show-output"], cwd=scratch, env=env,
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    record.update(output=outcome.stdout, exitCode=outcome.returncode)
    require(outcome.returncode == 0, "The native watch loss trial failed; see nativeLossTest")
    return native_loss_evidence(outcome.stdout)


def execute(args, output, report):
    exe = ".exe" if os.name == "nt" else ""
    cargo, rustc = TOOLCHAIN / ("cargo" + exe), TOOLCHAIN / ("rustc" + exe)
    report["compiler"] = subprocess.check_output([sys.executable, CHECK, args.target, "--rustc", rustc], text=True).strip()
    sources = [HERE / "Cargo.toml", HERE / "Cargo.lock", HERE / "run.py", HERE / "windows_control.py",
               HERE / "test_windows_control.py",
               *sorted((HERE / "src").glob("*.rs")), PIN, CHECK]
    report["inputs"] = {s.relative_to(ROOT).as_posix(): sha(s) for s in sources}
    report["revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report["sourceChanges"] = subprocess.check_output(["git", "status", "--short", "--", *sources], cwd=ROOT, text=True).splitlines()
    worker = "src/ImmichFolderWatch.Core/Services/FolderWatchWorker.cs"
    original = subprocess.check_output(["git", "show", REFERENCE + ":" + worker], cwd=ROOT)
    report["shippingWorker"] = {"revision": REFERENCE, "sha256": hashlib.sha256(original).hexdigest()}
    report["toolBinaries"] = {p.name: sha(p) for p in (cargo, rustc)}
    report["controlTests"] = subprocess.check_output(
        [sys.executable, "-m", "unittest", "-v", "test_windows_control.py"], cwd=HERE,
        text=True, stderr=subprocess.STDOUT, timeout=30).strip()
    with tempfile.TemporaryDirectory(prefix="native-", dir=output) as scratch:
        area = Path(scratch)
        target_dir = area / "build"
        temporary = area / "tmp"
        temporary.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CARGO_", "RUSTC_", "RUSTFLAGS"))}
        env.update(PATH=str(TOOLCHAIN) + os.pathsep + env["PATH"], RUSTC=str(rustc), CARGO_HOME=str(area / "cargo-home"),
                   CARGO_TARGET_DIR=str(target_dir), CARGO_NET_OFFLINE="true",
                   TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary))
        def run(*cmd):
            return subprocess.check_output([cargo, *cmd], cwd=HERE, env=env, text=True, stderr=subprocess.STDOUT, timeout=150)
        manifest = json.loads(run("metadata", "--frozen", "--format-version", "1"))
        require([(p["name"], p["source"], p["dependencies"]) for p in manifest["packages"]]
                == [("native-watch-hints", None, [])], "Unexpected package or dependency in the frozen graph")
        report["resolvedPackages"] = [p["name"] for p in manifest["packages"]]
        report["fmt"] = run("fmt", "--check").strip()
        report["clippy"] = run("clippy", "--frozen", "--all-targets", "--target", args.target, "--", "-D", "warnings").strip()
        tests = ("test", "--frozen", "--lib", "--target", args.target)
        loss_test = "native::overflow_test::native_buffer_loss_retires_the_watch_and_a_fresh_watch_recovers"
        # Run the Windows queue-loss trial after the other independent observations.
        unit_tests = (*tests, "--", "--skip", loss_test) if os.name == "nt" else tests
        report["unitTests"] = run(*unit_tests).strip()
        messages = run(*tests, "--no-run", "--message-format=json")
        library_test = library_test_program(messages, target_dir, args.target)
        report["libraryTestProgram"] = {"programSha256": sha(library_test), "machine": machine(library_test, args.target)}
        report["releaseBuild"] = run("build", "--frozen", "--release", "--target", args.target).strip()
        binary = target_dir / args.target / "release" / ("native-watch-hints" + exe)
        report["binarySha256"] = sha(binary)
        report["binaryMachine"] = machine(binary, args.target)
        rows = report["observations"] = {}
        work = fixture(area, "runtime")
        if os.name == "nt":
            from windows_control import registration_controls
            report["nativeRegistrationControls"] = registration_controls(work / "source")
        with observe(binary, work) as (subject, _):
            if sys.platform == "linux":
                require(subject.command("DIRFLAGS") == f"DIRFLAGS {os.O_DIRECTORY} {os.O_NOFOLLOW}",
                        "The Rust directory-open flags differ from the native Linux ABI")
                report["directoryFlags"] = {"O_DIRECTORY": os.O_DIRECTORY, "O_NOFOLLOW": os.O_NOFOLLOW}
            report["runtimeModules"] = module_inventory(subject)
            rows["pending-io-at-stop"] = {"stopMicros": subject.stop()}
        if os.name == "nt":
            windows_notification_lease(binary, area, rows)
        mutation_cases(binary, area, rows)
        cancelled_periodic_scan(binary, area, rows)
        queue_and_inventory(binary, area, rows)
        topology(binary, area, rows)
        missing_subtree(binary, area, rows)
        if sys.platform == "linux":
            registration_gap(binary, area, rows)
            linux_overflow_and_loss(binary, area, rows)
        else:
            windows_sharing(binary, area, rows)
            rows["native-kernel-overflow"] = windows_loss_trial(library_test, args.target, area, env, loss_test, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(json.loads(PIN.read_text())["targets"]))
    parser.add_argument("--run-name", help="keep a separate local repeat below the target evidence directory")
    args = parser.parse_args()
    output = ARTIFACTS / args.target
    if args.run_name:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.run_name):
            parser.error("invalid isolated run name")
        output /= args.run_name
    output.mkdir(parents=True, exist_ok=True)
    result = output / "result.json"
    with result.open("x", encoding="utf-8") as reserved:
        reserved.write('{"status":"running"}\n')
    report = {"target": args.target, "system": platform.platform(), "status": "failed"}
    try:
        execute(args, output, report)
        report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            report["commandOutput"] = (error.output or "")[-4000:]
        raise
    finally:
        result.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        (output / "evidence.sha256").write_text(f"{sha(result)}  result.json\n", encoding="ascii", newline="\n")
    print(f"Native watch observations passed for {args.target}. {sha(result)}")


if __name__ == "__main__":
    main()
