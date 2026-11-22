"""Check the launcher's Win64 ABI, explicit desktop, handle inheritance and cleanup contract."""

from contextlib import ExitStack
import ctypes as c
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from tempfile import TemporaryFile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

QA = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(QA / "windows-desktop"), str(QA / "windows-performance")]
import named_process as subject


TOKEN = "0123456789abcdef" * 2
IMAGE = PureWindowsPath(r"C:\fixture with spaces\subject\native-gui-assessment.exe")
CWD = IMAGE.parent.parent / "trial"


class NamedProcessTests(unittest.TestCase):
    def setUp(self):
        self.resources = self.enterContext(ExitStack())
        self.log = self.enterContext(TemporaryFile())
        self.env = {"IFW_QA_ISOLATED": "1", "IFW_QA_INVENTORY_TOKEN": TOKEN, "Path": r"C:\Ä",
                    "=C:": str(CWD), "Unicode": "Grüße 🖼"}
        self.api = Mock()
        self.resources.enter_context(patch.object(subject, "Kernel", return_value=self.api))
        self.resources.enter_context(patch.dict(sys.modules, msvcrt=SimpleNamespace(get_osfhandle=lambda fd: fd)))
        self.resources.enter_context(patch.object(c, "get_last_error", return_value=122, create=True))
        self.resources.enter_context(patch.object(os, "O_BINARY", 0, create=True))
        self.api.initialize.side_effect = self.initialize
        self.api.compare.side_effect = lambda a, _na, b, _nb, ignore: 2 + (a.upper() > b.upper()) - (a.upper() < b.upper())
        self.api.update.side_effect = self.update
        self.api.create.side_effect = self.create
        self.api.resume.return_value = 1
        self.api.wait.side_effect = lambda _handle, _ms: subject.WAIT_TIMEOUT if self.status is None else 0
        self.api.terminate.side_effect = self.terminate
        self.api.exit_code.side_effect = self.exit_code
        self.status = None

    @staticmethod
    def initialize(attributes, count, flags, capacity):
        if (count, flags) != (1, 0):
            raise AssertionError("Expected one attribute")
        if attributes is None:
            capacity._obj.value = 128
            return False
        return c.sizeof(attributes) == capacity._obj.value

    def update(self, attributes, flags, key, handles, size, previous, returned):
        self.assertEqual((flags, key, size, previous, returned), (0, 0x20002, 2 * c.sizeof(c.c_void_p), None, None))
        self.attributes = c.addressof(attributes)
        self.handles = tuple(handles)
        self.assertEqual(len(set(self.handles)), 2)
        self.assertTrue(all(os.get_inheritable(fd) for fd in self.handles))
        return True

    def create(self, exe, command, process_security, thread_security, inherit, flags, env, cwd, startup, result):
        self.assertEqual((exe, cwd, process_security, thread_security, inherit), (str(IMAGE), str(CWD), None, None, True))
        extended = startup._obj
        info = extended.startup
        self.assertEqual((info.size, info.flags, extended.attributes), (112, 0x100, self.attributes))
        self.assertEqual((info.stdin, info.stdout, info.stderr), (*self.handles, self.handles[1]))
        self.assertNotIn(self.log.fileno(), self.handles)
        self.command, self.desktop, self.flags = command.value, info.desktop, flags
        self.block = bytes(env).decode("utf-16-le")
        # The child retains its own inherited descriptors after the parent discards the temporary duplicates.
        self.reader = self.resources.enter_context(os.fdopen(os.dup(info.stdin), "rb", buffering=0))
        self.writer = self.resources.enter_context(os.fdopen(os.dup(info.stdout), "wb", buffering=0))
        result._obj.process, result._obj.thread, result._obj.pid, result._obj.tid = 900, 901, 902, 903
        return True

    def terminate(self, handle, code):
        self.assertEqual(handle, 900)
        self.status = code
        return True

    def exit_code(self, handle, output):
        self.assertEqual(handle, 900)
        output._obj.value = self.status
        return True

    def start(self, desktop="Default", arguments=(), primary=True):
        return subject.start(IMAGE, arguments, cwd=CWD, env=self.env, stream=self.log, desktop=desktop, primary=primary)

    def test_private_named_primary_has_only_its_input_and_log_and_retains_original_thread(self):
        name = "IfwQa_Launcher_" + TOKEN
        proc = self.start(name, ["--autostart"])
        self.addCleanup(proc.close)
        self.assertEqual(self.desktop, "WinSta0\\" + name)
        self.assertEqual(self.command, f'"{IMAGE}" --autostart')
        self.assertEqual(self.flags, 0x08080404)
        self.assertEqual(self.block, "\0".join(f"{k}={self.env[k]}" for k in sorted(self.env, key=str.upper)) + "\0\0")
        self.assertEqual((proc.pid, proc.thread_id, proc._handle), (902, 903, 900))
        self.assertFalse(os.get_inheritable(proc.stdin.fileno()))
        self.assertFalse(os.get_inheritable(self.log.fileno()))
        for fd in self.handles:
            with self.assertRaises(OSError):
                os.fstat(fd)
        proc.stdin.write(b"B")
        self.assertEqual(self.reader.read(1), b"B")
        self.writer.write(b"ready")
        self.log.seek(0)
        self.assertEqual(self.log.read(), b"ready")
        self.api.resume.assert_not_called()
        proc.resume()
        self.api.resume.assert_called_once_with(901)
        with self.assertRaises(ValueError):
            proc.resume()
        with self.assertRaises(subprocess.TimeoutExpired):
            proc.wait(timeout=.0001)
        self.api.wait.assert_called_once_with(900, 1)
        self.status = 259  # A signaled process can actually exit with STILL_ACTIVE as its code.
        self.assertEqual(proc.poll(), 259)
        proc.close()
        self.assertTrue(proc.stdin.closed)
        self.assertIsNone(proc._handle)
        self.assertEqual(self.api.close.call_args_list, [call(901), call(900)])
        self.api.terminate.assert_not_called()

    def test_detached_secondary_has_no_arguments_no_command_pipe_and_immediate_standard_input_eof(self):
        proc = self.start(primary=False)
        self.addCleanup(proc.close)
        self.assertEqual((self.command, self.desktop, self.flags), (f'"{IMAGE}"', r"WinSta0\Default", 0x0008040C))
        self.assertIsNone(proc.stdin)
        self.assertEqual(self.reader.read(1), b"")
        self.assertIsNone(proc.poll())
        proc.close()
        self.api.terminate.assert_called_once_with(900, 1)
        self.api.wait.assert_any_call(900, 8000)
        self.assertEqual(proc.returncode, 1)

    def test_only_original_fixture_names_or_default_are_accepted(self):
        for desktop in ("WinSta0\\Default", "Winlogon", "IfwQa_Tray_" + "a" * 32):
            with self.subTest(desktop=desktop), self.assertRaises(ValueError):
                self.start(desktop)
        with self.assertRaises(ValueError):
            self.start(arguments=["--autostart"], primary=False)
        self.api.create.assert_not_called()
        proc = self.start("IfwQa_Tray_" + TOKEN)
        proc.close()

    def test_rejects_ambiguous_environments_before_process_creation(self):
        for addition in ({"pATH": "duplicate"}, {"bad=key": "value"}, {"x": "part\0two"}):
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                subject.environment_block(self.api, {**self.env, **addition})
        self.api.create.assert_not_called()

    def test_failure_after_creation_reaps_the_still_suspended_child_and_closes_both_handles(self):
        self.api.delete.side_effect = OSError("attribute cleanup")
        with self.assertRaisesRegex(OSError, "attribute cleanup"):
            self.start()
        self.api.resume.assert_not_called()
        self.api.terminate.assert_called_once_with(900, 1)
        self.assertEqual(self.api.close.call_args_list, [call(901), call(900)])

    def test_failed_creation_does_not_treat_unspecified_output_handles_as_a_process(self):
        def failed(*args):
            args[-1]._obj.process = 1000
            return False
        self.api.create.side_effect = failed
        with self.assertRaisesRegex(OSError, "CreateProcessW"):
            self.start()
        self.api.delete.assert_called_once()
        self.api.terminate.assert_not_called()
        self.api.close.assert_not_called()

    def test_unreaped_child_gates_further_trials_and_attempts_both_handle_releases(self):
        proc = self.start()
        self.api.wait.side_effect = None
        self.api.wait.return_value = subject.WAIT_TIMEOUT
        with self.assertRaises(subject.CleanupUnconfirmed) as raised:
            proc.close()
        self.assertIsInstance(raised.exception.__cause__, subprocess.TimeoutExpired)
        self.assertTrue(proc.stdin.closed)
        self.assertEqual(self.api.close.call_args_list, [call(901), call(900)])


if __name__ == "__main__":
    unittest.main()
