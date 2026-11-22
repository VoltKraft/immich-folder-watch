"""Compare actual notification I/O on independently acquired synthetic handles.

Each method runs in its own bounded process so an unresponsive kernel operation
cannot outlive a freed ctypes buffer. Name acquisition is fixture-only; the Rust
adapter accepts already authorized asynchronous file objects.
"""
import ctypes as c
import json
from pathlib import Path
import subprocess
import sys
from contextlib import ExitStack


METHODS = ("ReOpenFile", "OpenFileById", "directFixtureOpen", "NtOpenFileRelativeEmpty")


def require_file_id(identifier):
    """Decline the successful-but-unsupported MS-FSCC FileIdInformation value."""
    value = bytes(identifier)
    if len(value) != 16 or not any(value):
        raise ValueError("The filesystem did not provide a 128-bit file identity")


def idle_cancel_passed(result):
    return (result.get("sameDirectory") is True and result.get("idleWaitResult") == 258
            and result.get("cancelError") == 0 and result.get("completionError") == 995)


def registration_controls(root):
    results = {}
    for method in METHODS:
        try:
            result = subprocess.run([sys.executable, __file__, "--trial", str(root), method],
                                    check=True, capture_output=True, text=True, timeout=20)
            results[method] = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            results[method] = {"processTimeoutSeconds": 20}
        except subprocess.CalledProcessError as error:
            results[method] = {"processExitCode": error.returncode, "error": error.stderr[-2048:]}
    return results


def trial(root, method):
    from ctypes import wintypes as w

    class FileId(c.Structure):
        _fields_ = [("volume", c.c_uint64), ("identifier", c.c_ubyte * 16)]

    class AttributeTag(c.Structure):
        _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]

    class IdUnion(c.Union):
        _fields_ = [("file_id", c.c_int64), ("identifier", c.c_ubyte * 16)]

    class FileIdDescriptor(c.Structure):
        _fields_ = [("size", w.DWORD), ("kind", c.c_int), ("extended", IdUnion)]

    class Overlapped(c.Structure):
        _fields_ = [("internal", c.c_size_t), ("internal_high", c.c_size_t),
                    ("offsets", w.DWORD * 2), ("event", w.HANDLE)]

    class IoStatus(c.Structure):
        _fields_ = [("status", c.c_size_t), ("information", c.c_size_t)]

    class UnicodeString(c.Structure):
        _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", w.LPWSTR)]

    class ObjectAttributes(c.Structure):
        _fields_ = [("length", w.ULONG), ("root", w.HANDLE), ("name", c.POINTER(UnicodeString)),
                    ("attributes", w.ULONG), ("security", c.c_void_p), ("qos", c.c_void_p)]

    assert c.sizeof(Overlapped) == 32 and Overlapped.event.offset == 24
    assert c.sizeof(FileIdDescriptor) == 24 and FileIdDescriptor.extended.offset == 8
    assert c.alignment(FileIdDescriptor) == 8 and c.sizeof(IoStatus) == 16
    api = c.WinDLL("kernel32", use_last_error=True)
    nt = c.WinDLL("ntdll")

    def bind(library, name, returns, *args):
        fn = getattr(library, name)
        fn.restype, fn.argtypes = returns, args
        return fn

    create = bind(api, "CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE)
    reopen = bind(api, "ReOpenFile", w.HANDLE, w.HANDLE, w.DWORD, w.DWORD, w.DWORD)
    by_id = bind(api, "OpenFileById", w.HANDLE, w.HANDLE, c.POINTER(FileIdDescriptor), w.DWORD, w.DWORD, c.c_void_p, w.DWORD)
    identity = bind(api, "GetFileInformationByHandleEx", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
    close = bind(api, "CloseHandle", w.BOOL, w.HANDLE)
    event = bind(api, "CreateEventW", w.HANDLE, c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR)
    wait = bind(api, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
    change = bind(api, "ReadDirectoryChangesW", w.BOOL, w.HANDLE, c.c_void_p, w.DWORD,
                  w.BOOL, w.DWORD, c.POINTER(w.DWORD), c.POINTER(Overlapped), c.c_void_p)
    completed = bind(api, "GetOverlappedResult", w.BOOL, w.HANDLE, c.POINTER(Overlapped), c.POINTER(w.DWORD), w.BOOL)
    cancel = bind(api, "CancelIoEx", w.BOOL, w.HANDLE, c.POINTER(Overlapped))
    query = bind(nt, "NtQueryInformationFile", c.c_long, w.HANDLE, c.POINTER(IoStatus), c.c_void_p, w.ULONG, c.c_int)
    ntopen = bind(nt, "NtOpenFile", c.c_long, c.POINTER(w.HANDLE), w.DWORD, c.POINTER(ObjectAttributes),
                  c.POINTER(IoStatus), w.DWORD, w.DWORD)
    dos_error = bind(nt, "RtlNtStatusToDosError", w.ULONG, c.c_long)
    invalid = c.c_void_p(-1).value
    flags = 0x02000000 | 0x00200000
    access, share = 0x100081, 3
    nt_options = 1 | 0x4000 | 0x200000

    def identifier(handle):
        result = FileId()
        if not identity(handle, 18, c.byref(result), c.sizeof(result)):
            raise c.WinError(c.get_last_error())
        require_file_id(result.identifier)
        return result

    def release(handle):
        if not close(handle):
            raise c.WinError(c.get_last_error())

    def info(handle, kind):
        value, status = w.ULONG(), IoStatus()
        # File-information queries are synchronous even for an asynchronous file object.
        result = query(handle, c.byref(status), c.byref(value), c.sizeof(value), kind)
        return {"status": hex(result & 0xffffffff), "bytes": status.information,
                "value": value.value if result == 0 and status.information == 4 else None}

    def decode(buffer, count):
        import struct
        data, position, names = bytes(buffer)[:count], 0, []
        while position < len(data):
            if position + 12 > len(data):
                raise RuntimeError("Incomplete native notification header")
            next_offset, action, name_bytes = struct.unpack_from("<III", data, position)
            if name_bytes % 2 or position + 12 + name_bytes > len(data):
                raise RuntimeError("Incomplete native notification name")
            name = data[position + 12:position + 12 + name_bytes].decode("utf-16-le")
            names.append({"action": action, "name": name})
            if not next_offset:
                break
            if (next_offset < 12 + name_bytes or next_offset % 4
                    or position + next_offset >= len(data)):
                raise RuntimeError("Invalid native notification offset")
            position += next_offset
        return names

    with ExitStack() as outer:
        original_handle = create(str(root), access, share, None, 3, flags, None)
        if original_handle == invalid:
            raise c.WinError(c.get_last_error())
        outer.callback(release, original_handle)
        original = identifier(original_handle)

        def acquire():
            if method == "ReOpenFile":
                handle = reopen(original_handle, access, share, flags | 0x40000000)
            elif method == "OpenFileById":
                descriptor = FileIdDescriptor(c.sizeof(FileIdDescriptor), 2, IdUnion(identifier=original.identifier))
                handle = by_id(original_handle, c.byref(descriptor), access, share, None, flags | 0x40000000)
            elif method == "directFixtureOpen":
                handle = create(str(root), access, share, None, 3, flags | 0x40000000, None)
            else:
                # Probe same-object, handle-relative acquisition without resolving a path.
                empty = c.create_unicode_buffer(1)
                name = UnicodeString(0, 2, c.cast(empty, w.LPWSTR))
                attributes = ObjectAttributes(c.sizeof(ObjectAttributes), original_handle, c.pointer(name), 0x40, None, None)
                status, handle = IoStatus(), w.HANDLE()
                # Directory, backup intent, open reparse point; neither synchronous option.
                result = ntopen(c.byref(handle), access, c.byref(attributes), c.byref(status), share,
                                nt_options)
                if result < 0:
                    return None, {"openError": dos_error(result), "ntStatus": hex(result & 0xffffffff)}
                handle = handle.value
            if handle == invalid or not handle:
                return None, {"openError": c.get_last_error()}
            try:
                current = identifier(handle)
                attributes = AttributeTag()
                if not identity(handle, 9, c.byref(attributes), c.sizeof(attributes)):
                    raise c.WinError(c.get_last_error())
                information = {"openError": 0, "sameDirectory": bytes(current) == bytes(original),
                               "grantedAccess": info(handle, 8), "mode": info(handle, 16),
                               "attributes": attributes.attributes, "reparseTag": attributes.tag}
            except BaseException:
                release(handle)
                raise
            return handle, information

        def request_trial(cancel_only):
            handle, result = acquire()
            if handle is None:
                return result
            with ExitStack() as owned:
                owned.callback(release, handle)
                if (result["mode"]["value"] is None or result["mode"]["value"] & 0x30
                        or result["grantedAccess"]["value"] is None
                        or result["grantedAccess"]["value"] & 0x81 != 0x81
                        or result["attributes"] & 0x400 or not result["sameDirectory"]):
                    result["eligibilityError"] = "Requires matching asynchronous no-reparse listing object"
                    return result
                done = event(None, True, False, None)
                if not done:
                    raise c.WinError(c.get_last_error())
                owned.callback(release, done)
                buffer, request = (w.DWORD * 8192)(), Overlapped(event=done)
                started = change(handle, buffer, c.sizeof(buffer), True, 1 | 2 | 8 | 0x10 | 0x40,
                                 None, c.byref(request), None)
                error = c.get_last_error() if not started else 0
                result["submissionError"] = error
                if error not in (0, 997):
                    return result
                try:
                    if not cancel_only:
                        name = "native-control-" + method + ".txt"
                        (root / name).write_text("synthetic notification control", encoding="ascii")
                        result["waitResult"] = wait(done, 5000)
                        if result["waitResult"] != 0:
                            return result
                    else:
                        result["idleWaitResult"] = wait(done, 100)
                    if cancel_only:
                        result["cancelError"] = 0 if cancel(handle, c.byref(request)) else c.get_last_error()
                    count = w.DWORD()
                    ok = completed(handle, c.byref(request), c.byref(count), True)
                    result["completionError"] = 0 if ok else c.get_last_error()
                    result["bytes"] = count.value
                    if ok and not cancel_only:
                        result["notifications"] = decode(buffer, count.value)
                        result["createdNameObserved"] = any(row["name"] == name for row in result["notifications"])
                    result["passed"] = (idle_cancel_passed(result) if cancel_only else
                        result["sameDirectory"] and bool(ok) and result.get("createdNameObserved", False))
                    return result
                finally:
                    # Cancel then drain before ctypes storage is freed. If the OS
                    # cannot finish, the outer process timeout terminates this
                    # isolated trial instead of freeing a still-live I/O buffer.
                    cancel(handle, c.byref(request))
                    completed(handle, c.byref(request), c.byref(w.DWORD()), True)

        delivery = request_trial(False)
        cancellation = request_trial(True)
        options = ({"requestedNtCreateOptions": nt_options} if method == "NtOpenFileRelativeEmpty"
                   else {"requestedWin32Flags": flags | 0x40000000})
        return {"requestedAccess": access, "requestedShare": share,
                **options,
                "delivery": delivery, "cancellation": cancellation}


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--trial" or sys.argv[3] not in METHODS:
        raise SystemExit("Expected an isolated Windows notification trial")
    root = Path(sys.argv[2])
    marker = root.parent / "owner"
    token = marker.read_text(encoding="ascii")
    if root.name != "source" or len(token) != 32 or any(ch not in "0123456789abcdef" for ch in token):
        raise SystemExit("Expected the synthetic watch-profile marker")
    print(json.dumps(trial(root, sys.argv[3]), ensure_ascii=False))
