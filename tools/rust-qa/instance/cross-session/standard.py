"""Read effective Windows user authority, and start only the fixed fixture writer."""

from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
import re
import stat
import queue
import subprocess
import threading

from fixture import bind, checked, guard_id, instance, verified_process


# Local administrative/operator aliases and the local-account administrator membership marker.
ADMIN_GROUPS = {"S-1-5-114", *("S-1-5-32-" + str(r) for r in (544, 547, 548, 549, 550, 551, 556))}
STANDARD_PRIVILEGES = {"SeChangeNotifyPrivilege", "SeShutdownPrivilege", "SeUndockPrivilege",
                       "SeIncreaseWorkingSetPrivilege", "SeTimeZonePrivilege"}


class Group(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("flags", w.DWORD)]


class Groups(c.Structure):
    _fields_ = [("count", w.DWORD), ("first", Group)]


class Luid(c.Structure):
    _fields_ = [("low", w.DWORD), ("high", w.LONG)]


class Privilege(c.Structure):
    _fields_ = [("id", Luid), ("flags", w.DWORD)]


def sid_string(accounts, ptr):
    result = c.c_void_p()
    checked(accounts.sid_string(ptr, c.byref(result)), "ConvertSidToStringSidW")
    try:
        return c.wstring_at(result.value)
    finally:
        accounts.free(result)


def restriction_flag(buffer):
    """Read TokenHasRestrictions on hosts returning BOOLEAN or DWORD."""
    value = bytes(buffer)
    if len(value) not in (1, 4):
        raise ValueError("Unexpected TokenHasRestrictions result size")
    return int.from_bytes(value, "little") != 0


def authority(accounts, token):
    advapi = c.WinDLL("advapi32", use_last_error=True)
    lookup = bind(advapi, "LookupPrivilegeNameW", w.BOOL, w.LPCWSTR, c.POINTER(Luid), w.LPWSTR, c.POINTER(w.DWORD))
    def groups(kind):
        members = accounts.token_info(token, kind)
        count = w.DWORD.from_buffer(members).value
        if not count:
            return []
        if Groups.first.offset + count * c.sizeof(Group) > len(members):
            raise ValueError("Invalid group count")
        return sorted((sid_string(accounts, group.sid), group.flags)
                      for group in (Group * count).from_buffer(members, Groups.first.offset))

    members, restrictions, capabilities = (groups(kind) for kind in (2, 11, 30))
    enabled_admin = deny_only_admin = 0
    for name, flags in members:
        if name in ADMIN_GROUPS:
            enabled_admin += bool(flags & 4 and not flags & 16)
            deny_only_admin += bool(flags & 16)
    privs = accounts.token_info(token, 3)
    n = w.DWORD.from_buffer(privs).value
    offset = c.sizeof(w.DWORD)
    if offset + n * c.sizeof(Privilege) > len(privs):
        raise ValueError("Invalid privilege count")
    outside = enabled_outside = 0
    privileges = []
    for item in (Privilege * n).from_buffer(privs, offset):
        name, length = c.create_unicode_buffer(256), w.DWORD(256)
        checked(lookup(None, c.byref(item.id), name, c.byref(length)), "LookupPrivilegeNameW")
        # USED_FOR_ACCESS records history and does not grant additional authority.
        privileges.append((name.value, item.flags & 7))
        if name.value not in STANDARD_PRIVILEGES:
            outside += 1
            enabled_outside += bool(item.flags & 2)
    label = sid_string(accounts, c.c_void_p.from_buffer(accounts.token_info(token, 25)))
    prefix = "S-1-16-"
    if not label.startswith(prefix) or not label[len(prefix):].isdigit():
        raise ValueError("Unknown Windows token integrity authority")
    def scalar(kind):
        return w.DWORD.from_buffer(accounts.token_info(token, kind)).value
    digest = hashlib.sha256(json.dumps([members, restrictions, capabilities, sorted(privileges)],
                                       ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return dict(authorityInventorySha256=digest, enabledAdministrativeGroups=enabled_admin, denyOnlyAdministrativeGroups=deny_only_admin,
                privilegeCount=n, privilegesOutsideStandard=outside, enabledOutsideStandard=enabled_outside,
                integrityRid=int(label[len(prefix):]), tokenType=scalar(8), uiAccess=bool(scalar(26)),
                capabilityCount=len(capabilities), hasRestrictions=restriction_flag(accounts.token_info(token, 21)))


def qualifies(receipt):
    return (receipt.get("elevated") is False and receipt.get("tokenType") == 1
            and receipt.get("elevationType") in (1, 3)
            and receipt.get("enabledAdministrativeGroups") == 0 and receipt.get("privilegesOutsideStandard") == 0
            and receipt.get("enabledOutsideStandard") == 0 and receipt.get("uiAccess") is False
            and receipt.get("capabilityCount") == 0 and receipt.get("integrityRid") in (0, 4096, 8192))


AMBIENT = "hosted-S4U-ambient"
STANDARD = "hosted-S4U"
EXISTING = "existing-standard-sessions"


def unchanged_authority(actual, parent):
    # Compare each process with its own bootstrap or child in the same session.
    # Keep the private SID/attribute and privilege lists behind their deterministic digest.
    fields = ("sidSha256", "sessionId", "tokenSessionId", "elevated", "elevationType",
              "integrityRid", "tokenType", "uiAccess", "capabilityCount", "hasRestrictions",
              "privilegeCount", "privilegesOutsideStandard", "enabledOutsideStandard",
              "enabledAdministrativeGroups", "denyOnlyAdministrativeGroups", "authorityInventorySha256")
    return (isinstance(actual.get("authorityInventorySha256"), str)
            and re.fullmatch("[0-9a-f]{64}", actual["authorityInventorySha256"]) is not None
            and actual.get("tokenType") == 1 and actual.get("tokenSessionId") == actual.get("sessionId")
            and all(key in actual and key in parent and actual[key] == parent[key] for key in fields))


def required_authority(mode, actual, parent):
    if mode == AMBIENT:
        return unchanged_authority(actual, parent)
    if mode in (STANDARD, EXISTING):
        return qualifies(actual)
    raise ValueError("Unknown native writer measurement mode")


class ThreadEntry(c.Structure):
    _fields_ = [(name, w.DWORD) for name in ("size", "usage", "tid", "pid", "base", "delta", "flags")]


class JobLimits(c.Structure):
    _fields_ = [("processTime", c.c_int64), ("jobTime", c.c_int64), ("flags", w.DWORD),
                ("minimumWs", c.c_size_t), ("maximumWs", c.c_size_t), ("processes", w.DWORD),
                ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD),
                ("io", c.c_uint64 * 6), ("memory", c.c_size_t * 4)]


class FixedWriter(instance.Child):
    def __init__(self, area, sid, env):
        self.proc = subprocess.Popen([area / "build/instance.exe", "writer", area / "profile", sid, "0"],
                                     cwd=area / "profile", env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
                                     creationflags=4)  # CREATE_SUSPENDED, ordinary inherited process token
        self.job = None
        kernel = c.WinDLL("kernel32", use_last_error=True)
        self.close_job = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        try:
            create = bind(kernel, "CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
            limit = bind(kernel, "SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
            assign = bind(kernel, "AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
            self.job = checked(create(None, None), "CreateJobObjectW(owned Rust writer)")
            limits = JobLimits()
            limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            checked(limit(self.job, 9, c.byref(limits), c.sizeof(limits)), "SetInformationJobObject")
            checked(assign(self.job, int(self.proc._handle)), "AssignProcessToJobObject(owned suspended Rust writer)")
            self.events = queue.Queue()
            self.reader = threading.Thread(target=self.read_output, daemon=True)
            self.reader.start()
        except BaseException:
            if self.job:
                self.close_job(self.job)
            self.proc.kill()
            self.proc.wait(timeout=10)
            self.proc.stdin.close()
            self.proc.stdout.close()
            raise

    def __exit__(self, *exc):
        try:
            super().__exit__(*exc)
        finally:
            self.close_job(self.job)

    def resume(self):
        if self.proc.poll() is not None:
            raise RuntimeError("The owned suspended writer exited")
        kernel = c.WinDLL("kernel32", use_last_error=True)
        snapshot = bind(kernel, "CreateToolhelp32Snapshot", w.HANDLE, w.DWORD, w.DWORD)
        first = bind(kernel, "Thread32First", w.BOOL, w.HANDLE, c.POINTER(ThreadEntry))
        get_next = bind(kernel, "Thread32Next", w.BOOL, w.HANDLE, c.POINTER(ThreadEntry))
        open_thread = bind(kernel, "OpenThread", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        owner = bind(kernel, "GetProcessIdOfThread", w.DWORD, w.HANDLE)
        resume = bind(kernel, "ResumeThread", w.DWORD, w.HANDLE)
        close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        snap = snapshot(4, 0)
        if snap in (None, c.c_void_p(-1).value):
            raise OSError(c.get_last_error(), "CreateToolhelp32Snapshot(threads)")
        try:
            row, matches = ThreadEntry(), []
            row.size = c.sizeof(row)
            ok = first(snap, c.byref(row))
            while ok:
                if row.pid == self.proc.pid:
                    matches.append(row.tid)
                row.size = c.sizeof(row)
                ok = get_next(snap, c.byref(row))
            if len(matches) != 1:
                raise RuntimeError("Expected only the initial thread of the owned suspended writer")
            thread = checked(open_thread(0x0802, False, matches[0]), "OpenThread(owned writer)")
            try:
                if owner(thread) != self.proc.pid or resume(thread) != 1:
                    raise RuntimeError("Could not resume exactly the original writer thread")
            finally:
                close(thread)
        finally:
            close(snap)


@contextmanager
def fixed_writer(area, accounts, sid, parent, env, config):
    exe, profile = area / "build/instance.exe", area / "profile"
    if guard_id(profile) != config["guard"]:
        raise RuntimeError("The pre-created guard changed")
    keys = ("SYSTEMROOT", "WINDIR", "RUNNER_ENVIRONMENT", "GITHUB_ACTIONS", "GITHUB_REPOSITORY",
            "GITHUB_REF", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP")
    selected = {key: value for key, value in env.items() if key.upper() in keys}
    import msvcrt
    kernel = c.WinDLL("kernel32", use_last_error=True)
    create = bind(kernel, "CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE)
    image = create(str(exe), 0x80000000, 1, None, 3, 0x00200000, None)  # Read only, deny replacement/write.
    if image in (None, c.c_void_p(-1).value):
        raise OSError(c.get_last_error(), "CreateFileW(expected Rust image)")
    try:
        fd = msvcrt.open_osfhandle(image, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        accounts.close(image)
        raise
    with os.fdopen(fd, "rb") as pinned:
        info = os.fstat(pinned.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or hashlib.file_digest(pinned, "sha256").hexdigest() != config["binarySha256"]):
            raise RuntimeError("The pinned Rust executable is not the reviewed fixture image")
        with FixedWriter(area, sid, selected) as child:
            receipt = verified_process(accounts, child.proc.pid, sid, exe, parent["sessionId"])
            if not required_authority(config["mode"], receipt, parent):
                raise RuntimeError("The suspended Rust writer does not have the required authority for this trial")
            yield child, receipt
