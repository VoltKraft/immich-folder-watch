"""Positive and negative controls for HWND identity, changed screen pixels and clock attribution."""
from copy import deepcopy
import ctypes as c
from ctypes import wintypes as w
import io
import unittest

from witness import PHASES, Screen, Witness, color, frame_log, verify, visibility_log
from assess import visible_frames_during_work
from scan import coverage


def example():
    pid, hwnd, seed = 9, 17, 0xcb272a
    frames = [(hwnd, n, tick, tick + 2, color(seed, n)) for n, tick in ((1, 10), (2, 160), (3, 260))]
    calls = [dict(hwnd=hwnd, generation=1, action="show", start=8, end=15)]
    requests, observations = [], []
    for index in range(4):
        action = "reopen" if index % 2 else "close"
        issued = 100 + 50 * index
        requests.append(dict(action=action, hwnd=hwnd, issuedQpc=issued, responseQpc=issued + 9))
        calls.append(dict(hwnd=hwnd, generation=1 + (index + 1) // 2, action="show" if index % 2 else "hide",
                          start=issued + 3, end=issued + 13))
        for offset in range(2):
            number = 2 * index + offset
            phase = PHASES[number % 4][0]
            generation = 1 + (number + 1) // 4
            visible = number % 4 in (0, 3)
            rgb = color(seed, generation)
            when = issued + 17 if offset else issued - 12
            observations.append(dict(phase=phase, action=action, generation=generation, visible=visible, pid=pid,
                                     hwnd=hwnd, start=when, end=when + 4, pixels=[rgb, rgb ^ 0xffffff] if visible else [],
                                     pixelQpc=[when + 1, when + 3] if visible else []))
    return dict(seed=seed, pid=pid, hwnd=hwnd, frames=frames, calls=calls, requests=requests, witnesses=observations)


class EvidenceTests(unittest.TestCase):
    def test_realistic_observation_can_precede_showwindow_return_and_visible_frame(self):
        verify(**example())

    def test_independent_pixels_changed_on_each_reopen(self):
        d = example()
        d["witnesses"][3]["pixels"] = d["witnesses"][0]["pixels"]
        with self.assertRaisesRegex(ValueError, "pixels"):
            verify(**d)
        d = example()
        d["witnesses"][0]["pixels"].pop()
        with self.assertRaisesRegex(ValueError, "pixels"):
            verify(**d)

    def test_refuses_missing_extra_or_stale_evidence(self):
        original = example()
        for key, ind, patch in (
            ("calls", 1, {"end": 2}), ("calls", 2, {"start": 299}),
            ("witnesses", 1, {"pixels": [123]}), ("witnesses", 0, {"pid": 13}),
            ("witnesses", 4, {"generation": 1}), ("witnesses", 3, {"visible": False}),
            ("witnesses", 3, {"pixelQpc": [120, 121]}), ("witnesses", 2, {"pixelQpc": [120, 121]}),
            ("witnesses", 6, {"end": 255}), ("witnesses", 5, {"start": 198}),
            ("requests", 3, {"hwnd": 18}), ("requests", 2, {"action": "reopen"}),
        ):
            with self.subTest(key=key, ind=ind, patch=patch):
                data = deepcopy(original)
                data[key][ind].update(patch)
                with self.assertRaises(ValueError):
                    verify(**data)
        for key in ("frames", "calls", "requests", "witnesses"):
            with self.subTest(key=key):
                data = deepcopy(original)
                data[key].pop()
                with self.assertRaises(ValueError):
                    verify(**data)
        data = deepcopy(original)
        data["frames"][1] = (17, 2, 120, 123, color(data["seed"], 2))
        with self.assertRaisesRegex(ValueError, "previously"):
            verify(**data)

    def test_windows_reports_require_complete_lines_and_checked_layout(self):
        text = "GDI_VISIBILITY 17 2 show 102 110\r\nGDI_FRAME 17 2 107 109 881122\r\nGDI_FRAME 17 3 11"
        self.assertEqual(frame_log(text), [(17, 2, 107, 109, 0x881122)])
        self.assertEqual(visibility_log(text), [dict(hwnd=17, generation=2, action="show", start=102, end=110)])
        observer = object.__new__(Witness)
        observer.stream = io.BytesIO(b"GDI_FRAME 17 2 107 109")
        observer.partial, observer.frames = b"", []
        observer.read_frames()
        self.assertEqual(observer.frames, [])
        observer.stream = io.BytesIO(b" 881122\r\nGDI_VISIBILITY ignored")
        observer.read_frames()
        self.assertEqual(observer.frames, frame_log(text))

    def test_scan_requires_external_visibility_flush_and_real_pixels_in_file_work(self):
        lines = ["READY 42 rust", "COUNTS 750000 2300000 0 0 0 0 0 0"]
        for sweep, origin in enumerate((100, 200000)):
            lines.extend(f"D {sweep} {d} {origin + d * 1000} 1000" for d in range(100))
            lines.extend(f"B {sweep} {origin + i * 32 + 1} {origin + i * 32 + 32} 32" for i in range(3125))
        trace = "\n".join([*lines, "COMPLETE"])
        requests, rows, frames = [], [], [(17, 1, 300, 305, 0)]
        for i in range(10):
            lo = 99000 + 120 * i
            requests.append(dict(action="reopen" if i % 2 else "close", hwnd=17, issuedQpc=lo, responseQpc=lo + 4))
            if i % 2:
                frames.append((17, len(frames) + 1, lo + 3, lo + 8, 0))
            for offset in (-5, 10):
                rows.append(dict(generation=len(frames), pixelQpc=[lo + offset, lo + offset + 1]))
        scan = coverage(trace, requests, 100101, 300001, 10000, 42, "rust")
        scan.update(allRequests=requests, nativeWitness=dict(observations=rows, frames=frames), inventoryPid=42)
        found = visible_frames_during_work(scan, trace, 10000)
        self.assertEqual(found, {"close": [0, 2, 4, 6, 8], "reopen": [1, 3, 5, 7, 9]})
        for key in ("frames", "observations"):
            with self.subTest(key=key):
                changed = deepcopy(scan)
                if key == "frames":
                    changed["nativeWitness"]["frames"][-1] = (17, 6, 100102, 100103, 0)
                else:
                    changed["nativeWitness"]["observations"][-1]["pixelQpc"] = [100102, 100103]
                with self.assertRaises(ValueError):
                    visible_frames_during_work(changed, trace, 10000)

    def test_screen_read_requires_both_owned_points_before_and_after_sampling(self):
        screen = object.__new__(Screen)
        def rectangle(_hwnd, pointer):
            rect = c.cast(pointer, c.POINTER(w.RECT)).contents
            rect.left, rect.top, rect.right, rect.bottom = 0, 0, 640, 400
            return True
        screen.rect = rectangle
        screen.client = lambda _hwnd, _p: True
        reads, releases = [], []
        screen.get_dc = lambda _: 3
        screen.release_dc = lambda _hwnd, dc: releases.append(dc) or True
        screen.pixel = lambda _dc, x, y: reads.append((x, y)) or (0x563412 if y == 100 else 0xa9cbed)
        for owners, expected, read in (([17, 18], None, False), ([17, 17, 17, 18], None, True),
                                       ([17] * 4, [0x123456, 0xedcba9], True)):
            with self.subTest(owners=owners):
                values = iter(owners)
                screen.at = lambda _point: next(values)
                reads.clear()
                releases.clear()
                self.assertEqual(screen.sample(17), expected)
                self.assertEqual(reads, [(320, 100), (320, 300)] if read else [])
                self.assertEqual(releases, [3] if read else [])


if __name__ == "__main__":
    unittest.main()
