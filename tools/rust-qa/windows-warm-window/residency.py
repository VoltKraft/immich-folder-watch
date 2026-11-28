"""Count resident pages of an already owned process without reading or changing their contents."""
from collections import Counter
import ctypes as c
from pathlib import PureWindowsPath


class Region(c.Structure):
    _fields_ = [("base", c.c_void_p), ("allocation", c.c_void_p), ("allocation_protect", c.c_uint32),
                ("partition", c.c_uint16), ("size", c.c_size_t), ("state", c.c_uint32),
                ("protect", c.c_uint32), ("kind", c.c_uint32)]


def sample(api, handle):
    from native import bind
    if c.sizeof(Region) != 48 or c.sizeof(c.c_size_t) != 8:
        raise ValueError("Expected the native 64-bit Windows layout")
    k = api.kernel
    system = (c.c_uint32 * 16)()
    bind(k, "GetSystemInfo", None, c.c_void_p)(system)
    page = system[1]
    if page < 4096 or page & (page - 1):
        raise ValueError("Unexpected native page size")
    working = bind(k, "K32QueryWorkingSet", c.c_int, c.c_void_p, c.c_void_p, c.c_uint32)
    query = bind(k, "VirtualQueryEx", c.c_size_t, c.c_void_p, c.c_void_p, c.POINTER(Region), c.c_size_t)
    mapped = bind(k, "K32GetMappedFileNameW", c.c_uint32, c.c_void_p, c.c_void_p, c.c_wchar_p, c.c_uint32)
    capacity = 65536
    for _ in range(4):
        blocks = (c.c_size_t * (1 + capacity))()
        if working(handle, blocks, c.sizeof(blocks)):
            break
        if c.get_last_error() != 24 or not capacity < blocks[0] < 2_000_000:
            raise c.WinError(c.get_last_error())
        capacity = blocks[0] + 8192
    else:
        raise RuntimeError("The resident page snapshot did not stabilize")
    if not 0 < blocks[0] <= capacity:
        raise ValueError("Invalid resident page count")
    end = 0
    by_type, images, shareable = Counter(), Counter(), 0
    names = {}
    for entry in sorted(blocks[1:blocks[0] + 1]):
        address = (entry >> 12) * page
        if address >= end:
            region = Region()
            if query(handle, address, c.byref(region), c.sizeof(region)) != c.sizeof(region):
                raise c.WinError(c.get_last_error())
            end = (region.base or 0) + region.size
            if not (region.base or 0) <= address < end:
                raise ValueError("Invalid memory region for the owned process")
        category = {0x1000000: "image", 0x40000: "mapped", 0x20000: "private"}.get(region.kind, "unclassified")
        by_type[category] += page
        if category == "image":
            if region.allocation not in names:
                name = c.create_unicode_buffer(32768)
                length = mapped(handle, address, name, len(name))
                names[region.allocation] = PureWindowsPath(name.value).name.casefold() if 0 < length < len(name) else "unresolved"
            images[names[region.allocation]] += page
        if entry & (1 << 8):
            shareable += page
    return dict(pageSize=page, residentBytes=blocks[0] * page, regionBytes=dict(by_type),
                shareableBytes=shareable, imageBytes=dict(images.most_common()))
