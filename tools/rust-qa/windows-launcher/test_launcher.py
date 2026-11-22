"""Exercise the ordinary secondary invocation and the evidence required to attribute its window."""
import ctypes as c
from pathlib import Path, PureWindowsPath
import subprocess
import unittest
from unittest.mock import Mock, patch

import observe


GUI = PureWindowsPath(r"C:\fixture\subject\native-gui-assessment.exe")
WORKER = GUI.with_name("ifw-performance-worker.exe")
CONSOLE = PureWindowsPath(r"C:\Windows\System32\conhost.exe")


class PrimaryJobTests(unittest.TestCase):
    def observe_members(self, members, *, outside_job=()):
        # IDs 12 and 13 represent the original GUI and worker handles retained by the fixture.
        api, desk = Mock(), Mock()
        def query(job, info, buffer, size, returned):
            self.assertEqual((job, info, size), (100, 3, c.sizeof(observe.JobProcessIds)))
            listing = buffer._obj
            listing.assigned = listing.listed = len(members)
            listing.ids[:len(members)] = sorted(members)
            return True
        def belongs(pid, job, result):
            result._obj.value = pid not in outside_job
            return True
        def running(pid, result):
            result._obj.value = 259
            return True
        def image(pid, flags, output, size):
            output.value = str(members[pid][1])
            return True
        api.query_job.side_effect = query
        api.in_job.side_effect = belongs
        api.exit_code.side_effect = running
        api.open.side_effect = lambda access, inherit, pid: pid
        api.process_identity.side_effect = lambda pid: pid * 100
        api.processes.return_value = {pid: (parent, path.name) for pid, (parent, path) in members.items()}
        api.processes.return_value[99] = (12, "unrelated.exe")
        desk.image.side_effect = image
        self.report = {}
        try:
            return observe.primary_job_members(api, desk, 100, 12, 13, GUI, CONSOLE, self.report)
        finally:
            for call in api.open.call_args_list:
                self.assertEqual(call.args[:2], (0x1000, False))
                self.assertIn(call.args[2], members)
            self.assertEqual(api.close.call_count, api.open.call_count)

    def test_primary_and_worker_identified_with_and_without_the_native_console_host(self):
        original = {12: (5, GUI), 13: (12, WORKER)}
        for helpers in ({}, {14: (13, CONSOLE)}, {14: (13, CONSOLE), 15: (12, CONSOLE)}):
            with self.subTest(helpers=helpers):
                self.assertEqual(self.observe_members(original | helpers), [13, 1300])
                self.assertEqual([row["role"] for row in self.report["members"]],
                                 ["primary", "worker"] + ["systemConsoleHost"] * len(helpers))
                self.assertEqual(self.report["pids"], sorted(original | helpers))

    def test_primary_rejects_extra_applications_and_unverified_helpers(self):
        original = {12: (5, GUI), 13: (12, WORKER)}
        for changes in ({14: (13, WORKER)}, {14: (12, GUI)}, {14: (13, GUI.with_name("conhost.exe"))},
                        {14: (5, CONSOLE)}, {14: (13, CONSOLE), 15: (13, CONSOLE)},
                        {13: (5, WORKER)}, {13: (12, GUI)}, {12: (5, WORKER)}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Unexpected executable or parent"):
                self.observe_members(original | changes)
            self.assertEqual(self.report["pids"], sorted(original | changes))
        with self.assertRaisesRegex(ValueError, "both original application processes"):
            self.observe_members({12: (5, GUI)})
        with self.assertRaisesRegex(ValueError, "no longer belongs"):
            self.observe_members(original | {14: (13, CONSOLE)}, outside_job=(14,))
        self.assertEqual([row["pid"] for row in self.report["members"]], [12, 13])


class LauncherTests(unittest.TestCase):
    def test_secondary_runs_the_same_image_without_arguments_or_input_pipe(self):
        api, desk = Mock(), Mock()
        desk.name.return_value = "IfwQa_test"
        desk.receiving_input.return_value = False
        image = Path("native-gui-assessment.exe")
        with (patch.object(subprocess, "STARTUPINFO", create=True),
              patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True),
              patch.object(subprocess, "Popen") as launch):
            launch.return_value.stdin = None
            with observe.child(api, desk, "IfwQa_test", image, [], Path("case"), {}, None, False):
                pass
        self.assertEqual(launch.call_args.args, ([image],))
        self.assertNotIn("stdin", launch.call_args.kwargs)
        api.assign_suspended.assert_called_once_with(api.new_job.return_value, launch.return_value, image)

    def test_receipt_requires_the_original_primary_and_its_worker(self):
        secondary = ["LAUNCHER_SECONDARY server=12"]
        primary = ["LAUNCHER_OPEN client=15"]
        receipt = dict(primaryPid=12, secondaryPid=15, initialWindowPid=12, reopenedWindowPid=12,
                       hiddenBeforeLaunch=True, workerBefore=[13, 1234], workerAfter=[13, 1234],
                       secondaryExit=0, secondaryJobEmpty=True, secondaryTotalProcesses=1)
        observe.qualify(secondary, primary, receipt)
        for key, value in (("hiddenBeforeLaunch", False), ("reopenedWindowPid", 15),
                           ("workerAfter", [13, 4321]), ("secondaryTotalProcesses", 2)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.qualify(secondary, primary, dict(receipt, **{key: value}))
        for wrong_secondary, wrong_primary in [
            (["READY Visible Unavailable"], primary), (secondary, []),
            (secondary, ["LAUNCHER_OPEN"]), (secondary, primary * 2),
        ]:
            with self.assertRaises(ValueError):
                observe.qualify(wrong_secondary, wrong_primary, receipt)


if __name__ == "__main__":
    unittest.main()
