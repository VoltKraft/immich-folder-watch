"""Read the existing batch-logon assignment for the current token and its groups."""

import ctypes as c
from ctypes import wintypes as w

from fixture import bind, checked


class ObjectAttributes(c.Structure):
    _fields_ = [("length", w.ULONG), ("root", w.HANDLE), ("name", c.c_void_p), ("attributes", w.ULONG),
                ("descriptor", c.c_void_p), ("quality", c.c_void_p)]


class LsaString(c.Structure):
    _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", c.c_void_p)]


class Group(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("attributes", w.DWORD)]


class Groups(c.Structure):
    _fields_ = [("count", w.DWORD), ("first", Group)]


def batch_rights(accounts):
    advapi = c.WinDLL("advapi32", use_last_error=True)
    open_policy = bind(advapi, "LsaOpenPolicy", w.LONG, c.c_void_p, c.POINTER(ObjectAttributes),
                       w.ULONG, c.POINTER(w.HANDLE))
    rights = bind(advapi, "LsaEnumerateAccountRights", w.LONG, w.HANDLE, c.c_void_p,
                  c.POINTER(c.POINTER(LsaString)), c.POINTER(w.ULONG))
    release = bind(advapi, "LsaFreeMemory", w.LONG, c.c_void_p)
    close = bind(advapi, "LsaClose", w.LONG, w.HANDLE)
    error = bind(advapi, "LsaNtStatusToWinError", w.ULONG, w.LONG)
    attrs = ObjectAttributes()
    attrs.length = c.sizeof(attrs)
    policy, token = w.HANDLE(), w.HANDLE()
    status = open_policy(None, c.byref(attrs), 0x0800, c.byref(policy))  # local POLICY_LOOKUP_NAMES
    if status:
        raise OSError(error(status), "LsaOpenPolicy(POLICY_LOOKUP_NAMES)")

    def for_sid(sid):
        rows, count = c.POINTER(LsaString)(), w.ULONG()
        status = rights(policy, sid, c.byref(rows), c.byref(count))
        if status:
            if error(status) in (2, 259):  # no LSA account rights assigned directly to this SID
                return set()
            raise OSError(error(status), "LsaEnumerateAccountRights(current token membership)")
        try:
            return {c.wstring_at(row.buffer, row.length // 2) for row in rows[:count.value]}
        finally:
            release(rows)

    try:
        checked(accounts.open_token(w.HANDLE(-1), 8, c.byref(token)), "OpenProcessToken(current)")
        try:
            user, groups = accounts.token_info(token, 1), accounts.token_info(token, 2)
            direct = for_sid(c.c_void_p.from_buffer(user))
            count = w.DWORD.from_buffer(groups).value
            if Groups.first.offset + count * c.sizeof(Group) > len(groups):
                raise RuntimeError("Invalid token group buffer")
            members = (Group * count).from_buffer(groups, Groups.first.offset)
            allow, deny = "SeBatchLogonRight", "SeDenyBatchLogonRight"
            group_allow, group_deny = False, False
            for member in members:
                if member.attributes & (4 | 16):  # SE_GROUP_ENABLED or USE_FOR_DENY_ONLY
                    assigned = for_sid(member.sid)
                    group_allow |= bool(member.attributes & 4) and allow in assigned
                    group_deny |= deny in assigned
            return {"directAllow": allow in direct, "directDeny": deny in direct,
                    "enabledGroupAllow": group_allow, "groupDeny": group_deny}
        finally:
            accounts.close(token)
    finally:
        close(policy)


def eligible(rights):
    return ((rights["directAllow"] or rights["enabledGroupAllow"])
            and not rights["directDeny"] and not rights["groupDeny"])
