"""Provision and restore only SeBatchLogonRight on the newly created local fixture SID."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from batch import LsaString, ObjectAttributes
from fixture import HOSTED, bind


def change(root, action):
    if (action not in ("grant", "restore") or not all(os.environ.get(k) == v for k, v in HOSTED.items())
            or os.environ.get("RUNNER_ARCH") != "ARM64" or os.environ.get("RUNNER_OS") != "Windows"
            or root.parent != Path(os.environ["ProgramData"]).resolve()
            or not re.fullmatch(r"IfwWriterArm_[0-9a-f]{32}", root.name)):
        raise ValueError("This provisioner requires the isolated Windows ARM64 runner")
    config = json.loads((root / "launch.json").read_text(encoding="utf-8-sig"))
    account = "ifwqa" + root.name.split("_")[1][:12]
    # Resolve the local test account afresh and bind it to the user created in this job.
    adv = c.WinDLL("advapi32", use_last_error=True)
    lookup = bind(adv, "LookupAccountNameW", w.BOOL, w.LPCWSTR, w.LPCWSTR, c.c_void_p,
                  c.POINTER(w.DWORD), w.LPWSTR, c.POINTER(w.DWORD), c.POINTER(w.DWORD))
    account_sid = c.create_string_buffer(256)
    domain = c.create_unicode_buffer(256)
    nsid, nname, kind = w.DWORD(len(account_sid)), w.DWORD(len(domain)), w.DWORD()
    if (not lookup(None, os.environ["COMPUTERNAME"] + "\\" + account, account_sid, c.byref(nsid), domain,
                   c.byref(nname), c.byref(kind)) or kind.value != 1
            or domain.value.casefold() != os.environ["COMPUTERNAME"].casefold()):
        raise ValueError("Could not resolve the dedicated local test user")
    text_sid = c.c_void_p()
    conv = bind(adv, "ConvertSidToStringSidW", w.BOOL, c.c_void_p, c.POINTER(c.c_void_p))
    free = bind(c.WinDLL("kernel32"), "LocalFree", c.c_void_p, c.c_void_p)
    if not conv(account_sid, c.byref(text_sid)):
        raise OSError(c.get_last_error(), "ConvertSidToStringSidW")
    try:
        if hashlib.sha256(c.wstring_at(text_sid).encode("ascii")).hexdigest() != config["sidSha256"]:
            raise ValueError("The generated account no longer has its original SID")
    finally:
        free(text_sid)
    open_policy = bind(adv, "LsaOpenPolicy", w.LONG, c.c_void_p, c.POINTER(ObjectAttributes), w.ULONG, c.POINTER(w.HANDLE))
    enum = bind(adv, "LsaEnumerateAccountRights", w.LONG, w.HANDLE, c.c_void_p,
                c.POINTER(c.POINTER(LsaString)), c.POINTER(w.ULONG))
    add = bind(adv, "LsaAddAccountRights", w.LONG, w.HANDLE, c.c_void_p, c.POINTER(LsaString), w.ULONG)
    remove = bind(adv, "LsaRemoveAccountRights", w.LONG, w.HANDLE, c.c_void_p, c.c_ubyte, c.POINTER(LsaString), w.ULONG)
    release = bind(adv, "LsaFreeMemory", w.LONG, c.c_void_p)
    close = bind(adv, "LsaClose", w.LONG, w.HANDLE)
    translate = bind(adv, "LsaNtStatusToWinError", w.ULONG, w.LONG)
    def check(status):
        if status:
            raise OSError(translate(status), "Temporary user batch-logon assignment")
    attrs, policy = ObjectAttributes(), w.HANDLE()
    attrs.length = c.sizeof(attrs)
    # POLICY_LOOKUP_NAMES | POLICY_CREATE_ACCOUNT creates only a per-SID LSA entry.
    check(open_policy(None, c.byref(attrs), 0x0810, c.byref(policy)))
    def rights():
        rows, size = c.POINTER(LsaString)(), w.ULONG()
        status = enum(policy, account_sid, c.byref(rows), c.byref(size))
        if status and translate(status) in (2, 259):
            return []
        check(status)
        try:
            return sorted(c.wstring_at(r.buffer, r.length//2) for r in rows[:size.value])
        finally:
            release(rows)
    try:
        name = "SeBatchLogonRight"
        buf = c.create_unicode_buffer(name)
        right = LsaString(len(name)*2, c.sizeof(buf), c.cast(buf, c.c_void_p))
        before = rights()
        if action == "grant":
            if before:
                raise ValueError("A freshly created local test SID must have no direct assignments")
            check(add(policy, account_sid, c.byref(right), 1))
        elif before == [name]:
            check(remove(policy, account_sid, False, c.byref(right), 1))
        elif before:
            raise ValueError("Unexpected assignments on the isolated test SID")
        after = rights()
        if after != ([name] if action == "grant" else []):
            raise ValueError("The exact batch assignment did not reach the expected state")
        return {"before": before, "after": after}
    finally:
        close(policy)


if __name__ == "__main__":
    print(json.dumps(change(Path(sys.argv[2]).resolve(strict=True), sys.argv[1])))
