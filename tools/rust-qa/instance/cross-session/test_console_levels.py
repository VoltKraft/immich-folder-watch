"""Exercise private console bounds, ownership and evidence selection without changing a token."""

import base64
import ctypes as c
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import console_levels as console
import worker


def completed(status, raw):
    return subprocess.CompletedProcess([], status, raw, b"")


class LevelQueryTests(unittest.TestCase):
    def test_launch_output_preserves_empty_binary_and_truncated_native_messages(self):
        prefix = bytes(range(256)) * 16
        for raw, truncated in ((b"", False), (b"\xff\x00\r\n", False), (prefix, False), (prefix + b"x", True)):
            with self.subTest(size=len(raw)):
                report = worker.launch_output(raw)
                self.assertEqual(report["bytes"], len(raw))
                self.assertEqual(report["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(base64.b64decode(report["prefixBase64"], validate=True), raw[:4096])
                self.assertIs(report["truncated"], truncated)

    def test_redirected_results_keep_positive_negative_and_error_authority(self):
        for status, raw, passed in ((0, b"0x20000", True), (0, b"0x40000", False), (1, b"", False),
                                    (1, b"0x20000", False)):
            with self.subTest(status=status, raw=raw):
                receipt, probe = {}, Mock()
                self.assertEqual(worker.observe_levels(receipt, completed(status, raw), probe), passed)
                probe.assert_not_called()
                self.assertEqual(receipt["levelListed"], passed)
                self.assertNotIn("privateConsoleQuery", receipt)

    def test_only_confirmed_private_console_listing_can_resolve_zero_return_and_empty_pipe(self):
        for status, raw, passed in ((0, "0x00020000 (Basic User)", True), (0, "0x40000", False),
                                    (0, "", False), (1, "0x20000", False)):
            receipt = {}
            probe = Mock(return_value=completed(status, raw.encode("utf-16le")))
            self.assertEqual(worker.observe_levels(receipt, completed(0, b""), probe), passed)
            probe.assert_called_once_with()
            self.assertFalse(receipt["levelListed"])
            self.assertEqual(receipt["levelQueryBytes"], 0)
            self.assertEqual(receipt["privateConsoleQuery"]["levelListed"], passed)
            archived = base64.b64decode(receipt["privateConsoleQuery"]["screenUtf16LeBase64"], validate=True)
            self.assertEqual(archived.decode("utf-16le"), raw)
            self.assertEqual(worker.level_inventory(status, archived)["levelListed"], passed)
            self.assertEqual(receipt.get("levelSource"), "private-console-query" if passed else None)
        for malformed in (b"x", b"x" * (console.MAX_CELLS * 2 + 2)):
            with self.assertRaisesRegex(ValueError, "evidence size"):
                worker.observe_levels({}, completed(0, b""), lambda: completed(0, malformed))

    def test_invalid_cursor_and_incomplete_console_ownership_are_refused(self):
        info = console.ScreenInfo()
        info.size = console.Coord(80, 300)
        for cursor in ((80, 0), (79, 300), (-1, 3), (64, 204)):
            info.cursor = console.Coord(*cursor)
            with self.assertRaises(ValueError):
                console.used_cells(info)
        info.cursor = console.Coord(1, 2)
        self.assertEqual(console.used_cells(info), 161)
        for count, pid in ((0, os.getpid()), (1, os.getpid() + 1), (2, os.getpid()), (3, os.getpid())):
            def other(clients, capacity):
                clients[0] = pid
                return count
            with self.assertRaises(RuntimeError):
                console.require_sole_client(other)

    def test_bootstrap_requests_a_fresh_hidden_console_and_keeps_diagnostics_separate(self):
        area = Path.cwd()
        with (patch.object(subprocess, "STARTUPINFO", create=True, new=SimpleNamespace),
              patch.object(subprocess, "STARTF_USESHOWWINDOW", create=True, new=1),
              patch.object(subprocess, "SW_HIDE", create=True, new=0),
              patch.object(subprocess, "CREATE_NEW_CONSOLE", create=True, new=0x10),
              patch.object(subprocess, "run") as run):
            worker.console_probe(area, "scheduled")
        args, options = run.call_args
        self.assertEqual(args[0], [sys.executable, "-I", "-B", str(worker.HERE / "worker.py"),
                                   "--console-levels", "scheduled", str(area)])
        self.assertEqual(options["creationflags"], 0x10)
        self.assertEqual((options["startupinfo"].dwFlags, options["startupinfo"].wShowWindow), (1, 0))
        self.assertTrue(options["close_fds"])
        self.assertEqual((options["stdin"], options["stdout"], options["stderr"]),
                         (subprocess.DEVNULL, subprocess.PIPE, subprocess.PIPE))

    def test_fixed_utility_writes_to_the_dedicated_screen_and_returns_its_actual_exit(self):
        output, modes = "", []

        def processes(clients, capacity):
            clients[0] = os.getpid()
            return 1

        def info(handle, pointer):
            self.assertEqual(handle, 123)
            value = c.cast(pointer, c.POINTER(console.ScreenInfo)).contents
            value.size, value.cursor = console.Coord(80, 25), console.Coord(0, int(bool(output)))
            return True

        def chars(handle, array, size, origin, count):
            self.assertEqual((handle, size, origin.x, origin.y), (123, 2000, 0, 0))
            array[:] = output.ljust(size)
            c.cast(count, c.POINTER(console.w.DWORD))[0] = size
            return True

        def utility(argv, **kwargs):
            nonlocal output
            self.assertEqual(argv, [Path("System32/runas.exe"), "/showtrustlevels"])
            self.assertEqual((kwargs["stdin"], kwargs["stdout"], kwargs["stderr"]), (20, 21, 21))
            self.assertTrue(kwargs["close_fds"])
            output = "0x00020000 (Basic User)"
            return completed(7, b"")

        def open_device(name, flags):
            modes.append((name, flags))
            return 19 + len(modes)

        fake = SimpleNamespace(GetConsoleProcessList=processes, GetConsoleScreenBufferInfo=info,
                               ReadConsoleOutputCharacterW=chars)
        with (patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: 123)}),
              patch.object(console.c, "WinDLL", create=True, return_value=fake),
              patch.object(console.os, "O_BINARY", create=True, new=0),
              patch.object(console.os, "open", side_effect=open_device),
              patch.object(console.os, "close") as close, patch.object(console.subprocess, "run", side_effect=utility)):
            status, raw = console.query(Path("System32/runas.exe"), Path.cwd())
        self.assertEqual((status, raw.decode("utf-16le")), (7, output))
        self.assertEqual(modes, [("CONIN$", os.O_RDONLY), ("CONOUT$", os.O_RDWR)])
        self.assertEqual([entry.args[0] for entry in close.call_args_list], [21, 20])
