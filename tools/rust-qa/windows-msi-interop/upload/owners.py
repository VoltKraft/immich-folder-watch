"""Measure owners of a held IPv4 connection and the restored database on Windows."""
import ctypes as c
from ctypes import wintypes as w
import socket
import struct

from shared import require


def decode_connection(raw):
    state, local, local_port, remote, remote_port, pid = struct.unpack("<6I", raw)
    def address(value, port):
        return [socket.inet_ntoa(struct.pack("<I", value)), socket.ntohs(port & 0xffff)]
    return dict(state=state, client=address(local, local_port), server=address(remote, remote_port), pid=pid)


def client_connection(proc, observed):
    from native import bind
    query = bind(c.WinDLL("iphlpapi"), "GetExtendedTcpTable", w.DWORD, c.c_void_p, c.POINTER(w.DWORD),
                 w.BOOL, w.ULONG, c.c_int, w.ULONG)
    size = w.DWORD()
    for _ in range(4):
        data = c.create_string_buffer(size.value) if size.value else None
        code = query(data, c.byref(size), False, socket.AF_INET, 4, 0)  # TCP_TABLE_OWNER_PID_CONNECTIONS
        if code == 122 and size.value <= 4 * 1024 * 1024:
            continue
        if code:
            raise c.WinError(code)
        count, = struct.unpack_from("<I", data.raw)
        require(4 + count * 24 <= len(data), "Incomplete native connected IPv4 table")
        expected = dict(pid=proc.pid, state=5, client=list(observed["client"]), server=list(observed["server"]))
        matches = [r for r in struct.iter_unpack("24s", data.raw[4:4+24*count]) if decode_connection(r[0]) == expected]
        require(len(matches) == 1 and proc.poll() is None, "No unique live WPF connection to the held asset request")
        return matches[0][0].hex()
    raise ValueError("The native TCP table changed throughout the bounded observation")


class UniqueProcess(c.Structure):
    _fields_ = [("pid", w.DWORD), ("creation", w.FILETIME)]


class ProcessInfo(c.Structure):
    _fields_ = [("process", UniqueProcess), ("name", w.WCHAR * 256), ("service", w.WCHAR * 64),
                ("type", c.c_int), ("status", w.ULONG), ("session", w.DWORD), ("restartable", w.BOOL)]


def database_owner(path, proc, created):
    """Query users of this registered filename only. Never request shutdown or restart."""
    from native import bind
    dll = c.WinDLL("rstrtmgr")
    start = bind(dll, "RmStartSession", w.DWORD, c.POINTER(w.DWORD), w.DWORD, w.LPWSTR)
    register = bind(dll, "RmRegisterResources", w.DWORD, w.DWORD, w.UINT, c.POINTER(w.LPCWSTR),
                    w.UINT, c.c_void_p, w.UINT, c.c_void_p)
    query = bind(dll, "RmGetList", w.DWORD, w.DWORD, c.POINTER(w.UINT), c.POINTER(w.UINT),
                 c.POINTER(ProcessInfo), c.POINTER(w.DWORD))
    end = bind(dll, "RmEndSession", w.DWORD, w.DWORD)
    def checked(code):
        if code:
            raise c.WinError(code)
    session = w.DWORD()
    checked(start(c.byref(session), 0, c.create_unicode_buffer(33)))
    try:
        checked(register(session, 1, (w.LPCWSTR * 1)(str(path)), 0, None, 0, None))
        needed, actual, reasons = w.UINT(), w.UINT(), w.DWORD()
        for _ in range(4):
            entries = (ProcessInfo * actual.value)() if actual.value else None
            code = query(session, c.byref(needed), c.byref(actual), entries, c.byref(reasons))
            if code == 234 and 0 < needed.value <= 128:
                actual.value = needed.value
                continue
            checked(code)
            for entry in list(entries or ())[:actual.value]:
                identity = entry.process
                stamp = identity.creation.dwLowDateTime | (identity.creation.dwHighDateTime << 32)
                if (identity.pid, stamp) == (proc.pid, created) and proc.poll() is None:
                    return dict(pid=identity.pid, created=stamp, registeredFile=str(path))
            return None
        raise ValueError("The restored database owner list did not stabilize")
    finally:
        checked(end(session))
