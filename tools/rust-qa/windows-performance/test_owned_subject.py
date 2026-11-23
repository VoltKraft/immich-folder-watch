"""Check the Windows recorder's job, grant and controller lifetime contracts."""
from contextlib import ExitStack, contextmanager
import ctypes as c
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

import native
from run import idle_complete, pin_images


class JobTests(unittest.TestCase):
    def setUp(self):
        self.api, self.proc = Mock(), Mock()
        self.api.new_job.return_value = 123
        self.api.clock.return_value = 42
        self.proc.pid = 456
        self.proc.stdin = io.BytesIO()
        self.stop = Mock()

    def launch(self, stack):
        with patch.object(subprocess, "Popen", return_value=self.proc) as spawn:
            got = native.start_owned_subject(stack, self.api, Path("gui.exe"), Path("private"), {}, 7, True, self.stop)
        self.assertEqual(spawn.call_args.kwargs["creationflags"], 4)
        self.assertIs(got, self.proc)
        self.assertEqual(got.benchmark_start_qpc, 42)
        self.api.assign_suspended.assert_called_once_with(123, self.proc, Path("gui.exe"))
        self.api.resume_owned_process.assert_not_called()

    def test_exit_requires_empty_job_before_closing_it(self):
        with ExitStack() as stack:
            self.launch(stack)
        self.stop.assert_called_once_with(self.proc, True)
        self.api.wait_job_empty.assert_called_once_with(123, 1)
        self.api.close.assert_called_once_with(123)
        self.api.terminate_job.assert_not_called()

    def test_failure_before_assignment_reaps_only_the_suspended_subject(self):
        self.api.assign_suspended.side_effect = OSError("assignment refused")
        with self.assertRaisesRegex(OSError, "assignment refused"), ExitStack() as stack:
            self.launch(stack)
        self.proc.kill.assert_called_once_with()
        self.proc.wait.assert_called_once_with(timeout=10)
        self.api.wait_job_empty.assert_called_once_with(123, 5)
        self.api.close.assert_called_once_with(123)
        self.assertTrue(self.proc.stdin.closed)
        self.stop.assert_not_called()

    def test_escaped_grace_interval_fails_the_trial_after_reaping_descendants(self):
        self.api.wait_job_empty.side_effect = [False, True]
        with self.assertRaisesRegex(RuntimeError, "forced descendant cleanup"), ExitStack() as stack:
            self.launch(stack)
        self.api.terminate_job.assert_called_once_with(123, 1)
        self.proc.wait.assert_called_once_with(timeout=5)
        self.api.close.assert_called_once_with(123)

    def test_missing_terminal_accounting_blocks_any_further_trial_and_profile_removal(self):
        self.api.wait_job_empty.return_value = False
        with self.assertRaises(native.CleanupUnconfirmed), ExitStack() as stack:
            self.launch(stack)
        self.api.close.assert_called_once_with(123)

    def test_x64_and_arm64_structure_layouts(self):
        self.assertEqual([c.sizeof(s) for s in (native.JobLimits, native.JobAccounting, native.FileInformation,
                                                native.UnicodeString, native.ObjectAttributes)], [144, 48, 52, 16, 48])
        self.assertEqual(native.JobAccounting.active.offset, 40)
        self.assertEqual(native.JobLimits.io_counters.offset, 64)


class FixtureTests(unittest.TestCase):
    def test_idle_requires_the_two_original_complete_lines(self):
        first = "INVENTORY_COMPLETE files=0 changed=0 pass=0\n"
        second = "INVENTORY_COMPLETE files=0 changed=0 pass=1"
        self.assertFalse(idle_complete(first + second))
        self.assertTrue(idle_complete(first + "READY\n" + second + "\r\n"))
        for wrong in (first + second + "0\n", second + "\n", first * 2 + second + "\n",
                      first + second.replace("changed=0", "changed=2") + "\n"):
            with self.assertRaises(ValueError):
                idle_complete(wrong)

    def test_missing_controller_is_reaped_and_only_its_trace_identity_is_requested(self):
        helper = Mock()
        helper.stdin = io.BytesIO()
        helper.wait.side_effect = [subprocess.TimeoutExpired("trace", 1), 1]
        helper.poll.return_value = 1
        area = Path("private")
        etl, name = area / "subject.etl", "IFW-RW02-" + uuid.uuid4().hex
        with patch.object(subprocess, "run") as check, self.assertRaises(subprocess.TimeoutExpired):
            native.finish_owned_trace(helper, "observer.exe", area, etl, name, 1)
        helper.kill.assert_called_once_with()
        check.assert_called_once_with(["observer.exe", "--stop-owned", etl, name], cwd=area,
                                      stdin=subprocess.DEVNULL, check=True, timeout=15)

    def test_unconfirmed_controller_cleanup_blocks_profile_removal(self):
        helper = Mock()
        helper.stdin = io.BytesIO()
        with (patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(3, "stop")),
              self.assertRaises(native.CleanupUnconfirmed)):
            native.finish_owned_trace(helper, "observer.exe", Path("a"), Path("a/subject.etl"), "owned", 1)

    def test_cleanup_uses_the_first_directory_identity_and_refuses_a_replacement(self):
        api = Mock()
        api.create_child_directory.return_value = 111
        api.path_handle.return_value = 222
        api.file_info.side_effect = [(0x10, (1, 1)), (0x10, (1, 2))]
        with patch.object(native, "pin_path") as pinned, patch.object(native, "remove_owned_contents") as empty:
            pinned.return_value.__enter__.return_value = (99, (1, 99))
            with self.assertRaisesRegex(ValueError, "identity changed"), native.owned_directory(api, Path("a"), "fixture"):
                pass
        empty.assert_called_once_with(api, Path("a/fixture"))
        api.delete_handle.assert_not_called()

    def test_unknown_job_state_preserves_the_marked_directory(self):
        api = Mock()
        api.file_info.return_value = (0x10, (1, 1))
        with patch.object(native, "pin_path") as pinned, patch.object(native, "remove_owned_contents") as empty:
            pinned.return_value.__enter__.return_value = (99, (1, 99))
            with self.assertRaises(native.CleanupUnconfirmed), native.owned_directory(api, Path("a"), "fixture"):
                try:
                    raise native.CleanupUnconfirmed("no readback")
                finally:
                    raise RuntimeError("another ExitStack callback reported an error")
        empty.assert_not_called()
        api.delete_handle.assert_not_called()

    def test_marker_creation_failure_is_inside_profile_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            scopes = []
            @contextmanager
            def tracked(api, parent, name):
                scopes.append(name)
                try:
                    yield parent / name
                finally:
                    scopes.append("cleaned")
            with (patch.object(native, "hosted", return_value=True), patch.object(native, "known_folder", return_value=path),
                  patch.object(native, "Win32"), patch.object(native, "owned_directory", tracked),
                  patch.object(native, "pin_new_marker", side_effect=OSError("marker failed"))):
                with self.assertRaisesRegex(OSError, "marker failed"), native.wpf_profile(path, "http://127.0.0.1:9"):
                    self.fail("unexpected yield")
            self.assertEqual(scopes, ["Immich Folder Watch", "cleaned"])

    def test_original_marker_handle_is_held_until_the_deny_write_reader_matches(self):
        api = Mock()
        api.create_file.return_value = 1
        api.path_handle.side_effect = [2, 3]
        api.file_info.return_value = (0x80, (1, 101))
        token = uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as temp, ExitStack() as pins:
            marker = Path(temp) / "inventory.owner"
            def write(handle, data, size, written, unused):
                self.assertEqual(handle, 1)
                marker.write_bytes(data)
                written._obj.value = size
                return True
            api.write.side_effect = write
            self.assertEqual(native.pin_new_marker(pins, api, marker, token), (1, 101))
            self.assertEqual([call.args[0] for call in api.close.call_args_list], [1, 2])
            pins.close()
            self.assertEqual([call.args[0] for call in api.close.call_args_list], [1, 2, 3])

    def test_worker_must_match_the_original_build_receipt_while_pinned(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            stage, reference = path / "subject", path / "reference"
            stage.mkdir()
            reference.mkdir()
            gui, worker, wpf = stage / "gui.exe", stage / "ifw-performance-worker.exe", reference / "wpf.exe"
            for image in (gui, worker, wpf):
                image.write_bytes(b"")
            sha = hashlib.sha256(b"").hexdigest()
            facts = dict(guiBinarySha256=sha, inventory={"worker": sha}, wpfOutput={wpf.name: sha})
            @contextmanager
            def pinned(api, item, directory):
                self.assertEqual(directory, item.is_dir())
                yield 99, (1, 2)
            with patch("run.pin_path", pinned), ExitStack() as stack:
                records = pin_images(stack, None, path, wpf, gui, None, None, facts)
                self.assertIn("subject/ifw-performance-worker.exe", records)
                worker.write_bytes(b"other")
                with self.assertRaisesRegex(ValueError, "build receipt"):
                    pin_images(stack, None, path, wpf, gui, None, None, facts)

    @unittest.skipUnless(native.hosted(), "requires a disposable native GitHub Windows runner")
    def test_native_job_and_handle_based_fixture_lifecycle(self):
        api = native.Win32()
        parent = Path(os.environ["RUNNER_TEMP"])
        with native.owned_directory(api, parent, "ifw-rw02-" + uuid.uuid4().hex) as area:
            nested = area / "nested"
            nested.mkdir()
            sample = nested / "sample"
            sample.write_text("owned", encoding="ascii")
            with ExitStack() as pins:
                token = uuid.uuid4().hex
                marker = area / "inventory.owner"
                native.pin_new_marker(pins, api, marker, token)
                self.assertEqual(marker.read_text(), token)
                with self.assertRaises(PermissionError):
                    marker.write_text("replacement")
            with native.pin_path(api, sample, False):
                with self.assertRaises(PermissionError):
                    sample.rename(nested / "newname")
                with self.assertRaises(PermissionError) as busy:
                    native.remove_owned_contents(api, nested)
                self.assertEqual(busy.exception.winerror, 32)
                self.assertEqual(busy.exception.__notes__,
                                 ["CreateFileW(DELETE | FILE_READ_ATTRIBUTES) on owned fixture entry 'sample'"])
                self.assertEqual(sample.read_text(encoding="ascii"), "owned")
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
            env.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1")
            cleanup = lambda proc, rust: proc.wait(timeout=5)
            with ExitStack() as stack:
                stream = stack.enter_context((area / "exit.log").open("wb"))
                proc = native.start_owned_subject(stack, api, Path(sys.executable), area, env, stream, True, cleanup)
                api.resume_owned_process(proc.pid)
                proc.stdin.write(b"print('OWNED_SUBJECT_EXIT')\n")
                proc.stdin.close()
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((area / "exit.log").read_text().strip(), "OWNED_SUBJECT_EXIT")
        self.assertFalse(area.exists())


if __name__ == "__main__":
    unittest.main()
