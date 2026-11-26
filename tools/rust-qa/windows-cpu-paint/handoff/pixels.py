"""Read three physical 5 by 5 screen regions wholly belonging to the observed visible HWND."""
import ctypes as c
from ctypes import wintypes as w

SIDE = 5
HEADER = b"P6\n15 5\n255\n"
RED, GREEN, BLACK, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 0), (0, 0, 255)
EXPECTED = ((RED, RED, BLACK), (RED, GREEN, BLACK), (RED, GREEN, BLUE))


def colors(data, phase):
    payload = data[len(HEADER):]
    if not data.startswith(HEADER) or len(payload) != 3 * SIDE * SIDE * 3:
        raise ValueError("Invalid captured RGB tile geometry")
    for y in range(SIDE):
        for x in range(SIDE * 3):
            offset = (y * SIDE * 3 + x) * 3
            if any(abs(actual - want) > 2 for actual, want in zip(payload[offset:offset + 3], EXPECTED[phase][x // SIDE], strict=True)):
                return False
    return True


def sample(api, windows, root, centers):
    from native import bind, checked
    user, gdi = c.WinDLL("user32", use_last_error=True), c.WinDLL("gdi32", use_last_error=True)
    hwnd = root["hwnd"]
    if windows.visible() != hwnd or len(centers) != 3:
        raise ValueError("The original texture window is no longer visible")
    client = bind(user, "ClientToScreen", w.BOOL, w.HWND, c.POINTER(w.POINT))
    at_point = bind(user, "WindowFromPoint", w.HWND, w.POINT)
    get_dc = bind(user, "GetDC", w.HDC, w.HWND)
    release = bind(user, "ReleaseDC", c.c_int, w.HWND, w.HDC)
    pixel = bind(gdi, "GetPixel", w.DWORD, w.HDC, c.c_int, c.c_int)
    origin = w.POINT(0, 0)
    checked(client(hwnd, c.byref(origin)))
    screen = [[x + origin.x, y + origin.y] for x, y in centers]
    if any(not 2 <= x < root["width"] - 2 or not 2 <= y < root["height"] - 2 for x, y in centers):
        raise ValueError("Texture samples fall outside the original client")
    start = api.clock()
    dc = checked(get_dc(None))
    pixels = bytearray(HEADER)
    try:
        for dy in range(-2, 3):
            for cx, cy in screen:
                for dx in range(-2, 3):
                    x, y = cx + dx, cy + dy
                    if at_point(w.POINT(x, y)) != hwnd:
                        raise ValueError("The visible screen sample is covered by another window")
                    rgb = pixel(dc, x, y)
                    if at_point(w.POINT(x, y)) != hwnd:
                        raise ValueError("The native sample lost the original root during readback")
                    if rgb == 0xffffffff:
                        raise OSError("GetPixel could not read a visible desktop pixel")
                    pixels.extend((rgb & 255, (rgb >> 8) & 255, (rgb >> 16) & 255))
    finally:
        checked(release(None, dc))
    after = w.POINT(0, 0)
    checked(client(hwnd, c.byref(after)))
    if (after.x, after.y) != (origin.x, origin.y) or windows.visible() != hwnd:
        raise ValueError("The visible root moved during the pixel sample")
    return bytes(pixels), dict(clientCenters=centers, screenCenters=screen, origin=[origin.x, origin.y], boundsQpc=[start, api.clock()])
