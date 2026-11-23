"""Launch only the assessment observer on an explicit desktop, with a bounded process tree."""

import ctypes as c
from ctypes import wintypes as w
import subprocess
import sys

from win32 import P, bind, check


class Startup(c.Structure):
    _fields_ = [("size", c.c_uint32), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR), ("title", w.LPWSTR),
                ("dimensions", c.c_uint32 * 7), ("flags", c.c_uint32), ("show", c.c_uint16), ("reserved_size", c.c_uint16),
                ("reserved_data", c.c_void_p), ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]


class Process(c.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", c.c_uint32), ("tid", c.c_uint32)]


class BasicLimits(c.Structure):
    _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64), ("flags", c.c_uint32),
                ("minimum_ws", c.c_size_t), ("maximum_ws", c.c_size_t), ("processes", c.c_uint32),
                ("affinity", c.c_size_t), ("priority", c.c_uint32), ("scheduling", c.c_uint32)]


class ExtendedLimits(c.Structure):
    _fields_ = [("basic", BasicLimits), ("io_counters", c.c_uint64 * 6), ("memory_limits", c.c_size_t * 4)]


def run_worker(worker, args, desktop, cwd, record, *, timeout_seconds=180, environment_block=None):
    if (c.sizeof(Startup), c.sizeof(Process), c.sizeof(ExtendedLimits)) != (104, 24, 144):
        raise RuntimeError("Expected the native Windows x64 or ARM64 structure layout")
    if not 1 <= timeout_seconds <= 900:
        raise ValueError("The native desktop worker requires a bounded lifetime")
    kernel = c.WinDLL("kernel32", use_last_error=True)
    make_job = bind(kernel, "CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
    set_limits = bind(kernel, "SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
    create = bind(kernel, "CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL,
                  w.DWORD, c.c_void_p, w.LPCWSTR, P(Startup), P(Process))
    assign = bind(kernel, "AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
    resume = bind(kernel, "ResumeThread", w.DWORD, w.HANDLE)
    wait = bind(kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
    get_status = bind(kernel, "GetExitCodeProcess", w.BOOL, w.HANDLE, P(w.DWORD))
    terminate = bind(kernel, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
    close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
    job = check(make_job(None, None), "CreateJobObjectW")
    process = Process()
    assigned = False
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        check(set_limits(job, 9, c.byref(limits), c.sizeof(limits)), "SetInformationJobObject")
        start = Startup()
        start.size, start.desktop = c.sizeof(start), "WinSta0\\" + desktop
        cmdline = c.create_unicode_buffer(subprocess.list2cmdline([sys.executable, "-B", str(worker), *map(str, args)]))
        flags = subprocess.CREATE_NO_WINDOW | 4
        if environment_block is not None:
            flags |= 0x400  # CREATE_UNICODE_ENVIRONMENT
        check(create(sys.executable, cmdline, None, None, False,
                     flags, environment_block, str(cwd), c.byref(start), c.byref(process)),
              "CreateProcessW(CREATE_SUSPENDED)")
        record["workerPid"] = process.pid
        check(assign(job, process.process), "AssignProcessToJobObject")
        assigned = True
        check(resume(process.thread) != 0xffffffff, "ResumeThread")
        outcome = wait(process.process, timeout_seconds * 1000)
        if outcome == 258:  # WAIT_TIMEOUT
            raise TimeoutError(f"The desktop worker exceeded {timeout_seconds} seconds")
        check(outcome == 0, "WaitForSingleObject")
        status = w.DWORD()
        check(get_status(process.process, c.byref(status)), "GetExitCodeProcess")
        record["workerExit"] = status.value
        return status.value
    finally:
        # A failed assignment leaves a suspended process that has never executed user code.
        try:
            if process.process and not assigned:
                check(terminate(process.process, 1), "TerminateProcess(suspended fixture)")
        finally:
            try:
                check(close(job), "CloseHandle(fixture job)")
                record["jobClosed"] = True
                if process.process:
                    check(wait(process.process, 10_000) == 0, "WaitForSingleObject(fixture cleanup)")
            finally:
                if process.thread:
                    close(process.thread)
                if process.process:
                    close(process.process)
