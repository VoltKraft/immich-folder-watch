"""Query two new read-only handles to the same synthetic Windows directory."""
import ctypes as c
from contextlib import ExitStack


def registration_controls(root):
    from ctypes import wintypes as w

    class FileId(c.Structure):
        _fields_ = [("volume", c.c_uint64), ("identifier", c.c_ubyte * 16)]

    class FileIdDescriptor(c.Structure):
        _fields_ = [("size", w.DWORD), ("kind", c.c_int), ("identifier", c.c_ubyte * 16)]

    api = c.WinDLL("kernel32", use_last_error=True)
    def bind(name, returns, *args):
        fn = getattr(api, name)
        fn.restype, fn.argtypes = returns, args
        return fn
    create = bind("CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE)
    reopen = bind("ReOpenFile", w.HANDLE, w.HANDLE, w.DWORD, w.DWORD, w.DWORD)
    by_id = bind("OpenFileById", w.HANDLE, w.HANDLE, c.POINTER(FileIdDescriptor), w.DWORD, w.DWORD, c.c_void_p, w.DWORD)
    identity = bind("GetFileInformationByHandleEx", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
    close = bind("CloseHandle", w.BOOL, w.HANDLE)
    invalid = c.c_void_p(-1).value
    def identifier(handle):
        result = FileId()
        if not identity(handle, 18, c.byref(result), c.sizeof(result)):  # FileIdInfo
            raise c.WinError(c.get_last_error())
        return result
    def release(handle):
        if not close(handle):
            raise c.WinError(c.get_last_error())
    def describe(name, handle, stack, results, original):
        if handle == invalid:
            results[name] = {"openError": c.get_last_error()}
            return
        stack.callback(release, handle)
        try:
            current = identifier(handle)
        except OSError as err:
            results[name] = {"openError": 0, "identityError": err.winerror}
        else:
            results[name] = {"openError": 0, "sameDirectory": bytes(current) == bytes(original)}
    flags = 0x02000000 | 0x00200000  # Directory handle, open the entry itself.
    results = {}
    with ExitStack() as stack:
        root_handle = create(str(root), 0x100081, 3, None, 3, flags, None)
        if root_handle == invalid:
            raise c.WinError(c.get_last_error())
        stack.callback(release, root_handle)
        original = identifier(root_handle)
        describe("ReOpenFile", reopen(root_handle, 1, 7, 0x42000000), stack, results, original)
        desc = FileIdDescriptor(c.sizeof(FileIdDescriptor), 2, original.identifier)
        describe("OpenFileById", by_id(root_handle, c.byref(desc), 0x81, 3, None, flags | 0x40000000),
                 stack, results, original)
        describe("directFixtureOpen", create(str(root), 0x81, 3, None, 3, flags | 0x40000000, None),
                 stack, results, original)
    return results
