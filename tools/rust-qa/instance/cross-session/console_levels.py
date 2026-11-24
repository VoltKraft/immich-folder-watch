"""Read a fixed system trust-level operation on the fixture's own Windows console."""

import ctypes as c
from ctypes import wintypes as w
from contextlib import ExitStack
import os
import subprocess
import sys
import time

from fixture import HERE, bind, checked, write


MAX_CELLS = 16384


class Coord(c.Structure):
    _fields_ = [("x", c.c_short), ("y", c.c_short)]


class ScreenInfo(c.Structure):
    _fields_ = [("size", Coord), ("cursor", Coord), ("attributes", c.c_ushort),
                ("window", c.c_short * 4), ("maximum", Coord)]


def used_cells(info):
    width, height = info.size.x, info.size.y
    x, y = info.cursor.x, info.cursor.y
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("Invalid console cursor or screen dimensions")
    used = width * y + x
    if used >= MAX_CELLS:
        raise ValueError("The system query exceeded the private screen read limit")
    return used


def require_sole_client(process_list):
    clients = (w.DWORD * 2)()
    if process_list(clients, len(clients)) != 1 or clients[0] != os.getpid():
        raise RuntimeError("The console must belong to the dedicated query process")


def wait_for_private_screen(process_list, area):
    # A successful launch may attach its console participant until the independent writer trial finishes.
    deadline = time.monotonic() + 145
    while True:
        try:
            require_sole_client(process_list)
            return
        except RuntimeError:
            if (area / "abort").exists() or time.monotonic() >= deadline:
                raise
        time.sleep(.1)


def query(runas, area, *, launch_role=None):
    """Run the listing or launch the fixed Basic User participant and capture the native screen."""
    import msvcrt

    arguments = [runas, "/showtrustlevels"]
    if launch_role is not None:
        if launch_role not in ("original", "scheduled"):
            raise ValueError("Unknown Basic User participant")
        participant = subprocess.list2cmdline([sys.executable, "-I", "-B", str(HERE / "worker.py"),
                                             "--participant", launch_role, str(area)])
        arguments = [runas, "/trustlevel:0x20000", participant]
    kernel = c.WinDLL("kernel32", use_last_error=True)
    process_list = bind(kernel, "GetConsoleProcessList", w.DWORD, c.POINTER(w.DWORD), w.DWORD)
    screen_info = bind(kernel, "GetConsoleScreenBufferInfo", w.BOOL, w.HANDLE, c.POINTER(ScreenInfo))
    read_screen = bind(kernel, "ReadConsoleOutputCharacterW", w.BOOL, w.HANDLE, w.LPWSTR, w.DWORD,
                       Coord, c.POINTER(w.DWORD))
    require_sole_client(process_list)
    # The helper's redirected stdout returns evidence to the bootstrap. Only the
    # fixed utility uses these handles, both opened on the helper's new console.
    with ExitStack() as owned:
        source = os.open("CONIN$", os.O_RDONLY | os.O_BINARY)
        owned.callback(os.close, source)
        screen = os.open("CONOUT$", os.O_RDWR | os.O_BINARY)
        owned.callback(os.close, screen)
        handle = msvcrt.get_osfhandle(screen)

        def capture():
            info = ScreenInfo()
            checked(screen_info(handle, c.byref(info)), "GetConsoleScreenBufferInfo")
            used = used_cells(info)
            size = min(info.size.x * info.size.y, MAX_CELLS)
            chars, count = c.create_unicode_buffer(size), w.DWORD()
            checked(read_screen(handle, chars, size, Coord(0, 0), c.byref(count)), "ReadConsoleOutputCharacterW")
            if count.value != size:
                raise RuntimeError("The private console returned an incomplete screen")
            return used, "".join(chars).rstrip(" \0").encode("utf-16le", errors="surrogatepass")

        cursor, before = capture()
        if cursor or before:
            raise RuntimeError("The dedicated query console was already in use")
        claim = area / (launch_role + "-console-launch.claim") if launch_role is not None else None
        if claim is not None:
            claim.touch(exist_ok=False)
        result = subprocess.run(arguments, cwd=area, stdin=source, stdout=screen,
                                stderr=screen, close_fds=True, timeout=10)
        if claim is not None:
            write(claim, {"exitCode": result.returncode})
        if claim is not None and result.returncode == 0:
            wait_for_private_screen(process_list, area)
        else:
            require_sole_client(process_list)
        _, text = capture()
        require_sole_client(process_list)
        return result.returncode, text
