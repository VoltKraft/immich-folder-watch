"""Read two pixels of the owned visible HWND and correlate them with GDI's flushed frames."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path

WIDTH, HEIGHT = 640, 400
PHASES = (("before", "close"), ("after", "close"), ("before", "reopen"), ("after", "reopen"))


def color(seed, generation):
    return (seed + generation * 0x5bc189) & 0xffffff


def frame_log(text):
    frames = []
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n") or not line.startswith("GDI_FRAME "):
            continue
        _, hwnd, generation, start, end, rgb = line.split()
        frames.append((int(hwnd), int(generation), int(start), int(end), int(rgb, 16)))
    return frames


def visibility_log(text):
    calls = []
    for line in text.splitlines(keepends=True):
        if line.endswith("\n") and line.startswith("GDI_VISIBILITY "):
            _, hwnd, generation, action, start, end = line.split()
            calls.append(dict(hwnd=int(hwnd), generation=int(generation), action=action, start=int(start), end=int(end)))
    return calls


def verify(seed, pid, hwnd, frames, calls, requests, witnesses):
    """Recheck every measurement against the unmodified observer timestamps and original frame log."""
    if not requests or len(witnesses) != 2 * len(requests) or not pid or not hwnd:
        raise ValueError("Missing complete native visibility witnesses")
    expected_frames = 1 + sum(row["action"] == "reopen" for row in requests)
    if len(frames) != expected_frames:
        raise ValueError("Missing or extra GDI frame")
    last = 0
    for sequence, (owner, generation, start, end, rgb) in enumerate(frames, 1):
        if (owner, generation, rgb) != (hwnd, sequence, color(seed, sequence)) or not last < start <= end:
            raise ValueError("GDI frame sequence, clock, marker or owner differs")
        last = end
    if (len(calls) != 1 + len(requests) or calls[0]["hwnd"] != hwnd or calls[0]["generation"] != 1
            or calls[0]["action"] != "show" or not 0 < calls[0]["start"] <= calls[0]["end"]):
        raise ValueError("Incomplete native ShowWindow coverage")
    last = 0
    for index, request in enumerate(requests):
        before, after = witnesses[2 * index:2 * index + 2]
        issued, response = request["issuedQpc"], request["responseQpc"]
        if (request["hwnd"] != hwnd or request["action"] != ("reopen" if index % 2 else "close")
                or not last <= before["start"] <= before["end"] <= issued <= response <= after["start"] <= after["end"]):
            raise ValueError("The pixel controls changed or overlapped the visibility measurement")
        last = after["end"]
        call = calls[index + 1]
        if (call["hwnd"] != hwnd or call["action"] != ("hide" if index % 2 == 0 else "show")
                or call["generation"] != 1 + (index + 1) // 2
                or not issued <= call["start"] <= response or call["end"] < call["start"]
                or call["start"] < calls[index]["end"]):
            raise ValueError("Native ShowWindow call differs from its external request")
        for position, witness in enumerate((before, after), 2 * index):
            phase, action = PHASES[position % 4]
            generation = 1 + (position + 1) // 4
            visible = (phase, action) in (("before", "close"), ("after", "reopen"))
            if ((witness["phase"], witness["action"], witness["hwnd"], witness["pid"], witness["generation"],
                 witness["visible"]) != (phase, action, hwnd, pid, generation, visible)):
                raise ValueError("Unexpected HWND state, owner or generation")
            if visible:
                rgb = color(seed, generation)
                pixel_span = witness["pixelQpc"]
                if (witness["pixels"] != [rgb, rgb ^ 0xffffff] or len(pixel_span) != 2 or not
                        max(witness["start"], frames[generation - 1][3]) <= pixel_span[0] <= pixel_span[1] <= witness["end"]):
                    raise ValueError("Visible pixels did not match the flushed GDI frame")
                if action == "reopen" and frames[generation - 1][2] < issued:
                    raise ValueError("Reopen reused a previously flushed GDI frame")
            elif witness["pixels"] or witness["pixelQpc"]:
                raise ValueError("Hidden window was sampled as a visible surface")


class Screen:
    def __init__(self, bind):
        u, g = c.WinDLL("user32", use_last_error=True), c.WinDLL("gdi32", use_last_error=True)
        self.client = bind(u, "ClientToScreen", w.BOOL, w.HWND, c.POINTER(w.POINT))
        self.rect = bind(u, "GetClientRect", w.BOOL, w.HWND, c.POINTER(w.RECT))
        self.is_window = bind(u, "IsWindow", w.BOOL, w.HWND)
        self.owner = bind(u, "GetWindowThreadProcessId", w.DWORD, w.HWND, c.POINTER(w.DWORD))
        self.is_visible = bind(u, "IsWindowVisible", w.BOOL, w.HWND)
        self.peek = bind(u, "PeekMessageW", w.BOOL, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT)
        self.dispatch = bind(u, "DispatchMessageW", w.LPARAM, c.POINTER(w.MSG))
        self.at = bind(u, "WindowFromPoint", w.HWND, w.POINT)
        self.get_dc = bind(u, "GetDC", w.HDC, w.HWND)
        self.release_dc = bind(u, "ReleaseDC", c.c_int, w.HWND, w.HDC)
        self.pixel = bind(g, "GetPixel", w.DWORD, w.HDC, c.c_int, c.c_int)

    def pump(self):
        message = w.MSG()
        while self.peek(c.byref(message), None, 0, 0, 1):
            self.dispatch(c.byref(message))

    def sample(self, hwnd, observation):
        rect = w.RECT()
        if not self.rect(hwnd, c.byref(rect)):
            observation["stage"] = "GetClientRect"
            return None
        bounds = [rect.left, rect.top, rect.right, rect.bottom]
        observation["clientRect"] = bounds
        if bounds != [0, 0, WIDTH, HEIGHT]:
            observation["stage"] = "client-size"
            return None
        points = [w.POINT(WIDTH // 2, HEIGHT // 4), w.POINT(WIDTH // 2, 3 * HEIGHT // 4)]
        if not all(self.client(hwnd, c.byref(point)) for point in points):
            observation["stage"] = "ClientToScreen"
            return None
        observation["points"] = [[point.x, point.y] for point in points]
        owned = [self.at(point) == hwnd for point in points]
        if not all(owned):
            observation.update(stage="point-ownership-before", owned=owned)
            return None
        dc = self.get_dc(None)
        if not dc:
            raise OSError("Could not obtain the screen DC")
        try:
            values = [self.pixel(dc, p.x, p.y) for p in points]
        finally:
            if not self.release_dc(None, dc):
                raise OSError("Could not release the screen DC")
        owned = [self.at(point) == hwnd for point in points]
        if not all(owned):
            observation.update(stage="point-ownership-after", owned=owned)
            return None
        if 0xffffffff in values:
            observation.update(stage="GetPixel", invalid=[v == 0xffffffff for v in values])
            return None
        # GetPixel returns COLORREF (0x00bbggrr), while 32-bit BI_RGB stores 0x00rrggbb.
        return [((v & 255) << 16) | (v & 0xff00) | (v >> 16) for v in values]


class Witness:
    def __init__(self, api, fixture, lifetime, stack, await_value, token, log):
        self.api, self.lifetime, self.stack = api, lifetime, stack
        self.await_value, self.seed, self.log = await_value, int(token[:6], 16), Path(log)
        self.screen = Screen(fixture.bind)
        self.hwnd = self.pid = None
        self.rows = []
        self.partial = b""
        self.frames = []

    def read_frames(self):
        data = self.partial + self.stream.read(65536)
        whole, newline, self.partial = data.rpartition(b"\n")
        if newline:
            self.frames.extend(frame_log((whole + newline).decode("utf-8")))

    def __call__(self, phase, action, hwnd, pid):
        start = self.api.clock()
        if self.hwnd is None:
            self.hwnd, self.pid = hwnd, pid
            self.stream = self.stack.enter_context(self.log.open("rb"))
            self.life = self.lifetime(pid)
            self.stack.callback(self.life.close)
        index = len(self.rows)
        if (self.hwnd, self.pid) != (hwnd, pid) or (phase, action) != PHASES[index % 4]:
            raise ValueError("Control was rebound to a different window, process or phase")
        generation = 1 + (index + 1) // 4
        visible = (phase, action) in (("before", "close"), ("after", "reopen"))
        rgb = color(self.seed, generation)
        last = {}
        attempts = 0

        def observe():
            nonlocal attempts
            attempts += 1
            last.clear()
            owner = w.DWORD()
            thread = self.screen.owner(hwnd, c.byref(owner))
            self.screen.pump()
            if (not self.screen.is_window(hwnd) or not thread or owner.value != pid
                    or any(handle == hwnd for handle, _, _ in self.life.events)):
                raise RuntimeError("The original HWND did not survive the observation")
            if bool(self.screen.is_visible(hwnd)) != visible:
                last["stage"] = "window-visibility"
                return None
            if not visible:
                return {"pixels": [], "pixelQpc": []}
            self.read_frames()
            if len(self.frames) < generation:
                last.update(stage="frame-log", flushedFrames=len(self.frames))
                return None
            owner, sequence, _, _, claimed = self.frames[generation - 1]
            if (owner, sequence, claimed) != (hwnd, generation, rgb):
                raise ValueError("The flushed GDI frame does not match the expected generation")
            # The external attribution reads only these two owned screen positions.
            pixel_start = self.api.clock()
            pixels = self.screen.sample(hwnd, last)
            pixel_end = self.api.clock()
            if pixels != [rgb, rgb ^ 0xffffff]:
                if pixels is not None:
                    last.update(stage="frame-color", ownedPixels=pixels, expected=[rgb, rgb ^ 0xffffff])
                return None
            return {"pixels": pixels, "pixelQpc": [pixel_start, pixel_end]}

        label = f"No owned GDI frame {generation} for {phase} {action}"
        try:
            pixels = self.await_value(observe, label, timeout=4, delay=.004)
        except TimeoutError as error:
            raise WitnessTimeout(label, {"hwnd": hwnd, "pid": pid, "phase": phase, "action": action,
                                        "generation": generation, "attempts": attempts, "last": last}) from error
        self.rows.append(dict(phase=phase, action=action, hwnd=hwnd, pid=pid, generation=generation,
                              visible=visible, start=start, end=self.api.clock(), **pixels))

    def finish(self, requests):
        def destroyed():
            self.screen.pump()
            return [kind for handle, kind, _ in self.life.events if handle == self.hwnd] == ["destroy"]
        self.await_value(destroyed, "No unique destruction event for the retained HWND", timeout=4)
        owner = w.DWORD()
        if self.screen.is_window(self.hwnd) and self.screen.owner(self.hwnd, c.byref(owner)) and owner.value == self.pid:
            raise ValueError("Owned HWND remains after Quit")
        text = self.log.read_text(encoding="utf-8", errors="strict")
        frames = frame_log(text)
        calls = visibility_log(text)
        verify(self.seed, self.pid, self.hwnd, frames, calls, requests, self.rows)
        if [line for line in text.splitlines() if line.startswith("DRAINED ")] != [f"DRAINED passes={len(frames)}"]:
            raise ValueError("The GDI supervisor did not drain after the observed frame sequence")
        return dict(hwnd=self.hwnd, pid=self.pid, seed=self.seed, events=self.life.events, frames=frames, showWindow=calls,
                    observations=self.rows)


class WitnessTimeout(TimeoutError):
    def __init__(self, label, observation):
        super().__init__(label)
        self.observation = observation
