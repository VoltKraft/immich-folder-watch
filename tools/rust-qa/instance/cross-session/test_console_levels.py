"""Exercise private console bounds, ownership and evidence selection without changing a token."""

import base64
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import console_levels as console
import fixture
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
            for launch, operation in ((False, "--console-levels"), (True, "--console-launch")):
                worker.console_probe(area, "scheduled", launch=launch)
                args, options = run.call_args
                self.assertEqual(args[0], [sys.executable, "-I", "-B", str(worker.HERE / "worker.py"),
                                           operation, "scheduled", str(area)])
                self.assertEqual(options["creationflags"], 0x10)
                self.assertEqual((options["startupinfo"].dwFlags, options["startupinfo"].wShowWindow), (1, 0))
                self.assertTrue(options["close_fds"])
                self.assertEqual((options["stdin"], options["stdout"], options["stderr"]),
                                 (subprocess.DEVNULL, subprocess.PIPE, subprocess.PIPE))

    def test_one_fixed_launch_requires_its_parent_and_the_observed_basic_user_level(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            runas = area / "utility"
            runas.write_bytes(b"fixture")
            parent = {"pid": os.getppid(), "sessionId": 2, "created100ns": 123}
            accounts = Mock()
            accounts.identify.return_value = (None, None, parent)
            fixture.write(area / "original-bootstrap.json", parent)
            level = {"levelListed": True, "levelCodes": ["0x20000"], "levelQueryExit": 0}
            request = {"privateConsoleQuery": level, "levelSource": "private-console-query", "launched": False,
                       "level": "0x20000", "secondaryLogonRunning": True, "launcherSha256": worker.instance.sha(runas)}
            path = area / "original-basic-user.json"
            for invalid in ({"level": "0x40000"}, {"launched": True}, {"launcherSha256": "other"},
                            {"privateConsoleQuery": {**level, "levelQueryExit": 1}},
                            {"privateConsoleQuery": {**level, "levelCodes": []}}):
                fixture.write(path, {**request, **invalid})
                with self.assertRaises(RuntimeError):
                    worker.authorize_console_launch(area, "original", accounts, runas)
            fixture.write(path, request)
            with patch.object(worker.os, "getppid", return_value=44), self.assertRaises(RuntimeError):
                worker.authorize_console_launch(area, "original", accounts, runas)
            worker.authorize_console_launch(area, "original", accounts, runas)
            accounts.identify.assert_called_with(parent["pid"], expected_image=Path(sys.executable),
                                                 expected_session=2, expected_created=123)
            (area / "original-bootstrap.json").unlink()
            (area / "original-console-launch.claim").touch()
            with patch.object(fixture, "Accounts"), self.assertRaisesRegex(RuntimeError, "no verifiable utility exit"):
                fixture.participants_exited(area)
            fixture.write(area / "original-console-launch.claim", {"exitCode": 1})
            with patch.object(fixture, "Accounts"):
                self.assertEqual(fixture.participants_exited(area), 0)
            fixture.write(area / "original-console-launch.claim", {"exitCode": 0})
            with patch.object(fixture, "Accounts"), self.assertRaisesRegex(RuntimeError, "no verifiable shutdown"):
                fixture.participants_exited(area)

    def test_native_launch_status_and_full_screen_are_separate_from_helper_failure(self):
        raw = ("A" * 2050 + " Fehler Ω").encode("utf-16le")
        for code in (0, 1, 1326):
            encoded = base64.b64encode(raw).decode("ascii")
            payload = json.dumps({"exitCode": code, "screenUtf16LeBase64": encoded}).encode()
            report = {}
            worker.record_console_launch(report, completed(0, payload))
            self.assertEqual(report["launchExit"], code)
            self.assertIs(report["launched"], code == 0)
            self.assertEqual(report["launchOutput"], worker.launch_output(raw))
            self.assertEqual(base64.b64decode(report["launchScreenUtf16LeBase64"]), raw)
        for code, screen in ((False, ""), (-1, ""), (1, "YQ=="), (0, "_"),
                             (0, base64.b64encode(bytes(console.MAX_CELLS * 2 + 2)).decode())):
            payload = json.dumps({"exitCode": code, "screenUtf16LeBase64": screen}).encode()
            with self.assertRaises(ValueError):
                worker.record_console_launch({}, completed(0, payload))
        report = {}
        with self.assertRaisesRegex(RuntimeError, "Could not observe"):
            worker.record_console_launch(report, subprocess.CompletedProcess([], 1, b"", b"unreadable"))
        self.assertEqual(report, {"consoleHelperExit": 1, "consoleDiagnostic": "unreadable"})

    def test_successful_launch_waits_for_exclusive_screen_ownership_and_respects_abort(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            with (patch.object(console, "require_sole_client", side_effect=[RuntimeError(), None]) as check,
                  patch.object(console.time, "sleep") as sleep):
                console.wait_for_private_screen(None, area)
                self.assertEqual(check.call_count, 2)
                sleep.assert_called_once()
            (area / "abort").touch()
            with patch.object(console, "require_sole_client", side_effect=RuntimeError()), self.assertRaises(RuntimeError):
                console.wait_for_private_screen(None, area)

    def test_confirmed_console_listing_launches_once_and_retains_native_exit_if_screen_read_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp)
            runas = area / "fixture.exe"
            runas.write_bytes(b"fixture")
            config = {"pythonSha256": worker.instance.sha(Path(sys.executable)),
                      "workerSha256": worker.instance.sha(worker.HERE / "worker.py")}
            def running(_, status):
                c.cast(status, c.POINTER(console.w.DWORD))[1] = 4
                return True
            api = SimpleNamespace(OpenSCManagerW=Mock(return_value=1), OpenServiceW=Mock(return_value=2),
                                  QueryServiceStatus=Mock(side_effect=running), CloseServiceHandle=Mock(return_value=True))
            def private_probe(folder, role, *, launch=False):
                if not launch:
                    return completed(0, "0x20000 (Basic User)".encode("utf-16le"))
                self.assertEqual(fixture.read(folder / (role + "-basic-user.json"))["levelSource"], "private-console-query")
                fixture.write(folder / (role + "-console-launch.claim"), {"exitCode": 1})
                return subprocess.CompletedProcess([], 1, b"", b"screen read failed")
            with (patch.object(worker, "system_runas", return_value=runas),
                  patch.object(worker.c, "WinDLL", create=True, return_value=api),
                  patch.object(worker.subprocess, "run", return_value=completed(0, b"")) as redirected,
                  patch.object(worker, "console_probe", side_effect=private_probe) as private,
                  self.assertRaisesRegex(RuntimeError, "Could not observe")):
                worker.basic_user(area, "original", config)
            self.assertEqual(redirected.call_count, 1)
            self.assertEqual(redirected.call_args.args[0], [runas, "/showtrustlevels"])
            self.assertEqual(private.call_count, 2)
            self.assertEqual([call.kwargs for call in private.call_args_list], [{}, {"launch": True}])
            report = fixture.read(area / "original-basic-user.json")
            self.assertEqual((report["launchExit"], report["consoleHelperExit"], report["launched"]), (1, 1, False))
            self.assertNotIn("launchOutput", report)

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

        runas = Path("System32/runas.exe")
        expected = [runas, "/showtrustlevels"]

        def utility(argv, **kwargs):
            nonlocal output
            self.assertEqual(argv, expected)
            self.assertEqual((kwargs["stdin"], kwargs["stdout"], kwargs["stderr"]), (20, 21, 21))
            self.assertTrue(kwargs["close_fds"])
            output = "0x00020000 (Basic User)" if len(argv) == 2 else "Native utility error"
            return completed(7, b"")

        def open_device(name, flags):
            modes.append((name, flags))
            return 19 + len(modes)

        fake = SimpleNamespace(GetConsoleProcessList=processes, GetConsoleScreenBufferInfo=info,
                               ReadConsoleOutputCharacterW=chars)
        close = Mock()
        devices = SimpleNamespace(getpid=os.getpid, O_BINARY=0, O_RDONLY=os.O_RDONLY, O_RDWR=os.O_RDWR,
                                  open=open_device, close=close)
        with (tempfile.TemporaryDirectory() as temp,
              patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: 123)}),
              patch.object(console.c, "WinDLL", create=True, return_value=fake),
              patch.object(console, "os", devices), patch.object(console.subprocess, "run", side_effect=utility)):
            area = Path(temp)
            for role in (None, "scheduled"):
                if role:
                    actor = subprocess.list2cmdline([sys.executable, "-I", "-B", str(worker.HERE / "worker.py"),
                                                     "--participant", role, str(area)])
                    expected = [runas, "/trustlevel:0x20000", actor]
                output = ""
                modes.clear()
                close.reset_mock()
                status, raw = console.query(runas, area, launch_role=role)
                self.assertEqual((status, raw.decode("utf-16le")), (7, output))
                self.assertEqual(modes, [("CONIN$", os.O_RDONLY), ("CONOUT$", os.O_RDWR)])
                self.assertEqual([entry.args[0] for entry in close.call_args_list], [21, 20])
            output = ""
            modes.clear()
            with self.assertRaises(FileExistsError):
                console.query(runas, area, launch_role="scheduled")
            with self.assertRaisesRegex(ValueError, "Unknown Basic User participant"):
                console.query(runas, area, launch_role="external command")
