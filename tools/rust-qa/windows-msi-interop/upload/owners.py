"""Measure owners of a held IPv4 connection and the restored database on Windows."""
import ctypes as c
from ctypes import wintypes as w
from ipaddress import IPv6Address
import socket
import struct

from shared import require


# MIB_TCPROW_OWNER_PID and MIB_TCP6ROW_OWNER_PID in the Windows SDK tcpmib.h.
ROW4 = struct.Struct("<I4sI4sII")
ROW6 = struct.Struct("<16sII16sIIII")


def ipv6_endpoint(address, scope):
    ip = IPv6Address(address)
    if scope:
        return f"{ip}%{socket.ntohl(scope)}"
    return str(ip.ipv4_mapped or ip)


def decode_connection(raw):
    if len(raw) == ROW4.size:
        state, local, local_port, remote, remote_port, pid = ROW4.unpack(raw)
        client, server = socket.inet_ntoa(local), socket.inet_ntoa(remote)
    elif len(raw) == ROW6.size:
        local, local_scope, local_port, remote, remote_scope, remote_port, state, pid = ROW6.unpack(raw)
        client, server = ipv6_endpoint(local, local_scope), ipv6_endpoint(remote, remote_scope)
    else:
        raise ValueError("Expected a complete native IPv4 or IPv6 owner row")
    return dict(state=state, client=[client, socket.ntohs(local_port & 0xffff)],
                server=[server, socket.ntohs(remote_port & 0xffff)], pid=pid)


def native_table(query, family):
    size = w.DWORD()
    for _ in range(4):
        data = c.create_string_buffer(size.value) if size.value else None
        code = query(data, c.byref(size), False, family, 4, 0)  # TCP_TABLE_OWNER_PID_CONNECTIONS
        if code == 122 and 0 < size.value <= 4 * 1024 * 1024:
            continue
        if code == 50 and family == socket.AF_INET6:  # ERROR_NOT_SUPPORTED on an IPv4-only host
            return None
        if code:
            raise OSError(code, f"GetExtendedTcpTable({family.name}) failed")
        require(data is not None and len(data) >= size.value >= 4, "Incomplete native TCP owner table")
        return data.raw[:size.value]
    raise ValueError(f"The native {family.name} table changed throughout the bounded observation")


def select_connection(tables, pid, observed):
    client, server = list(observed["client"]), list(observed["server"])
    require(client[0] == server[0] == "127.0.0.1" and client != server
            and all(type(port) is int and 0 < port <= 65535 for port in (client[1], server[1])),
            "Expected the accepted private IPv4 asset connection")
    selected = []
    ambiguous = False
    diagnostics = []
    for family, size in ((socket.AF_INET, ROW4.size), (socket.AF_INET6, ROW6.size)):
        data = tables[family]
        if data is None and family == socket.AF_INET6:
            diagnostics.append("AF_INET6 unsupported")
            continue
        require(data is not None and len(data) >= 4, "Missing native TCP owner table")
        count, = struct.unpack_from("<I", data)
        require(4 + count * size <= len(data), f"Truncated native {family.name} owner table")
        owned = hits = matched = 0
        for i in range(count):
            raw = data[4 + i * size:4 + (i + 1) * size]
            row = decode_connection(raw)
            if row["state"] != 5:  # ESTABLISHED
                continue
            owned += row["pid"] == pid
            if row["client"] == client and row["server"] == server:
                hits += 1
                if row["pid"] == pid:
                    matched += 1
                    selected.append(raw)
        # Both tables may represent the same held dual-mode connection. Each
        # representation must uniquely identify the same observed process.
        ambiguous |= hits != matched or hits > 1
        diagnostics.append(f"{family.name} WPF-established={owned} tuple-hits={hits} owned-hits={matched}")
    require(selected and not ambiguous, "No unique WPF owner of the held asset connection (" + ", ".join(diagnostics) + ")")
    return selected[0].hex()


def client_connection(proc, observed):
    from native import bind
    query = bind(c.WinDLL("iphlpapi"), "GetExtendedTcpTable", w.DWORD, c.c_void_p, c.POINTER(w.DWORD),
                 w.BOOL, w.ULONG, c.c_int, w.ULONG)
    tables = {family: native_table(query, family) for family in (socket.AF_INET, socket.AF_INET6)}
    selected = select_connection(tables, proc.pid, observed)
    require(proc.poll() is None, "The original WPF process exited during the TCP observation")
    return selected


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
