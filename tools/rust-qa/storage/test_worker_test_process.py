"""Observe the lifetime of synthetic test launchers without starting .NET."""

import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import worker_test_process as owner


class TestWorkerProcess(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.log = (self.root / "worker.log").open("w+b")
        self.addCleanup(self.log.close)
        self.options = dict(cwd=self.root, env=os.environ.copy(), log=self.log)

    def test_normal_launcher_waits_for_testhost_and_propagates_original_status(self):
        args = [sys.executable, "-c", "import subprocess,sys; "
                "subprocess.run([sys.executable,'-c','print(17)'],check=True); sys.exit(7)"]
        with owner.test_process(args, **self.options) as process:
            self.assertEqual(process.wait(timeout=10), 7)
            self.assertEqual(process.poll(), 7)
        self.assertEqual(process.wait(timeout=0), 7)
        self.log.seek(0)
        self.assertEqual(self.log.read().strip(), b"17")

    def test_waited_launcher_allows_its_remaining_testhost_to_finish(self):
        child = ("from pathlib import Path\nimport time\n"
                 "while not Path('release').exists(): time.sleep(.01)\n"
                 "time.sleep(.1)\nPath('finished').touch()")
        args = [sys.executable, "-c", "import subprocess,sys; subprocess.Popen([sys.executable,'-c',sys.argv[1]])", child]
        with owner.test_process(args, **self.options) as process:
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertFalse((self.root / "finished").exists())
            (self.root / "release").touch()
        self.assertTrue((self.root / "finished").is_file())

    @unittest.skipUnless(sys.platform == "linux", "requires Linux sessions and pidfds")
    def test_waited_leader_keeps_an_orphaned_child_bound_to_its_own_session(self):
        args = [sys.executable, "-c",
                "from pathlib import Path; import subprocess,sys; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(15)'],process_group=0); "
                "Path('child.pid').write_text(str(p.pid))"]
        outsider = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"], start_new_session=True)
        try:
            with patch.object(owner, "DRAIN_SECONDS", .05), self.assertRaisesRegex(RuntimeError, "forced cleanup"):
                with owner.test_process(args, **self.options) as process:
                    self.assertEqual(process.wait(timeout=5), 0)
                    child = int((self.root / "child.pid").read_text())
                    self.assertEqual(os.getsid(child), process.pid)
                    self.assertEqual(os.getpgid(child), child)
                    observer = os.pidfd_open(child)
                    self.addCleanup(os.close, observer)
                    event = select.poll()
                    event.register(observer, select.POLLIN)
                    self.assertFalse(event.poll(0))
            self.assertTrue(event.poll(1000), "the original child retained a live pidfd")
            self.assertIsNone(outsider.poll())
            with self.assertRaises(ChildProcessError):
                os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        finally:
            outsider.terminate()
            outsider.wait(timeout=5)

    def test_timeout_preserves_primary_error_and_reaps_the_launcher(self):
        args = [sys.executable, "-c", "import time; time.sleep(15)"]
        with patch.object(owner, "DRAIN_SECONDS", .05), self.assertRaises(subprocess.TimeoutExpired) as error:
            with owner.test_process(args, **self.options) as process:
                process.wait(timeout=.15)
        self.assertIsNotNone(process.returncode)
        self.assertTrue(any("forced cleanup" in note for note in error.exception.__notes__))

    def test_windows_assignment_failure_reaps_suspended_process_and_closes_job(self):
        api, process = Mock(), Mock()
        api.assign_suspended.side_effect = OSError("fixture assignment refused")
        api.wait_job_empty.return_value = True
        options = dict(env=self.options["env"], cwd=self.root, stdout=self.log)
        with (patch.object(owner, "_windows_api", return_value=(api, lambda status: status)),
              patch.object(subprocess, "Popen", return_value=process) as launch,
              self.assertRaisesRegex(OSError, "fixture assignment refused")):
            with owner._windows_process([sys.executable, "arg"], options):
                self.fail("an unassigned process executed")
        self.assertEqual(launch.call_args.kwargs["creationflags"], 4)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once()
        api.resume_owned_process.assert_not_called()
        api.terminate_job.assert_not_called()
        api.close.assert_called_once_with(api.new_job.return_value)

    def test_windows_resumes_after_assignment_and_preserves_exchange_error(self):
        api, process = Mock(), Mock()
        api.wait_job_empty.side_effect = [False, True]
        options = dict(env=self.options["env"], cwd=self.root, stdout=self.log)
        with (patch.object(owner, "_windows_api", return_value=(api, lambda status: status)),
              patch.object(subprocess, "Popen", return_value=process),
              self.assertRaisesRegex(ValueError, "exchange failed") as error):
            with owner._windows_process([sys.executable, "arg"], options):
                self.assertEqual([name for name, _, _ in api.mock_calls][:3],
                                 ["new_job", "assign_suspended", "resume_owned_process"])
                raise ValueError("exchange failed")
        self.assertTrue(any("forced cleanup" in note for note in error.exception.__notes__))
        api.terminate_job.assert_called_once_with(api.new_job.return_value, 1)
        api.close.assert_called_once_with(api.new_job.return_value)


if __name__ == "__main__":
    unittest.main()
