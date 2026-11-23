"""Win32 metrics and profile ownership for the two native Windows desktop subjects."""
import contextlib
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import re
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


class CleanupUnconfirmed(RuntimeError):
    """The recorder cannot safely remove the fixture or advance to the next subject."""

    @classmethod
    def in_chain(cls, error):
        seen = set()
        while error is not None and id(error) not in seen:
            if isinstance(error, cls):
                return True
            seen.add(id(error))
            error = error.__cause__ or error.__context__
        return False


def finish_owned_trace(helper, observer, area, etl, name, timeout):
    """Drain this controller, then verify its uniquely identified logger has gone away."""
    try:
        if not helper.stdin.closed:
            helper.stdin.close()
        try:
            helper.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            helper.kill()
            helper.wait(timeout=10)
            raise
    finally:
        # Close the race between stopping a stuck controller and reading its logger by name.
        try:
            if helper.poll() is None:
                helper.kill()
                helper.wait(timeout=10)
            subprocess.run([observer, "--stop-owned", etl, name], cwd=area, stdin=subprocess.DEVNULL, check=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise CleanupUnconfirmed("Could not confirm the owned ETW controller exit and session removal") from exc


def start_owned_subject(stack, api, exe, area, env, log, rust, stop_subject):
    job = api.new_job()
    stack.callback(api.close, job)
    started = api.clock()
    proc = subprocess.Popen([exe], cwd=area, env=env, stdin=subprocess.PIPE if rust else subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=4)  # CREATE_SUSPENDED
    try:
        api.assign_suspended(job, proc, exe)
    except BaseException:
        try:
            try:
                proc.kill()
                proc.wait(timeout=10)
                if not api.wait_job_empty(job, 5):
                    raise TimeoutError("Suspended subject remained active after assignment failure")
            except (OSError, TimeoutError, subprocess.SubprocessError) as exc:
                raise CleanupUnconfirmed("Could not reap the suspended subject after a start failure") from exc
        finally:
            if proc.stdin:
                proc.stdin.close()
        raise

    def finish():
        forced = False
        try:
            stop_subject(proc, rust)
        finally:
            try:
                if not api.wait_job_empty(job, 1):
                    forced = True
                    checked(api.terminate_job(job, 1))
                    if not api.wait_job_empty(job, 10):
                        raise TimeoutError("The owned process job still has active children")
                proc.wait(timeout=5)
            except (OSError, TimeoutError, subprocess.SubprocessError) as exc:
                raise CleanupUnconfirmed("Could not confirm the owned process job is empty") from exc
            finally:
                if proc.stdin:
                    proc.stdin.close()
        if forced:
            raise RuntimeError("The subject required forced descendant cleanup")

    stack.callback(finish)
    proc.benchmark_start_qpc = started
    return proc


@contextlib.contextmanager
def pin_path(api, path, directory):
    handle = api.path_handle(path, directory)
    try:
        attributes, identity = api.file_info(handle)
        if attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | 0x40) or bool(attributes & 0x10) != directory:
            raise ValueError(f"Unexpected type for pinned benchmark object {path.name}")
        yield handle, identity
    finally:
        checked(api.close(handle))


def pin_new_marker(stack, api, path, token):
    data = token.encode("ascii")
    if not re.fullmatch(b"[0-9a-f]{32}", data):
        raise ValueError("Expected a fresh 128-bit marker")
    with contextlib.ExitStack() as transition:
        with contextlib.ExitStack() as writer:
            created = api.create_file(str(path), 0xc0000000, 1, None, 1, 0x00200000, None)  # CREATE_NEW
            if created == c.c_void_p(-1).value:
                raise c.WinError(c.get_last_error())
            writer.callback(api.close, created)
            _, original = api.file_info(created)
            written = w.DWORD()
            checked(api.write(created, data, len(data), c.byref(written), None))
            if written.value != len(data):
                raise OSError("Incomplete ownership marker")
            # This reader permits the creating writer to finish, and denies name deletion throughout.
            reader = api.path_handle(path, False, allow_writer=True)
            transition.callback(api.close, reader)
            if api.file_info(reader)[1] != original:
                raise ValueError("The original marker identity changed during creation")
        _, sealed = stack.enter_context(pin_path(api, path, False))
        if sealed != original or path.read_bytes() != data:
            raise ValueError("The read-only marker differs from its creation handle")
        return original


def remove_owned_contents(api, path):
    for entry in path.iterdir():
        # The parent stays pinned. OPEN_REPARSE_POINT makes deletion of any link operate on the link itself.
        handle = api.path_handle(entry, True, delete=True)
        try:
            attributes, _ = api.file_info(handle)
            if attributes & 0x10 and not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                remove_owned_contents(api, entry)
            api.delete_handle(handle)
        finally:
            checked(api.close(handle))


@contextlib.contextmanager
def owned_directory(api, parent, name):
    path = parent / name
    with pin_path(api, parent, True) as (parent_handle, _):
        handle = api.create_child_directory(parent_handle, name)
        expected, cleanup, emptied = None, True, False
        try:
            _, expected = api.file_info(handle)
            try:
                yield path
            except BaseException as exc:
                cleanup = not CleanupUnconfirmed.in_chain(exc)
                if not cleanup and not isinstance(exc, CleanupUnconfirmed):
                    raise CleanupUnconfirmed("A previous cleanup could not confirm the fixture is idle") from exc
                raise
            finally:
                if cleanup:
                    remove_owned_contents(api, path)
                    emptied = True
        finally:
            checked(api.close(handle))
            # A DELETE handle would prevent the subject's own deny-delete leases. Reopen only this
            # empty directory, compare its original volume/file ID, and delete by that final handle.
            if expected is not None and emptied:
                final = api.path_handle(path, True, delete=True)
                try:
                    attributes, found = api.file_info(final)
                    if found != expected or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        raise ValueError("The disposable directory identity changed before removal")
                    api.delete_handle(final)
                finally:
                    checked(api.close(final))


def synthetic_config(media, endpoint):
    # YAML single-quoted scalars retain Windows backslashes for both subjects.
    path = str(media).replace("'", "''")
    return (f'immich:\n  serverApiUrl: "{endpoint}/api"\n  apiKey: "synthetic-benchmark"\n'
            '  allowInsecureHttp: true\nwatch:\n  sources:\n'
            f"    - path: '{path}'\n      syncMode: uploadNew\n      includeSubdirectories: true\n"
            '      deleteAfterUpload: false\n      extensions: [".jpg"]\n')


@contextlib.contextmanager
def wpf_profile(media, endpoint):
    if not hosted():
        raise ValueError("The genuine WPF host requires the disposable GitHub-hosted Windows profile")
    product = known_folder("f1b32785-6fba-4fcf-9d55-7b8e7f157091") / "Immich Folder Watch"
    shortcut = known_folder("b97d20bb-f46a-4c97-ba10-5e3608430854") / "Immich Folder Watch.lnk"
    absent(shortcut)
    absent(product)
    api = Win32()
    with owned_directory(api, product.parent, product.name):
        token = uuid.uuid4().hex
        marker = product / (".rw02-owned-" + token)
        with contextlib.ExitStack() as pins:
            pin_new_marker(pins, api, marker, token)
            config = synthetic_config(media, endpoint) + 'logging:\n  target: file\n  level: Information\n  logDirectory: engine-logs\n'
            (product / "config.yaml").write_text(config, encoding="utf-8")
            yield product
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


class ProcessEntry(c.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD), ("heap", c.c_size_t),
                ("module", w.DWORD), ("threads", w.DWORD), ("parent", w.DWORD), ("priority", w.LONG),
                ("flags", w.DWORD), ("image", w.WCHAR * 260)]


class ThreadEntry(c.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("tid", w.DWORD), ("owner", w.DWORD),
                ("priority", w.LONG), ("delta_priority", w.LONG), ("flags", w.DWORD)]


class JobLimits(c.Structure):
    _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", c.c_uint32),
                ("minimum_ws", c.c_size_t), ("maximum_ws", c.c_size_t), ("processes", c.c_uint32),
                ("affinity", c.c_size_t), ("priority", c.c_uint32), ("scheduling", c.c_uint32),
                ("io_counters", c.c_uint64 * 6), ("memory_limits", c.c_size_t * 4)]


class JobAccounting(c.Structure):
    _fields_ = [("times", c.c_int64 * 4), ("faults", c.c_uint32), ("total", c.c_uint32),
                ("active", c.c_uint32), ("terminated", c.c_uint32)]


class FileInformation(c.Structure):
    _fields_ = [("attributes", c.c_uint32), ("times", c.c_uint32 * 6), ("volume", c.c_uint32),
                ("size", c.c_uint32 * 2), ("links", c.c_uint32), ("index_high", c.c_uint32), ("index_low", c.c_uint32)]


class UnicodeString(c.Structure):
    _fields_ = [("length", c.c_ushort), ("capacity", c.c_ushort), ("buffer", c.c_void_p)]


class ObjectAttributes(c.Structure):
    _fields_ = [("length", c.c_uint32), ("root", c.c_void_p), ("name", c.POINTER(UnicodeString)),
                ("attributes", c.c_uint32), ("security", c.c_void_p), ("quality", c.c_void_p)]


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
        self.snapshot = bind(k, "CreateToolhelp32Snapshot", w.HANDLE, w.DWORD, w.DWORD)
        self.walk_process = [bind(k, name, w.BOOL, w.HANDLE, c.POINTER(ProcessEntry))
                             for name in ("Process32FirstW", "Process32NextW")]
        self.walk_thread = [bind(k, name, w.BOOL, w.HANDLE, c.POINTER(ThreadEntry))
                            for name in ("Thread32First", "Thread32Next")]
        self.open_thread = bind(k, "OpenThread", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.thread_owner = bind(k, "GetProcessIdOfThread", w.DWORD, w.HANDLE)
        self.resume = bind(k, "ResumeThread", w.DWORD, w.HANDLE)
        self.exit_code = bind(k, "GetExitCodeProcess", w.BOOL, w.HANDLE, c.POINTER(w.DWORD))
        self.create_job = bind(k, "CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
        self.set_job = bind(k, "SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
        self.query_job = bind(k, "QueryInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p)
        self.assign_job = bind(k, "AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
        self.in_job = bind(k, "IsProcessInJob", w.BOOL, w.HANDLE, w.HANDLE, c.POINTER(w.BOOL))
        self.terminate_job = bind(k, "TerminateJobObject", w.BOOL, w.HANDLE, w.UINT)
        self.get_file_info = bind(k, "GetFileInformationByHandle", w.BOOL, w.HANDLE, c.POINTER(FileInformation))
        self.set_file_info = bind(k, "SetFileInformationByHandle", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
        nt = c.WinDLL("ntdll")
        self.nt_create = bind(nt, "NtCreateFile", c.c_int32, c.POINTER(w.HANDLE), w.DWORD,
                              c.POINTER(ObjectAttributes), c.c_void_p, c.c_void_p, w.DWORD, w.DWORD, w.DWORD,
                              w.DWORD, c.c_void_p, w.DWORD)
        self.nt_error = bind(nt, "RtlNtStatusToDosError", w.DWORD, c.c_int32)

    def new_job(self):
        job = checked(self.create_job(None, None))
        try:
            limits = JobLimits()
            limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, with no breakaway permission.
            checked(self.set_job(job, 9, c.byref(limits), c.sizeof(limits)))
            received = JobLimits()
            checked(self.query_job(job, 9, c.byref(received), c.sizeof(received), None))
            if received.flags != limits.flags or self.active_job_processes(job):
                raise ValueError("The new unnamed job must be empty with kill-on-close enabled")
            return job
        except BaseException:
            checked(self.close(job))
            raise

    def active_job_processes(self, job):
        counts = JobAccounting()
        checked(self.query_job(job, 1, c.byref(counts), c.sizeof(counts), None))
        return counts.active

    def assign_suspended(self, job, proc, exe):
        # Popen retains the original process handle. Its PID cannot be recycled while that object is live.
        process = checked(self.open(0x1101, False, proc.pid))  # SET_QUOTA | TERMINATE | QUERY_LIMITED_INFORMATION
        try:
            checked(self.assign_job(job, process))
            query = bind(self.kernel, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD))
            image, capacity = c.create_unicode_buffer(32768), w.DWORD(32768)
            checked(query(process, 0, image, c.byref(capacity)))
            if Path(image.value) != exe:
                raise ValueError("The suspended process did not load its pinned executable")
            belongs = w.BOOL()
            checked(self.in_job(process, job, c.byref(belongs)))
            if not belongs.value or self.active_job_processes(job) != 1:
                raise ValueError("The suspended subject is not the sole process in its owned job")
        finally:
            checked(self.close(process))

    def wait_job_empty(self, job, timeout):
        until = time.monotonic() + timeout
        while self.active_job_processes(job):
            if time.monotonic() >= until:
                return False
            time.sleep(.025)
        return True

    def path_handle(self, path, directory, *, delete=False, allow_writer=False):
        access = (0x10000 | 0x80) if delete else (0x81 if directory else 0x80000000)
        handle = self.create_file(str(path), access, 3 if directory or allow_writer else 1, None, 3, 0x02200000, None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        return handle

    def file_info(self, handle):
        info = FileInformation()
        checked(self.get_file_info(handle, c.byref(info)))
        if not info.index_high and not info.index_low:
            raise ValueError("The benchmark volume did not provide a stable file ID")
        return info.attributes, (info.volume, (info.index_high << 32) | info.index_low)

    def create_child_directory(self, parent, name):
        if not re.fullmatch(r"ifw-(?:rw02|shell)-[0-9a-f]{32}|Immich Folder Watch", name):
            raise ValueError("Unexpected Windows fixture directory name")
        wide = c.create_unicode_buffer(name)
        size = len(name.encode("utf-16-le"))
        counted = UnicodeString(size, size, c.cast(wide, c.c_void_p))
        attributes = ObjectAttributes(c.sizeof(ObjectAttributes), parent, c.pointer(counted), 0x40, None, None)
        handle = w.HANDLE()
        io_status = (c.c_size_t * 2)()
        # FILE_CREATE returns a handle to the directory this call creates, relative to the pinned parent.
        status = self.nt_create(c.byref(handle), 0x100081, c.byref(attributes), io_status, None,
                                0x80, 3, 2, 0x00200021, None, 0)
        if status < 0:
            raise c.WinError(self.nt_error(status))
        return handle.value

    def delete_handle(self, handle):
        # FileDispositionInfoEx, DELETE | IGNORE_READONLY_ATTRIBUTE. No attribute changes on other links.
        flags = c.c_uint32(0x11)
        checked(self.set_file_info(handle, 21, c.byref(flags), c.sizeof(flags)))

    def snapshot_entries(self, flags, kind, functions):
        handle = self.snapshot(flags, 0)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            entry = kind()
            entry.size = c.sizeof(entry)
            step, advance = functions
            while step(handle, c.byref(entry)):
                yield kind.from_buffer_copy(entry)
                step = advance
            if c.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise c.WinError(c.get_last_error())
        finally:
            self.close(handle)

    def processes(self):
        return {e.pid: (e.parent, e.image) for e in self.snapshot_entries(2, ProcessEntry, self.walk_process)}

    def resume_owned_process(self, pid):
        # The recorder retains the original Popen/process handle until teardown.
        threads = [e.tid for e in self.snapshot_entries(4, ThreadEntry, self.walk_thread) if e.owner == pid]
        if len(threads) != 1:
            raise ValueError("Expected exactly one thread in the owned suspended subject")
        handle = checked(self.open_thread(0x0802, False, threads[0]))
        try:
            if self.thread_owner(handle) != pid or self.resume(handle) != 1:
                raise OSError("Could not release the owned primary thread")
        finally:
            self.close(handle)

    def process_identity(self, handle):
        creation, end, kernel, user = [w.FILETIME() for _ in range(4)]
        checked(self.times(handle, *map(c.byref, (creation, end, kernel, user))))
        return (creation.dwHighDateTime << 32) + creation.dwLowDateTime

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

    def usage(self, handle, *, working_set=True):
        creation, end, kernel, user = [w.FILETIME() for _ in range(4)]
        checked(self.times(handle, *map(c.byref, (creation, end, kernel, user))))
        ticks = sum((part.dwHighDateTime << 32) + part.dwLowDateTime for part in (kernel, user))
        memory = 0.
        if working_set:
            data = Memory()
            data.cb = c.sizeof(data)
            checked(self.memory(handle, c.byref(data), data.cb))
            memory = data.working / 1_048_576
        return ticks / 10_000_000, memory

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
