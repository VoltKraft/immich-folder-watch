"""Identify this process's own WTS session and authenticated local Windows logon."""
import ctypes as c
from ctypes import wintypes as w
import hashlib

from fixture import Accounts, bind, checked
from standard import Luid


class TokenStatisticsPrefix(c.Structure):
    _fields_ = [("token", Luid), ("authentication", Luid)]


class UnicodeString(c.Structure):
    _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", c.c_void_p)]


class SessionData(c.Structure):
    _fields_ = [("size", w.ULONG), ("id", Luid), ("user", UnicodeString),
                ("domain", UnicodeString), ("package", UnicodeString),
                ("logon_type", w.ULONG), ("session", w.ULONG)]


def current_logon(identity, role):
    accounts = Accounts()
    token = w.HANDLE()
    checked(accounts.open_token(w.HANDLE(-1), 8, c.byref(token)), "OpenProcessToken(current)")
    try:
        statistics = accounts.token_info(token, 10)  # TokenStatistics
        authentication = TokenStatisticsPrefix.from_buffer(statistics).authentication
        security = c.WinDLL("secur32")
        lookup = bind(security, "LsaGetLogonSessionData", w.LONG, c.POINTER(Luid), c.POINTER(c.c_void_p))
        release = bind(security, "LsaFreeReturnBuffer", w.LONG, c.c_void_p)
        memory = c.c_void_p()
        status = lookup(c.byref(authentication), c.byref(memory))
        if status or not memory.value:
            raise RuntimeError(f"LsaGetLogonSessionData(current logon) returned {status:#x}")
        try:
            data = c.cast(memory, c.POINTER(SessionData)).contents
            if data.size < c.sizeof(SessionData) or bytes(data.id) != bytes(authentication):
                raise RuntimeError("Windows returned a different logon session")
            logon_type = data.logon_type
        finally:
            release(memory)
        logon_id = hashlib.sha256(bytes(authentication)).hexdigest()
    finally:
        accounts.close(token)
    wts = c.WinDLL("wtsapi32", use_last_error=True)
    query = bind(wts, "WTSQuerySessionInformationW", w.BOOL, w.HANDLE, w.DWORD, c.c_int,
                 c.POINTER(c.c_void_p), c.POINTER(w.DWORD))
    free = bind(wts, "WTSFreeMemory", None, c.c_void_p)
    pointer, size = c.c_void_p(), w.DWORD()
    checked(query(None, 0xffffffff, 4, c.byref(pointer), c.byref(size)), "WTSQuerySessionInformationW(current, WTSSessionId)")
    try:
        if not pointer.value or size.value != c.sizeof(w.DWORD):
            raise ValueError("Unexpected WTS session ID size")
        session = c.cast(pointer, c.POINTER(w.DWORD)).contents.value
    finally:
        free(pointer)
    if (session != identity["sessionId"] or session != identity["tokenSessionId"]
            or (role == "scheduled" and (session != 0 or logon_type != 4))
            or (role == "original" and (session == 0 or logon_type != 2))
            or role not in ("scheduled", "original")):
        raise ValueError(f"Unexpected WTS session {session} or actual logon type {logon_type} for {role}")
    return {"wtsSessionId": session, "logonType": logon_type, "authenticationIdSha256": logon_id}
