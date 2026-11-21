"""Win32 metrics and profile ownership for the two native Windows desktop subjects."""
import contextlib
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid


def bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn


def checked(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


def known_folder(guid):
    shell = c.OleDLL("shell32")
    get = bind(shell, "SHGetKnownFolderPath", w.LONG, c.c_void_p, w.DWORD, w.HANDLE, c.POINTER(c.c_void_p))
    free = bind(c.WinDLL("ole32"), "CoTaskMemFree", None, c.c_void_p)
    out = c.c_void_p()
    status = get(c.create_string_buffer(uuid.UUID(guid).bytes_le), 0, None, c.byref(out))
    if status or not out:
        raise OSError(f"Windows known folder unavailable: {status}")
    try:
        return Path(c.wstring_at(out))
    finally:
        free(out)


def hosted():
    return (os.name == "nt" and os.getenv("GITHUB_ACTIONS") == "true"
            and os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and os.getenv("RUNNER_OS") == "Windows")


def absent(path):
    if os.path.lexists(path):
        raise ValueError(f"Expected an unused disposable runner path: {path.name}")


@contextlib.contextmanager
def wpf_profile(media, endpoint):
    if not hosted():
        raise ValueError("The genuine WPF host requires the disposable GitHub-hosted Windows profile")
    product = known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091") / "Immich Folder Watch"
    shortcut = known_folder("b97d20bb-f46a-4c97-ba10-5e3608430854") / "Immich Folder Watch.lnk"
    absent(shortcut)
    absent(product)
    product.mkdir()
    token = uuid.uuid4().hex
    marker = product / (".rw02-owned-" + token)
    marker.write_text(token, encoding="ascii")
    try:
        # YAML single-quoted scalars retain Windows backslashes.
        path = str(media).replace("'", "''")
        config = (f'immich:\n  serverApiUrl: "{endpoint}/api"\n  apiKey: "synthetic-benchmark"\n'
                  '  allowInsecureHttp: true\nwatch:\n  sources:\n'
                  f"    - path: '{path}'\n      syncMode: uploadNew\n      includeSubdirectories: true\n"
                  '      deleteAfterUpload: false\n      extensions: [".jpg"]\nlogging:\n'
                  '  target: file\n  level: Information\n  logDirectory: engine-logs\n')
        (product / "config.yaml").write_text(config, encoding="utf-8")
        yield product
    finally:
        if product.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or marker.read_text(encoding="ascii") != token:
            raise ValueError("Disposable product directory ownership changed; refusing cleanup")
        shutil.rmtree(product)
        absent(shortcut)


def sid():
    result = subprocess.check_output(["whoami.exe", "/user", "/fo", "csv", "/nh"], encoding="ascii", errors="replace")
    matches = re.findall(r'\bS-1-[0-9]+(?:-[0-9]+)+\b', result)
    if len(matches) != 1:
        raise ValueError("Cannot determine the disposable account SID")
    return matches[0]


class Memory(c.Structure):
    _fields_ = [("cb", w.DWORD), ("faults", w.DWORD),
                *[(name, c.c_size_t) for name in ("peak_working", "working", "peak_paged", "paged",
                                                  "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]]


class Win32:
    def __init__(self):
        self.kernel = k = c.WinDLL("kernel32", use_last_error=True)
        self.open = bind(k, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.close = bind(k, "CloseHandle", w.BOOL, w.HANDLE)
        self.times = bind(k, "GetProcessTimes", w.BOOL, w.HANDLE, *[c.POINTER(w.FILETIME)] * 4)
        self.memory = bind(k, "K32GetProcessMemoryInfo", w.BOOL, w.HANDLE, c.POINTER(Memory), w.DWORD)
        self.counter = bind(k, "QueryPerformanceCounter", w.BOOL, c.POINTER(c.c_longlong))
        freq = c.c_longlong()
        checked(bind(k, "QueryPerformanceFrequency", w.BOOL, c.POINTER(c.c_longlong))(c.byref(freq)))
        self.frequency = freq.value
        self.create_file = bind(k, "CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                w.DWORD, w.DWORD, w.HANDLE)
        self.pipe_pid = bind(k, "GetNamedPipeServerProcessId", w.BOOL, w.HANDLE, c.POINTER(w.ULONG))
        self.write = bind(k, "WriteFile", w.BOOL, w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p)
        self.wow = bind(k, "IsWow64Process2", w.BOOL, w.HANDLE, c.POINTER(w.WORD), c.POINTER(w.WORD))

    def clock(self):
        now = c.c_longlong()
        checked(self.counter(c.byref(now)))
        return now.value

    def machine(self, handle):
        proc, native = w.WORD(), w.WORD()
        checked(self.wow(handle, c.byref(proc), c.byref(native)))
        return proc.value or native.value, native.value

    def ensure_no_primary(self, user_sid):
        fn = bind(self.kernel, "OpenMutexW", w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
        mutex = fn(0x00100000, False, "Local\\ImmichFolderWatch-" + user_sid)
        if mutex:
            self.close(mutex)
            raise ValueError("The shipping single-instance mutex already exists")
        if c.get_last_error() != 2:
            raise c.WinError(c.get_last_error())

    def usage(self, handle):
        creation, end, kernel, user = [w.FILETIME() for _ in range(4)]
        checked(self.times(handle, *map(c.byref, (creation, end, kernel, user))))
        ticks = sum((part.dwHighDateTime << 32) + part.dwLowDateTime for part in (kernel, user))
        data = Memory()
        data.cb = c.sizeof(data)
        checked(self.memory(handle, c.byref(data), data.cb))
        return ticks / 10_000_000, data.working / 1_048_576

    def activate_wpf(self, user_sid, pid):
        path = "\\\\.\\pipe\\ifw-" + user_sid
        until = time.monotonic() + 2
        while True:
            handle = self.create_file(path, 0x40000000, 0, None, 3, 0, None)
            if handle != c.c_void_p(-1).value:
                break
            if c.get_last_error() not in (2, 231) or time.monotonic() >= until:
                raise c.WinError(c.get_last_error())
            time.sleep(.002)
        try:
            owner, count = w.ULONG(), w.DWORD()
            checked(self.pipe_pid(handle, c.byref(owner)))
            if owner.value != pid:
                raise ValueError("The named pipe belongs to a different process")
            payload = b"SHOW_GUI"
            checked(self.write(handle, payload, len(payload), c.byref(count), None))
            if count.value != len(payload):
                raise OSError("Incomplete WPF activation signal")
        finally:
            self.close(handle)
