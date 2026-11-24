"""Install one volatile per-user display name for the hosted notification trial."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import re

PARENT = r"Software\Classes\AppUserModelId"
DISPLAY = "IFW synthetic notification "
DELETE = 0x10000


class MissingNamespace(Exception):
    """The original per-user notification registration namespace does not exist."""


class NativeKeys:
    def __init__(self):
        import winreg
        self.reg = winreg
        self.create_key = c.WinDLL("advapi32").RegCreateKeyExW
        self.create_key.argtypes = (w.HANDLE, w.LPCWSTR, w.DWORD, w.LPWSTR, w.DWORD, w.DWORD,
                                    c.c_void_p, c.POINTER(w.HANDLE), c.POINTER(w.DWORD))
        self.create_key.restype = w.LONG
        self.delete_key = c.WinDLL("ntdll").NtDeleteKey
        self.delete_key.argtypes = (w.HANDLE,)
        self.delete_key.restype = w.LONG

    def create(self, parent, name, rights):
        handle, disposition = w.HANDLE(), w.DWORD()
        # REG_OPTION_VOLATILE applies only to the newly created UUID leaf.
        error = self.create_key(int(parent), name, 0, None, 1, rights, None, c.byref(handle), c.byref(disposition))
        if error:
            raise c.WinError(error)
        return handle.value, disposition.value

    def delete_empty(self, key):
        if self.reg.QueryInfoKey(key)[:2] != (0, 0):
            raise ValueError("The test registry key acquired unowned values or children")
        code = self.delete_key(key)
        if code:
            raise OSError(f"Could not delete the original empty registry key (NTSTATUS 0x{code & 0xffffffff:08x})")


@contextmanager
def new_identity(api, parent, name, record):
    reg = api.reg
    handle, disposition = api.create(parent, name, reg.KEY_READ | reg.KEY_SET_VALUE | DELETE)
    record["leafDisposition"] = disposition
    try:
        if disposition != 1:
            raise ValueError("The unique notification identity already exists or has an unknown disposition")
        try:
            yield handle
        finally:
            api.delete_empty(handle)
    finally:
        reg.CloseKey(handle)


def absent(reg, parent, name):
    try:
        with reg.OpenKey(parent, name, 0, reg.KEY_READ):
            return False
    except FileNotFoundError:
        return True


def identity(token):
    if not re.fullmatch(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}", token):
        raise ValueError("Expected the trial's version 4 UUID")
    return "IFW.RustQA.Toast." + token


def identity_absent(token, reg=None):
    if reg is None:
        import winreg as reg
    return absent(reg, reg.HKEY_CURRENT_USER, PARENT + "\\" + identity(token))


@contextmanager
def display_name(token, record, *, api=None):
    name, value = identity(token), DISPLAY + token
    api = api or NativeKeys()
    reg = api.reg
    record.update(aumid=name, displayName=value, view="native", parent=PARENT, leafRemoved=False)
    try:
        existing = reg.OpenKey(reg.HKEY_CURRENT_USER, PARENT, 0, reg.KEY_READ | reg.KEY_CREATE_SUB_KEY)
    except FileNotFoundError as exc:
        record["parentOpened"] = False
        raise MissingNamespace("The per-user notification registry namespace HKCU\\" + PARENT + " is absent") from exc
    record["parentOpened"] = True
    with existing as parent:
        try:
            with new_identity(api, parent, name, record) as leaf:
                try:
                    reg.SetValueEx(leaf, "DisplayName", 0, reg.REG_SZ, value)
                    with reg.OpenKey(parent, name, 0, reg.KEY_READ) as reader:
                        if (reg.QueryInfoKey(reader)[:2] != (0, 1)
                                or reg.QueryValueEx(reader, "DisplayName") != (value, reg.REG_SZ)):
                            raise ValueError("The separately opened notification registration differs")
                        record["readback"] = True
                    yield
                finally:
                    try:
                        stored = reg.QueryValueEx(leaf, "DisplayName")
                    except FileNotFoundError:
                        pass
                    else:
                        if stored != (value, reg.REG_SZ):
                            raise ValueError("The synthetic display name changed during the trial")
                        reg.DeleteValue(leaf, "DisplayName")
        finally:
            if record.get("leafDisposition") == 1:
                record["leafRemoved"] = absent(reg, parent, name)
                if not record["leafRemoved"]:
                    raise RuntimeError("Could not verify removal of the synthetic app identity")
