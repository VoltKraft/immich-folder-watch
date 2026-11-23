"""Read the Windows contrast palette and verify a reversible change on a disposable runner."""
from collections import Counter
import ctypes as c
from dataclasses import dataclass
from pathlib import Path
import hashlib
import struct
import time


COLOR_INDEX = {"window": 5, "text": 8, "highlight": 13, "highlightText": 14,
               "button": 15, "disabledText": 17, "buttonText": 18, "link": 26}
ON, AVAILABLE, OPTION_NO_THEME_CHANGE = 0x1, 0x2, 0x1000


class HighContrast(c.Structure):
    _fields_ = [("size", c.c_uint32), ("flags", c.c_uint32), ("scheme", c.c_void_p)]


@dataclass(frozen=True)
class State:
    flags: int
    scheme: str | None
    colors: dict

    @property
    def enabled(self):
        return bool(self.flags & ON)


class SystemColors:
    def __init__(self, bind, check):
        user = c.WinDLL("user32", use_last_error=True)
        kernel = c.WinDLL("kernel32", use_last_error=True)
        self.parameters = bind(user, "SystemParametersInfoW", c.c_int, c.c_uint32, c.c_uint32,
                               c.POINTER(HighContrast), c.c_uint32)
        self.color = bind(user, "GetSysColor", c.c_uint32, c.c_int)
        self.free = bind(kernel, "LocalFree", c.c_void_p, c.c_void_p)
        self.check = check

    def read(self):
        value = HighContrast(c.sizeof(HighContrast), 0, None)
        self.check(self.parameters(0x42, value.size, c.byref(value), 0), "SPI_GETHIGHCONTRAST")
        try:
            scheme = c.wstring_at(value.scheme) if value.scheme else None
        finally:
            if value.scheme and self.free(value.scheme):
                raise OSError("Could not release the Windows high contrast scheme name")
        colors = {}
        for role, index in COLOR_INDEX.items():
            colorref = self.color(index)
            colors[role] = [(colorref >> shift) & 255 for shift in (0, 8, 16)]
        return State(value.flags, scheme, colors)

    def set_mode(self, original, enabled):
        flags = (original.flags & ~(ON | OPTION_NO_THEME_CHANGE)) | int(enabled)
        name = c.create_unicode_buffer(original.scheme) if original.scheme is not None else None
        value = HighContrast(c.sizeof(HighContrast), flags, c.cast(name, c.c_void_p))
        # SPIF_SENDCHANGE broadcasts the setting. Do not request SPIF_UPDATEINIFILE.
        self.check(self.parameters(0x43, value.size, c.byref(value), 0x2), "SPI_SETHIGHCONTRAST")


def await_state(read, condition, label, timeout=15):
    deadline = time.monotonic() + timeout
    previous, since = None, None
    while True:
        state = read()
        if state != previous or not condition(state):
            previous, since = state, None
        elif since is None:
            since = time.monotonic()
        elif time.monotonic() - since >= .5:
            return state
        if time.monotonic() >= deadline:
            raise TimeoutError(label)
        time.sleep(.1)


def cleanup_read(system):
    for attempt in range(3):
        try:
            return system.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(.15 * (attempt + 1))


def owned_transition(original, observed):
    return (observed.enabled != original.enabled
            and not ((observed.flags ^ original.flags) & ~(ON | OPTION_NO_THEME_CHANGE))
            and (original.scheme is None or observed.scheme == original.scheme))


def restore(system, original, record, wait):
    def read():
        return cleanup_read(system)
    live = read()
    if live.enabled != original.enabled:
        expected = record.get("changed")
        # After a partly failed SET there is no confirmed replacement snapshot.
        # Only restore the exact original scheme and other flags in that case.
        expected_match = vars(live) == expected if expected is not None else live.scheme == original.scheme
        if not owned_transition(original, live) or not expected_match:
            raise RuntimeError("Another accessibility setting changed before restoration")
        try:
            system.set_mode(original, original.enabled)
        except OSError as error:
            record["restoreReportedError"] = str(error)
            # Windows can return an error after applying a setting. Only retry
            # if the exact still-owned state survived the first attempt.
            after = read()
            if after == live:
                try:
                    system.set_mode(original, original.enabled)
                except OSError as retry_error:
                    record["restoreRetryReportedError"] = str(retry_error)
    restored = wait(read, lambda state: state == original, "Windows did not restore the original flags, scheme and colors")
    record["restored"] = vars(restored)
    record["restoreVerified"] = True
    return restored


def contrast_cycle(system, session_guard, window_guard, capture, record, wait=await_state):
    """Only the outer supervisor changes settings. Its capture worker may exit at any phase."""
    session_guard()
    window_guard()
    original = system.read()
    if not original.flags & AVAILABLE:
        raise RuntimeError("Windows did not report an available high contrast setting")
    record["original"] = vars(original)
    first = record["originalFrame"] = capture("original", original)
    session_guard()
    if system.read() != original:
        raise RuntimeError("System appearance changed during the baseline observation")
    window_guard()
    record["restoreVerified"] = False
    try:
        system.set_mode(original, not original.enabled)
        before = wait(system.read, lambda state: state.enabled != original.enabled, "Windows did not change contrast mode")
        if not owned_transition(original, before):
            raise RuntimeError("A different contrast scheme or accessibility flag appeared during the change")
        record["changed"] = vars(before)
        window_guard()
        record["changedFrame"] = capture("changed", before)
        if system.read() != before:
            raise RuntimeError("The Windows palette changed during the second observation")
    finally:
        session_guard()
        restored = restore(system, original, record, wait)
    window_guard()
    last = record["restoredFrame"] = capture("restored", restored)
    if (system.read() != original or first["rasterSha256"] != last["rasterSha256"]
            or record["changedFrame"]["rasterSha256"] == first["rasterSha256"]):
        raise ValueError("The owned label did not change and then return to its original pixels")


def label_bitmap(path):
    """Read the small 24-bit BGR bitmap captured exclusively from the owned UIA label."""
    data = Path(path).read_bytes()
    if len(data) < 54 or data[:2] != b"BM" or struct.unpack_from("<I", data, 2)[0] != len(data):
        raise ValueError("Invalid Windows label bitmap")
    start, header, width, height, planes, bits, compression = struct.unpack_from("<IIiiHHI", data, 10)
    stride = (3 * width + 3) & ~3
    if (header != 40 or start != 54 or (planes, bits, compression) != (1, 24, 0)
            or not 4 <= width <= 512 or not 4 <= height <= 96 or start + height * stride != len(data)):
        raise ValueError("Unexpected label dimensions, compression or pixel layout")
    colors = Counter()
    raster = hashlib.sha256(struct.pack("<II", width, height))
    for y in reversed(range(height)):
        row = data[start+y*stride:start+y*stride+3*width]
        raster.update(row)  # Top-to-bottom packed BGR pixels, excluding BMP headers and row padding.
        colors.update(zip(row[2::3], row[1::3], row[::3]))
    return width, height, colors, raster.hexdigest()


def label_colors(colors, state):
    paper, count = colors.most_common(1)[0]
    total = sum(colors.values())
    if count * 2 <= total or len(colors) < 3:
        raise ValueError("No distinct static label ink and panel background")
    report = {"paper": list(paper), "paperPixels": count, "pixels": total}
    if state.enabled:
        text = tuple(state.colors["text"])
        separation = max(abs(a - b) for a, b in zip(paper, text))
        tolerance = max(2, min(24, separation // 8))
        ink = sum(n for rgb, n in colors.items() if max(abs(a-b) for a,b in zip(rgb, text)) <= tolerance)
        report["systemTextPixels"] = ink
        if tuple(state.colors["window"]) != paper or separation <= 2 * tolerance or ink < 4:
            raise ValueError("The rendered label does not use the live Windows window and text colors")
    return report
