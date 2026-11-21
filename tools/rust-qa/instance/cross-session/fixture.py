"""Shared state and read-only Windows identity checks for the marked two-session writer fixture."""

from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time

HERE = Path(__file__).resolve().parent
INSTANCE = HERE.parent
ROOT = INSTANCE.parents[2]
HOSTED = {"RUNNER_ENVIRONMENT": "github-hosted", "GITHUB_ACTIONS": "true",
          "GITHUB_REPOSITORY": "VoltKraft/immich-folder-watch", "GITHUB_REF": "refs/heads/rewrite/rust"}
MARKER = b"synthetic-only\n"
NAME = re.compile(r"IfwQaCross_[a-f0-9]{32}\Z")

spec = importlib.util.spec_from_file_location("ifw_instance_guard", INSTANCE / "run.py")
instance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instance)


def write(path, value):
    temporary = path.with_suffix(".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def wait(area, filename, timeout=45, scheduler=None):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if (area / "abort").exists():
            raise RuntimeError("The controller ended the fixture")
        if (area / filename).is_file():
            return read(area / filename)
        if (area / "worker-done.json").is_file():
            raise RuntimeError(f"Scheduled worker finished before {filename}: {read(area / 'worker-done.json')}")
        if scheduler is not None and scheduler.poll() is not None:
            raise RuntimeError(f"Task supervisor exited {scheduler.returncode} before {filename}")
        time.sleep(.1)
    raise TimeoutError(f"Waiting for {filename}")


def guard_id(profile):
    stat = (profile / "writer.lock").stat()
    if stat.st_size or not stat.st_ino:
        raise RuntimeError("Expected the new empty guard with a Windows filesystem ID")
    return {"volume": str(stat.st_dev), "fileId": str(stat.st_ino)}


def validate_area(area):
    if (not area.is_absolute() or not NAME.fullmatch(area.name)
            or (area / "profile/.ifw-instance-fixture").read_bytes() != MARKER):
        raise ValueError("Expected the unique marked synthetic writer fixture")


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

    def identify(self, pid):
        proc = checked(self.open_process(0x1000, False, pid), "OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)")
        try:
            sid_text, token, session, image_len = c.c_void_p(), w.HANDLE(), w.DWORD(), w.DWORD(32768)
            image = c.create_unicode_buffer(image_len.value)
            checked(self.session(pid, c.byref(session)), "ProcessIdToSessionId")
            checked(self.image(proc, 0, image, c.byref(image_len)), "QueryFullProcessImageNameW")
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
            finally:
                self.close(token)
        finally:
            self.close(proc)
        if token_session != session.value:
            raise RuntimeError("Token and ProcessIdToSessionId disagree")
        return sid, Path(image.value), {"pid": pid, "sessionId": session.value, "tokenSessionId": token_session,
                                        "image": Path(image.value).name, "elevated": elevated,
                                        "elevationType": elevation_type,
                                        "sidSha256": hashlib.sha256(sid.encode("ascii")).hexdigest()}


def verified_process(accounts, pid, sid, exe, session=None):
    actual, image, receipt = accounts.identify(pid)
    if actual != sid or image.resolve() != exe.resolve() or (session is not None and receipt["sessionId"] != session):
        raise RuntimeError("The writer process token, executable or native session differs from its owner")
    return receipt


@contextmanager
def writer(accounts, exe, profile, env, sid, session):
    with instance.Child([exe, "writer", profile, sid, "0"], profile, env) as child:
        receipt = verified_process(accounts, child.proc.pid, sid, exe, session)
        yield child, receipt


def release(child):
    child.send("RELEASE")
    child.expect("WRITER_RELEASED")
    child.success()
