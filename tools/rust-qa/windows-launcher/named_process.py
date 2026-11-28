"""Create the observer's ordinary, suspended subject on its verified Windows desktop."""

from contextlib import ExitStack, contextmanager
import ctypes as c
from ctypes import wintypes as w
from functools import cmp_to_key
import math
import os
from pathlib import PureWindowsPath
import re
import subprocess

from job import Process, Startup
from native import CleanupUnconfirmed
from win32 import P, bind, check


CREATE_SUSPENDED = 0x4
DETACHED_PROCESS = 0x8
CREATE_UNICODE_ENVIRONMENT = 0x400
EXTENDED_STARTUPINFO_PRESENT = 0x80000
CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x20002
WAIT_TIMEOUT = 258


class StartupEx(c.Structure):
    _fields_ = [("startup", Startup), ("attributes", c.c_void_p)]


class Kernel:
    def __init__(self):
        if (c.sizeof(Startup), c.sizeof(StartupEx), c.sizeof(Process)) != (104, 112, 24):
            raise RuntimeError("Expected the x64 or ARM64 Windows process structures")
        kernel = c.WinDLL("kernel32", use_last_error=True)
        self.initialize = bind(kernel, "InitializeProcThreadAttributeList", w.BOOL,
                               c.c_void_p, w.DWORD, w.DWORD, P(c.c_size_t))
        self.update = bind(kernel, "UpdateProcThreadAttribute", w.BOOL, c.c_void_p, w.DWORD,
                           c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, P(c.c_size_t))
        self.delete = bind(kernel, "DeleteProcThreadAttributeList", None, c.c_void_p)
        self.create = bind(kernel, "CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p,
                           w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR, P(StartupEx), P(Process))
        self.compare = bind(kernel, "CompareStringOrdinal", c.c_int, w.LPCWSTR, c.c_int,
                            w.LPCWSTR, c.c_int, w.BOOL)
        self.resume = bind(kernel, "ResumeThread", w.DWORD, w.HANDLE)
        self.wait = bind(kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        self.exit_code = bind(kernel, "GetExitCodeProcess", w.BOOL, w.HANDLE, P(c.c_uint32))
        self.terminate = bind(kernel, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
        self.close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)


def environment_block(api, env):
    """Preserve UTF-16 values and drive entries in Windows' case-insensitive ordinal order."""
    def compare(left, right):
        return check(api.compare(left, -1, right, -1, True), "CompareStringOrdinal") - 2

    for key, value in env.items():
        if (not key or "\0" in key or "\0" in value
                or ("=" in key and not re.fullmatch("=[A-Za-z]:", key))):
            raise ValueError("Invalid Windows fixture environment entry")
    keys = sorted(env, key=cmp_to_key(compare))
    if any(compare(left, right) == 0 for left, right in zip(keys, keys[1:])):
        raise ValueError("Duplicate case-insensitive environment key")
    block = ("\0".join(f"{key}={env[key]}" for key in keys) + "\0\0").encode("utf-16-le", "surrogatepass")
    return (c.c_uint16 * (len(block) // 2)).from_buffer_copy(block)


@contextmanager
def handle_list(api, stdin, output):
    size = c.c_size_t()
    if api.initialize(None, 1, 0, c.byref(size)) or c.get_last_error() != 122 or not size.value:
        raise OSError("Could not size the child handle attribute list")
    attributes = c.create_string_buffer(size.value)
    check(api.initialize(attributes, 1, 0, c.byref(size)), "InitializeProcThreadAttributeList")
    try:
        # Both handles are private inheritable descriptors. stdout and stderr share one file position.
        handles = (w.HANDLE * 2)(stdin, output)
        check(api.update(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles, c.sizeof(handles), None, None),
              "UpdateProcThreadAttribute(HANDLE_LIST)")
        yield attributes
    finally:
        api.delete(attributes)


class Child:
    """Keep original process and initial-thread identities until the fixture finishes job readback."""

    def __init__(self, api, args, stdin):
        self.api, self.args, self.stdin = api, args, stdin
        self.info = Process()
        self.returncode = None
        self.resumed = False

    @property
    def pid(self):
        return self.info.pid

    @property
    def thread_id(self):
        return self.info.tid

    @property
    def _handle(self):
        return self.info.process

    def resume(self):
        if self.resumed or not self.info.thread:
            raise ValueError("The original primary thread is no longer awaiting its first resume")
        previous = self.api.resume(self.info.thread)
        check(previous != 0xffffffff, "ResumeThread")
        if previous != 1:
            raise ValueError("The initial thread did not have exactly one suspension")
        self.resumed = True

    def _status(self, milliseconds):
        if self.returncode is None:
            if not self.info.process:
                raise ValueError("The original process handle is closed")
            state = self.api.wait(self.info.process, milliseconds)
            if state == WAIT_TIMEOUT:
                return None
            check(state == 0, "WaitForSingleObject")
            status = c.c_uint32()
            check(self.api.exit_code(self.info.process, c.byref(status)), "GetExitCodeProcess")
            self.returncode = status.value
        return self.returncode

    def poll(self):
        return self._status(0)

    def wait(self, timeout=8):
        if not math.isfinite(timeout) or not 0 <= timeout <= 0xfffffffe / 1000:
            raise ValueError("Expected a finite Windows wait")
        milliseconds = math.ceil(timeout * 1000)
        status = self._status(milliseconds)
        if status is None:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return status

    def kill(self):
        if self.poll() is None and not self.api.terminate(self.info.process, 1):
            failure = c.get_last_error()
            if self.poll() is None:  # The original process can exit between poll and TerminateProcess.
                raise OSError(failure, "TerminateProcess failed for the owned fixture")

    def close(self):
        # A partially started, suspended subject can still need termination before job assignment.
        try:
            with ExitStack() as cleanup:
                for field in ("process", "thread"):
                    handle = getattr(self.info, field)
                    if handle:
                        cleanup.callback(self._close_handle, field, handle)
                if self.stdin is not None:
                    cleanup.callback(self.stdin.close)
                if self.info.process and self.poll() is None:
                    self.kill()
                    self.wait(timeout=8)
        except Exception as exc:
            raise CleanupUnconfirmed("Could not reap the original child and release its handles") from exc

    def _close_handle(self, field, handle):
        check(self.api.close(handle), "CloseHandle(owned " + field + ")")
        setattr(self.info, field, None)


def start(exe, arguments, *, cwd, env, stream, desktop, primary, named_input=False, before_create=None):
    """Return a suspended child. The caller must check its image and job before resume and close it after use."""
    import msvcrt

    token = env.get("IFW_QA_INVENTORY_TOKEN", "")
    allowed = ("IfwQa_" + token,) if named_input else ("Default", "IfwQa_Launcher_" + token, "IfwQa_Tray_" + token)
    if (not re.fullmatch("[0-9a-f]{32}", token) or env.get("IFW_QA_ISOLATED") != "1"
            or desktop not in allowed):
        raise ValueError("Expected the verified fixture desktop and its original profile")
    if not PureWindowsPath(exe).is_absolute() or not PureWindowsPath(cwd).is_absolute():
        raise ValueError("The staged executable and working directory must have absolute paths")
    if not primary and arguments:
        raise ValueError("Expected an ordinary no-argument secondary")
    args = [os.fspath(exe), *map(os.fspath, arguments)]
    if any("\0" in value for value in (*args, os.fspath(cwd))):
        raise ValueError("Invalid Windows fixture path or argument")
    api = Kernel()
    cmdline = c.create_unicode_buffer(subprocess.list2cmdline(args))
    block = environment_block(api, env)
    child = Child(api, args, None)
    try:
        with ExitStack() as temporary:
            if primary:
                read_fd, write_fd = os.pipe()
                temporary.callback(os.close, read_fd)
                try:
                    child.stdin = os.fdopen(write_fd, "wb", buffering=0)
                except BaseException:
                    os.close(write_fd)
                    raise
            else:
                read_fd = os.open(os.devnull, os.O_RDONLY | os.O_BINARY)
                temporary.callback(os.close, read_fd)
            output_fd = os.dup(stream.fileno())
            temporary.callback(os.close, output_fd)
            os.set_inheritable(read_fd, True)
            os.set_inheritable(output_fd, True)
            stdin, output = map(msvcrt.get_osfhandle, (read_fd, output_fd))
            attributes = temporary.enter_context(handle_list(api, stdin, output))
            info = StartupEx()
            info.startup.size, info.startup.desktop = c.sizeof(info), "WinSta0\\" + desktop
            info.startup.flags = STARTF_USESTDHANDLES
            info.startup.stdin, info.startup.stdout, info.startup.stderr = stdin, output, output
            info.attributes = c.cast(attributes, c.c_void_p)
            flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
            flags |= CREATE_NO_WINDOW if primary else DETACHED_PROCESS
            original = Process()
            if before_create is not None:
                before_create()
            check(api.create(args[0], cmdline, None, None, True, flags, block, os.fspath(cwd),
                             c.byref(info), c.byref(original)), "CreateProcessW(owned desktop)")
            child.info = original
        return child
    except BaseException:
        child.close()
        raise
