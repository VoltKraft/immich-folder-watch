"""Shared state and read-only Windows identity checks for the marked two-session writer fixture."""

import ctypes as c
from ctypes import wintypes as w
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import time

HERE = Path(__file__).resolve().parent
INSTANCE = HERE.parent
ROOT = INSTANCE.parents[2]
HOSTED = {"RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_ACTIONS": "true",
          "GITHUB_REPOSITORY": "VoltKraft/immich-folder-watch", "GITHUB_REF": "refs/heads/rewrite/rust"}
MARKER = b"synthetic-only\n"
NAME = re.compile(r"IfwQaCross_[a-f0-9]{32}\Z")
SID_IN_TEXT = re.compile(r"\bS-\d+-(?:\d+-)*\d+\b", re.I)

spec = importlib.util.spec_from_file_location("ifw_instance_guard", INSTANCE / "run.py")
instance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instance)


def write(path, value):
    temporary = path.with_suffix(".writing")
    temporary.write_text(SID_IN_TEXT.sub("[account ID]", json.dumps(value, ensure_ascii=False, indent=2)) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def wait(area, filename, timeout=45, scheduler=None, *, collect_bootstrap=False):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if (area / "abort").exists():
            raise RuntimeError("The controller ended the fixture")
        if (area / filename).is_file():
            return read(area / filename)
        for name in ("worker-done.json", "scheduled-done.json", "original-done.json", "original-bootstrap-done.json"):
            if not collect_bootstrap and (area / name).is_file() and not read(area / name).get("passed"):
                raise RuntimeError(f"An isolated participant failed before {filename}, see {name}")
        if scheduler is not None and scheduler.poll() is not None:
            raise RuntimeError(f"Task supervisor exited {scheduler.returncode} before {filename}")
        time.sleep(.1)
    raise TimeoutError(f"Waiting for {filename}")


def guard_id(profile):
    info = (profile / "writer.lock").lstat()
    if (not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_size or not info.st_ino or info.st_nlink != 1):
        raise RuntimeError("Expected the new empty guard with a Windows filesystem ID")
    return {"volume": str(info.st_dev), "fileId": str(info.st_ino)}


def validate_area(area):
    marker = area / "profile/.ifw-instance-fixture"
    if not area.is_absolute() or not NAME.fullmatch(area.name):
        raise ValueError("Expected the unique marked synthetic writer fixture")
    objects = (area, area / "profile", marker, area / "profile/writer.lock", area / "build",
               area / "build/instance.exe", area / "controller.json")
    if any(getattr(p.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or p.is_symlink() for p in objects):
        raise ValueError("The synthetic fixture contains a reparse point")
    if marker.stat().st_size != len(MARKER) or marker.read_bytes() != MARKER:
        raise ValueError("Expected the original synthetic marker")


def subject_env(area, job):
    if job != HOSTED:
        raise ValueError("The original job identity is outside the hosted rewrite assessment")
    private = area / "synthetic-home"
    return {**os.environ, **job, "USERPROFILE": str(private), "HOME": str(private),
            "APPDATA": str(private / "roaming"), "LOCALAPPDATA": str(private / "local"),
            "TEMP": str(private / "tmp"), "TMP": str(private / "tmp"), "DOTNET_CLI_HOME": str(private),
            "NUGET_PACKAGES": str(private / "packages"), "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false", "DOTNET_ADD_GLOBAL_TOOLS_TO_PATH": "0",
            "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1"}


def bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn


def checked(value, api):
    if not value:
        raise OSError(c.get_last_error(), api)
    return value


class Accounts:
    def __init__(self):
        k = c.WinDLL("kernel32", use_last_error=True)
        a = c.WinDLL("advapi32", use_last_error=True)
        self.times = bind(k, "GetProcessTimes", w.BOOL, w.HANDLE, *([c.POINTER(w.FILETIME)] * 4))
        self.wait_process = bind(k, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        self.open_process = bind(k, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.session = bind(k, "ProcessIdToSessionId", w.BOOL, w.DWORD, c.POINTER(w.DWORD))
        self.image = bind(k, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD))
        self.open_token = bind(a, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, c.POINTER(w.HANDLE))
        self.query = bind(a, "GetTokenInformation", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD))
        self.sid_string = bind(a, "ConvertSidToStringSidW", w.BOOL, c.c_void_p, c.POINTER(c.c_void_p))
        self.free = bind(k, "LocalFree", c.c_void_p, c.c_void_p)
        self.close = bind(k, "CloseHandle", w.BOOL, w.HANDLE)

    def token_info(self, token, kind):
        needed = w.DWORD()
        self.query(token, kind, None, 0, c.byref(needed))
        if not 0 < needed.value <= 65536:
            raise OSError(c.get_last_error(), "GetTokenInformation(size)")
        buf = c.create_string_buffer(needed.value)
        checked(self.query(token, kind, buf, len(buf), c.byref(needed)), "GetTokenInformation")
        return buf

    def identify(self, pid, *, expected_image=None, expected_session=None, expected_created=None):
        if pid != os.getpid() and (expected_image is None or expected_session is None):
            raise ValueError("A different process requires its fixed expected image and native session")
        proc = checked(self.open_process(0x1000, False, pid), "OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)")
        try:
            sid_text, token, session, image_len = c.c_void_p(), w.HANDLE(), w.DWORD(), w.DWORD(32768)
            image = c.create_unicode_buffer(image_len.value)
            stamp, end, kernel, user_time = (w.FILETIME() for _ in range(4))
            checked(self.times(proc, c.byref(stamp), c.byref(end), c.byref(kernel), c.byref(user_time)), "GetProcessTimes")
            created = (stamp.dwHighDateTime << 32) | stamp.dwLowDateTime
            checked(self.session(pid, c.byref(session)), "ProcessIdToSessionId")
            checked(self.image(proc, 0, image, c.byref(image_len)), "QueryFullProcessImageNameW")
            if ((expected_image is not None and Path(image.value).resolve() != expected_image.resolve())
                    or (expected_session is not None and session.value != expected_session)
                    or (expected_created is not None and created != expected_created)):
                raise RuntimeError("The process does not match the fixture image, session or creation time")
            checked(self.open_token(proc, 8, c.byref(token)), "OpenProcessToken(TOKEN_QUERY)")
            try:
                user = self.token_info(token, 1)
                checked(self.sid_string(c.c_void_p.from_buffer(user), c.byref(sid_text)), "ConvertSidToStringSidW")
                try:
                    sid = c.wstring_at(sid_text.value)
                finally:
                    self.free(sid_text)
                token_session = w.DWORD.from_buffer(self.token_info(token, 12)).value
                elevated = bool(w.DWORD.from_buffer(self.token_info(token, 20)).value)
                elevation_type = w.DWORD.from_buffer(self.token_info(token, 18)).value
                from standard import authority
                effective = authority(self, token)
            finally:
                self.close(token)
        finally:
            self.close(proc)
        if token_session != session.value:
            raise RuntimeError("Token and ProcessIdToSessionId disagree")
        return sid, Path(image.value), {"pid": pid, "sessionId": session.value, "tokenSessionId": token_session,
                                        "image": Path(image.value).name, "created100ns": created, "elevated": elevated,
                                        "elevationType": elevation_type, **effective,
                                        "sidSha256": hashlib.sha256(sid.encode("ascii")).hexdigest()}


def participants_exited(area):
    accounts = Accounts()
    checked_processes = set()
    receipts = []
    for role in ("original", "scheduled"):
        receipts.extend(area / (role + suffix) for suffix in ("-bootstrap.json", "-console-helper.json", "-attempt.json"))
    for name in ("original-hold", "scheduled-refuse", "scheduled-hold", "original-refuse", "original-last"):
        receipts.append(area / (name + "-created.json"))
    for path in receipts:
        if not path.is_file():
            continue
        identity = read(path)
        process_key = (identity["pid"], identity["created100ns"])
        if process_key in checked_processes:
            continue
        proc = accounts.open_process(0x100000 | 0x1000, False, identity["pid"])
        if not proc:
            if c.get_last_error() != 87:
                raise OSError(c.get_last_error(), "OpenProcess(owned participant exit)")
        else:
            try:
                stamp, ended, kernel, user_time = (w.FILETIME() for _ in range(4))
                checked(accounts.times(proc, c.byref(stamp), c.byref(ended), c.byref(kernel), c.byref(user_time)), "GetProcessTimes")
                created = (stamp.dwHighDateTime << 32) | stamp.dwLowDateTime
                if created == identity["created100ns"] and accounts.wait_process(proc, 45000) != 0:
                    raise RuntimeError("Could not establish exit of an owned test participant")
            finally:
                accounts.close(proc)
        checked_processes.add(process_key)
    for role in ("original", "scheduled"):
        attempt = area / (role + "-attempt.json")
        launched = area / (role + "-basic-user.json")
        if launched.is_file() and not attempt.is_file():
            launch = read(launched)
            started = launch["launched"]
            claim = area / (role + "-console-launch.claim")
            if claim.exists():
                code = read(claim)["exitCode"] if claim.stat().st_size else None
                if type(code) is not int or launch.get("launchExit", code) != code:
                    raise RuntimeError("The fixed console launch has no verifiable utility exit or participant identity")
                started = code == 0
            if started and not (area / (role + "-done.json")).is_file():
                raise RuntimeError("The named Basic User action has no verifiable shutdown receipt")
    return len(checked_processes)


def verified_process(accounts, pid, sid, exe, session, created=None):
    actual, _, receipt = accounts.identify(pid, expected_image=exe, expected_session=session, expected_created=created)
    if actual != sid:
        raise RuntimeError("The writer process token, executable or native session differs from its owner")
    return receipt


def release(child):
    child.send("RELEASE")
    child.expect("WRITER_RELEASED")
    child.success()
