"""Exercise the ordinary secondary invocation and the evidence required to attribute its window."""
from contextlib import contextmanager
import ctypes as c
import json
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
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
    def test_passive_focus_observation_counts_only_the_same_still_visible_window(self):
        desk, windows = Mock(), Mock()
        hwnd = 27
        for surfaces, foregrounds, expected in (([hwnd, hwnd], [23, hwnd], True), ([99], [], False)):
            clock = [0.0]
            windows.visible.side_effect = surfaces
            desk.foreground.side_effect = foregrounds
            with (patch.object(observe.time, "monotonic", side_effect=lambda: clock[0]),
                  patch.object(observe.time, "sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration))):
                row = observe.passive_foreground(desk, windows, hwnd, False)
            self.assertFalse(row["initial"])
            self.assertEqual((row["observed"], row["sameWindowVisible"]), (expected, expected))

    def test_secondary_runs_the_same_image_without_arguments_or_input_pipe(self):
        api, desk = Mock(), Mock()
        desk.name.side_effect = lambda handle: "WinSta0" if handle is desk.station.return_value else "IfwQa_test"
        desk.receiving_input.return_value = False
        image = Path("native-gui-assessment.exe")
        with patch.object(observe, "start_named") as launch:
            with observe.child(api, desk, "IfwQa_test", image, [], Path("case"), {}, None, False):
                pass
        desk.open_named.assert_called_once_with("IfwQa_test", 0, False, 1)
        launch.assert_called_once_with(image, [], cwd=Path("case"), env={}, stream=None, desktop="IfwQa_test", primary=False)
        api.assign_suspended.assert_called_once_with(api.new_job.return_value, launch.return_value, image)
        launch.return_value.resume.assert_called_once_with()
        launch.return_value.close.assert_called_once_with()

    def test_normal_secondary_uses_the_existing_desktop_without_an_inherited_desktop_or_command_pipe(self):
        api, desk, image = Mock(), Mock(), Path("native-gui-assessment.exe")
        desk.name.side_effect = lambda handle: "WinSta0" if handle is desk.station.return_value else "Default"
        desk.receiving_input.return_value = True
        with patch.object(observe, "ordinary_console", return_value=True), patch.object(observe, "start_named") as launch:
            with observe.child(api, desk, "Default", image, [], Path("case"), {}, None, False, private=False):
                pass
        desk.open_named.assert_called_once_with("Default", 0, False, 1)
        launch.assert_called_once_with(image, [], cwd=Path("case"), env={}, stream=None, desktop="Default", primary=False)
        launch.return_value.close.assert_called_once_with()

    def test_native_tray_evidence_and_missing_receipt_have_distinct_foreground_startup_inputs(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shell.json"
            for value in (False, True):
                path.write_text(json.dumps(dict(head="head", target="target", workflowRun="run", hosted=True,
                                                probeCompleted=True, observations={"shellIconAcceptedAndRemoved": value})))
                result = {}
                self.assertIs(observe.foreground_tray_input(path, "target", "head", "run", result), value)
                self.assertEqual(result["source"], "native Shell receipt")
                self.assertEqual(result["sha256"], observe.recorder.sha(path))
            for candidate in (path, path.with_name("missing.json")):
                result = {}
                self.assertFalse(observe.foreground_tray_input(candidate, "target", "other", "run", result))
                self.assertEqual(result["source"], "synthetic unavailable tray")
                self.assertNotIn("sha256", result)

    def test_foreground_cycle_requires_close_second_process_worker_identity_and_quit(self):
        api, desk, windows = Mock(), Mock(), Mock()
        primary, second = Mock(pid=12, _handle=2), Mock(pid=15, _handle=5)
        primary.poll.return_value = None
        second.poll.return_value = 0
        windows.events = []
        desk.name.return_value = "Default"
        desk.foreground.return_value = 22
        api.process_identity.side_effect = lambda handle: handle * 10
        api.wait_job_empty.return_value = True
        current = None
        launches = []
        result = {}
        with TemporaryDirectory() as directory:
            out = Path(directory)
            primary_log = out / "foreground-primary.log"

            def emit(text):
                with primary_log.open("ab") as stream:
                    stream.write(text.encode())

            def write(data):
                nonlocal current
                if data == b"T":
                    current = 21
                    emit("LAUNCHER_PRIMARY pid=12\nREADY Visible Available\nADAPTER Dx12 Cpu\n")
                elif data == b"Q":
                    primary.poll.return_value = 0
                    emit("DRAINED passes=5\n")
                else:
                    self.fail("Only the initial tray result and Quit belong on the primary command pipe")

            def close_window(hwnd):
                nonlocal current
                self.assertEqual(hwnd, current)
                current = None
                emit("WINDOW_RELEASED generation=1\n")

            def owner(_hwnd, pid):
                pid._obj.value = 12
                return 8

            @contextmanager
            def launch(_api, _desk, name, exe, args, _trial, _env, stream, first, *, private):
                nonlocal current
                launches.append((name, exe, args, first, private))
                if first:
                    yield primary, 1, 8
                    return
                self.assertIsNone(current)
                stream.write(b"LAUNCHER_SECONDARY server=12\n")
                emit("LAUNCHER_OPEN client=15\nADAPTER Dx12 Cpu\n")
                current = 22
                yield second, 3, None

            def accounting(_job, _kind, value, _size, _returned):
                value._obj.total = 1
                return True

            primary.stdin.write.side_effect = write
            windows.visible.side_effect = lambda **_kwargs: current
            windows.close_window.side_effect = close_window
            windows.owner.side_effect = owner
            api.query_job.side_effect = accounting
            fixture = Mock()
            fixture.Windows.return_value = windows
            with (patch.object(observe, "child", launch), patch.object(observe, "snapshot", return_value={"witnessSeen": None}),
                  patch.object(observe.recorder, "idle_complete", return_value=True),
                  patch.object(observe.recorder, "owned_worker", return_value=13),
                  patch.object(observe, "primary_job_members", side_effect=[[13, 1300], [13, 1300]])):
                observe.cycle(api, desk, "Default", 9, None, fixture, GUI, CONSOLE, out, {}, out,
                              "foreground", result, tray=True)
        self.assertEqual(launches, [("Default", GUI, [], True, False), ("Default", GUI, [], False, False)])
        self.assertEqual(result["stage"], "drained")
        self.assertTrue(result["primaryJobEmpty"])
        self.assertEqual((result["initialWindow"], result["reopenedWindow"], result["workerAfter"]), (21, 22, [13, 1300]))
        self.assertEqual(list(result["windowReadbacks"]), ["startup-intent", "first-dx12-adapter", "first-visible-window",
                                                          "hidden-before-launch", "reopen"])

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
