"""Exercise bounded process-group cleanup with actual synthetic child processes."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from second_launch import reap_secondary


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux child subreaper and waitid required")
class SecondaryCleanupTests(unittest.TestCase):
    def test_reaps_the_departed_launchers_worker_and_leaves_other_children_waitable(self):
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)  # PR_GET_CHILD_SUBREAPER
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        self.addCleanup(libc.prctl, 36, previous.value, 0, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pid"
            script = ("import os, pathlib, signal, sys\n"
                      "pid = os.fork()\n"
                      "if pid == 0: signal.pause()\n"
                      "else: pathlib.Path(sys.argv[1]).write_text(str(pid))\n")
            with (subprocess.Popen([sys.executable, "-c", script, output], start_new_session=True) as launcher,
                  subprocess.Popen([sys.executable, "-c", "pass"]) as unrelated):
                try:
                    deadline = time.monotonic() + 3
                    while os.waitid(os.P_PID, launcher.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.01)
                finally:
                    record = {}
                    reap_secondary(launcher, record)
                self.assertEqual(record["exit"], 0)
                self.assertEqual(record["reapedDescendants"], [{"pid": int(output.read_text()), "exit": -signal.SIGKILL}])
                self.assertEqual(unrelated.wait(timeout=3), 0)


if __name__ == "__main__":
    unittest.main()
