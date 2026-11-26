"""Check the Windows recorder's job, grant and controller lifetime contracts."""
from contextlib import ExitStack, contextmanager
import ctypes as c
import hashlib
import io
from itertools import count
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

import native
from run import SubjectTree, await_value, idle_complete, pin_images, wpf_second_launch


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
        self.assertEqual(got.benchmark_job, 123)
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

    def test_native_handle_validation_rejects_a_different_pid_or_job(self):
        api = object.__new__(native.Win32)
        def membership(handle, job, member):
            member._obj.value = job == 123
            return 1
        api.in_job = membership
        api.process_id = lambda _: 456
        api.open, api.close = Mock(return_value=400), Mock(return_value=1)
        self.assertEqual(api.open_job_member(123, 456), 400)
        api.open.assert_called_once_with(0x1000, False, 456)
        for job, pid in ((789, 456), (123, 999)):
            with self.assertRaisesRegex(ValueError, "does not identify trial job member"):
                api.open_job_member(job, pid)
        self.assertEqual(api.close.call_count, 2)

    def test_job_process_list_resizes_and_rejects_incomplete_or_invalid_results(self):
        api = object.__new__(native.Win32)
        members = list(range(1, 21))
        def query(job, info, buffer, size, returned):
            self.assertEqual((job, info), (123, 3))
            if size < 8 + len(members) * c.sizeof(c.c_size_t):
                return 0
            header = (c.c_uint32 * 2).from_buffer(buffer)
            header[:] = (len(members), len(members))
            (c.c_size_t * len(members)).from_buffer(buffer, 8)[:] = members
            returned._obj.value = 8 + len(members) * c.sizeof(c.c_size_t)
            return 1
        api.query_job = Mock(side_effect=query)
        with patch.object(c, "get_last_error", return_value=234, create=True):
            self.assertEqual(api.job_pids(123), set(members))
            self.assertEqual(api.query_job.call_count, 2)
            members[:] = [4, 4]
            with self.assertRaisesRegex(ValueError, "Invalid process identifier"):
                api.job_pids(123)
            api.query_job.side_effect = lambda *args: 0
            with self.assertRaisesRegex(ValueError, "complete process list"):
                api.job_pids(123)


class FixtureTests(unittest.TestCase):
    def wpf_launch(self, windows_seen, foreground, show_tick=3):
        api, windows, primary, secondary = (Mock() for _ in range(4))
        primary.pid, secondary.pid = 41, 42
        primary.poll.return_value = secondary.poll.return_value = None
        secondary.wait.return_value = 0
        windows.visible.side_effect = windows_seen
        windows.events = []
        windows.pump.side_effect = lambda: windows.events.append(
            {"event": "show", "root": True, "hwnd": 100, "winEventTimeMs": show_tick})
        uptime = Mock(side_effect=[(1 << 32) - 4, (1 << 32) - 2, (1 << 32) + 50])
        values = {}
        with (patch.object(c, "WinDLL", create=True), patch("run.bind", side_effect=[lambda: foreground, uptime]),
              patch("run.start_owned_subject", return_value=secondary),
              patch("run.time.monotonic", side_effect=count()), patch("run.time.sleep")):
            wpf_second_launch(api, windows, primary, Path("ImmichFolderWatch.exe"), Path("private"), {}, 7, values)
        return api, values

    def test_wpf_observer_accepts_original_window_remaining_in_background(self):
        api, result = self.wpf_launch([100, None, None, 100, 100, 100], 500)
        api.resume_owned_process.assert_called_once_with(42)
        self.assertTrue(result["sameWindow"])
        self.assertFalse(result["foregroundObserved"])
        self.assertEqual("observed", result["status"])

    def test_wpf_show_on_the_resume_tick_cannot_be_attributed_to_the_secondary(self):
        _, result = self.wpf_launch([100, None, None, 100, 100], 100, (1 << 32) - 2)
        self.assertTrue(result["foregroundObserved"])
        self.assertEqual("show-order-inconclusive", result["status"])

    def test_wpf_observer_rejects_reopen_before_resume_or_a_changed_window(self):
        with self.assertRaisesRegex(ValueError, "must remain hidden"):
            self.wpf_launch([100, None, 100], 100)
        with self.assertRaisesRegex(ValueError, "different window"):
            self.wpf_launch([100, None, None, 101], 100)

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
        empty.assert_called_once_with(api, Path("a/fixture"), directory_waits=None)
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
    def test_native_directory_disposition_retries_the_same_handle_after_a_real_nonempty_result(self):
        api, waits, attempts, errors = native.Win32(), [], [], []
        delete = api.delete_handle
        directory_id = None
        parent = Path(os.environ["RUNNER_TEMP"])

        def inject_late_child(handle):
            if api.file_info(handle)[1] == directory_id:
                attempts.append(handle)
                if len(attempts) == 1:
                    # The creator holds its own CREATE_NEW file through the first directory disposition.
                    child = api.create_file(str(nested / "late-owned"), 0x10080, 7, None, 1, 0x00200080, None)
                    if child == c.c_void_p(-1).value:
                        raise c.WinError(c.get_last_error())
                    try:
                        return delete(handle)
                    except OSError as exc:
                        errors.append(exc.winerror)
                        raise
                    finally:
                        try:
                            delete(child)
                        finally:
                            native.checked(api.close(child))
            return delete(handle)

        with (patch.object(api, "delete_handle", side_effect=inject_late_child),
              native.owned_directory(api, parent, "ifw-rw02-" + uuid.uuid4().hex, directory_waits=waits) as area):
            nested = area / "subject"
            nested.mkdir()
            with native.pin_path(api, nested, True) as (_, identity):
                directory_id = identity
        self.assertEqual(errors, [145])
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(len(set(attempts)), 1)
        self.assertEqual([(r["relativeDirectory"], r["volume"], r["fileId"], r["initialWin32Error"],
                           r["dispositionAccepted"]) for r in waits], [("subject", *directory_id, 145, True)])
        self.assertFalse(os.path.lexists(area))

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

    @unittest.skipUnless(native.hosted(), "requires a disposable native GitHub Windows runner")
    def test_native_job_keeps_departed_child_cpu_and_measures_only_live_working_sets(self):
        api = native.Win32()
        parent = Path(os.environ["RUNNER_TEMP"])
        with native.owned_directory(api, parent, "ifw-rw02-" + uuid.uuid4().hex) as area:
            bootstrap = ("import os, sys, subprocess, time\nfrom pathlib import Path\n"
                         "def wait_marker(name):\n"
                         "    deadline = time.monotonic() + 20\n"
                         "    while not Path(name).exists():\n"
                         "        if time.monotonic() > deadline: raise TimeoutError(name)\n"
                         "        time.sleep(.01)\n")
            child = (bootstrap + "Path('child-ready').touch()\nwait_marker('release-child')\n"
                     "start = time.process_time()\nwhile time.process_time() - start < .25: pass\n"
                     "sys.exit(259)\n")
            program = (bootstrap + f"child = subprocess.Popen([sys.executable, '-I', '-S', '-c', {child!r}])\n"
                       "assert child.wait(timeout=25) == 259\n"
                       "Path('child-exited').touch()\nwait_marker('release-gui')\n")
            with ExitStack() as stack:
                stream = stack.enter_context((area / "trial.log").open("wb"))
                env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
                env.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1")
                proc = native.start_owned_subject(stack, api, Path(sys.executable), area, env, stream, True,
                                                  lambda proc, rust: proc.wait(timeout=10))
                api.resume_owned_process(proc.pid)
                proc.stdin.write(program.encode("ascii"))
                proc.stdin.close()
                # These are released even if a measurement raises, before teardown awaits the subject.
                stack.callback((area / "release-gui").touch)
                stack.callback((area / "release-child").touch)
                await_value((area / "child-ready").is_file, "Child did not start", timeout=10)
                tree = SubjectTree(api, stack, proc.benchmark_job, {proc.pid: int(proc._handle)})
                cpu, _ = tree.usage()
                initial = tree.samples[-1]
                self.assertEqual(len(initial["workingSetBytes"]), 2)
                self.assertTrue(all(n > 0 for n in initial["workingSetBytes"].values()))
                (area / "release-child").touch()
                await_value((area / "child-exited").is_file, "Child did not exit", timeout=10)
                final_cpu, _ = tree.usage()
                final = tree.samples[-1]
                self.assertEqual(set(final["workingSetBytes"]), {proc.pid})
                self.assertEqual(initial["totalProcesses"], final["totalProcesses"])
                self.assertGreaterEqual(final_cpu - cpu, .24)
            self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
