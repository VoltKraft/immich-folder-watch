"""Check evidence qualification without substituting test data for Windows observations."""

import ctypes as c
import hashlib
from pathlib import Path
import runpy
import struct
import tempfile
import unittest
import zlib

DRIVER = runpy.run_path(str(Path(__file__).with_name("run.py")))
from topology import DisplayPath, Mode, Source, Target, Topology, active_input


def png(path, width, height, changed):
    def block(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = b"".join(b"\0" + b"".join((b"\xee" if changed and x < 8 and y < 4 else b"\x10") * 3
                                  for x in range(width)) for y in range(height))
    raw = b"\x89PNG\r\n\x1a\n" + block(b"IHDR", header) + block(b"IDAT", zlib.compress(data)) + block(b"IEND", b"")
    path.write_bytes(raw)
    return {"width": width, "height": height, "sha256": hashlib.sha256(raw).hexdigest()}


class DisplayTests(unittest.TestCase):
    def test_remote_input_uses_the_own_active_unlocked_session(self):
        context = {"session": 3, "activeConsoleSession": 1, "windowStation": "WinSta0", "stationVisible": True,
                   "inputDesktop": "Default", "threadDesktop": "Default", "threadReceivesInput": True,
                   "inputObjectReceivesInput": True, "wts": {"session": 3, "connectionState": 0, "lockFlags": 1}}
        rdp = {"code": 2, "status": "observed"}
        self.assertTrue(active_input(context, rdp))
        self.assertFalse(active_input(context, {"code": 0, "status": "observed"}))
        self.assertFalse(active_input(context, {"status": "unavailable"}))
        for key, value in (("inputDesktop", "Winlogon"), ("threadReceivesInput", False), ("stationVisible", False),
                           ("wts", {"session": 3, "connectionState": 0, "lockFlags": 0})):
            self.assertFalse(active_input({**context, key: value}, rdp))
        self.assertTrue(active_input({**context, "activeConsoleSession": 3}, {"code": 0, "status": "observed"}))

    def test_one_monitor_or_equal_dpi_cannot_create_a_target(self):
        first = {"handle": "0x1", "dpi": 96}
        same = {"handle": "0x2", "dpi": 96}
        other = {"handle": "0x3", "dpi": 120}
        for rows in ([first], [first, same]):
            self.assertEqual(DRIVER["choose_monitor"]({"monitors": rows}, "0x1"), (first, None))
        self.assertEqual(DRIVER["choose_monitor"]({"monitors": [other, same, first]}, "0x2"), (same, other))
        with self.assertRaises(ValueError):
            DRIVER["choose_monitor"]({"monitors": [first]}, "other")

    def test_query_display_config_abi_and_remote_access_errors(self):
        self.assertEqual([c.sizeof(t) for t in (Source, Target, DisplayPath, Mode)], [20, 48, 72, 64])
        self.assertEqual([DisplayPath.target.offset, DisplayPath.flags.offset, Mode.data.offset], [20, 68, 16])
        native = Topology.__new__(Topology)
        for code, status in ((5, "unavailable"), (50, "unavailable"), (87, "failed")):
            native.buffer_sizes = lambda *_: code
            self.assertEqual(native.active_paths({}), {"status": status, "api": "GetDisplayConfigBufferSizes", "win32": code})

    def test_active_paths_retry_and_join_the_queried_source_monitor(self):
        native = Topology.__new__(Topology)
        def sizes(flags, count, modes):
            self.assertEqual(flags, 2)
            count._obj.value = modes._obj.value = 1
            return 0
        calls = []
        def query(flags, count, rows, mode_count, modes, topology_id):
            self.assertIsNone(topology_id)
            calls.append(flags)
            if len(calls) == 1:
                return 122
            rows[0].source.id = modes[0].id = 4
            rows[0].target.id, rows[0].flags, modes[0].type = 7, 1, 1
            modes[0].data.source.width, modes[0].data.source.height = 1440, 900
            return 0
        def source_name(ptr):
            ptr._obj.device = "DISPLAY3"
            return 0
        native.buffer_sizes, native.query, native.source_name = sizes, query, source_name
        rows = native.active_paths({"display3": 2})["paths"]
        self.assertEqual(calls, [2, 2])
        self.assertEqual((rows[0]["monitor"], rows[0]["sourceMode"], rows[0]["active"]), (2, [0, 0, 1440, 900], True))

    def test_uia_geometry_must_match_both_subject_and_physical_display(self):
        row = {"status": "observed", "pid": 1, "hwnd": 2, "field": "Dateiname", "expectedText": "fixture",
               "dpi": 144, "rect": [-800, 80, -500, 110]}
        layout = {"pid": 1, "hwnd": 2, "awareness": 2, "dpi": 144, "monitor": "left", "client": [-900, 0, -300, 400]}
        monitor = {"handle": "left", "dpi": 144, "bounds": [-1280, 0, 0, 800]}
        self.assertEqual(DRIVER["field_geometry"](row, layout, monitor, "fixture")["logicalFieldSizeAt96"], [200, 20])
        for key, bad in (("pid", 2), ("hwnd", 99), ("expectedText", "other"), ("dpi", 96), ("rect", [-800, 80, -200, 110])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                DRIVER["field_geometry"]({**row, key: bad}, layout, monitor, "fixture")

    def test_scaled_field_and_same_three_characters_follow_dpi_in_both_directions(self):
        a = {"dpi": 96, "rect": [0, 0, 240, 20], "prefixRect": [0, 0, 24, 15]}
        b = {"dpi": 144, "rect": [-900, 40, -540, 70], "prefixRect": [-895, 41, -859, 64]}
        self.assertEqual(DRIVER["scaled_geometry"](a, b)["fieldHeight"]["after"], 30)
        self.assertEqual(DRIVER["scaled_geometry"](b, a)["prefixWidth"]["after"], 24)
        for broken in (a, {**a, "dpi": 144}, {**b, "prefixRect": [0, 0, 24, 15]}):
            with self.assertRaises(ValueError):
                DRIVER["scaled_geometry"](a, broken)

    def test_stationary_frame_requires_own_focus_material_pixels_and_matching_image_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = [root / ("Frame.json." + role + ".png") for role in ("before", "after")]
            record = {"phase": "Frame", "focusAtEntry": True, "focusAtExit": True, "expectedText": DRIVER["FIRST"],
                      "textAfter": DRIVER["SECOND"], "before": png(a, 32, 10, False), "after": png(b, 32, 10, True),
                      "difference": {"columns": 8, "rows": 4, "pixels": 32}}
            self.assertEqual(DRIVER["frame_evidence"](record, root, 96), [a, b])
            for key, value in (("focusAtEntry", False), ("textAfter", "wrong"), ("phase", "../outside"),
                               ("difference", {"columns": 1, "rows": 8, "pixels": 8}),
                               ("after", {**record["after"], "sha256": record["before"]["sha256"]})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    DRIVER["frame_evidence"]({**record, key: value}, root, 96)
            b.write_bytes(a.read_bytes())
            with self.assertRaises(ValueError):
                DRIVER["frame_evidence"](record, root, 96)


if __name__ == "__main__":
    unittest.main()
