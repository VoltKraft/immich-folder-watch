"""Exercise the ordinary secondary invocation and the evidence required to attribute its window."""
from contextlib import contextmanager, nullcontext
import ctypes as c
import json
import os
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import observe
import retained_window
from test_retained_window import FIRST_RENDER, OwnedRoot, TITLE


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
        witnessed = []
        with patch.object(observe, "start_named") as launch:
            def before_resume(secondary):
                api.assign_suspended.assert_called_once_with(api.new_job.return_value, secondary, image)
                secondary.resume.assert_not_called()
                witnessed.append(secondary.pid)
            with observe.child(api, desk, "IfwQa_test", image, [], Path("case"), {}, None, False,
                               before_resume=before_resume):
                pass
        self.assertEqual(witnessed, [launch.return_value.pid])
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
        self.exercise_cycle()

    def exercise_cycle(self, subject="canonical", *, private=False, restart=False, keyboard_focus=True):
        api, desk = Mock(), Mock()
        windows = OwnedRoot(12)
        primary, second = Mock(pid=12, _handle=2), Mock(pid=15, _handle=5)
        primary.poll.return_value = None
        second.poll.return_value = 0
        name = "IfwQa_Launcher_" + "3" * 32 if private else "Default"
        label = "restart" if restart else ("activation" if private else "foreground")
        desk.name.return_value = name
        if private:
            windows.desktop = 9
            windows.enum_callback = lambda callback: callback
            windows.enumerate = lambda desktop, visit, _: desktop == 9 and all(visit(hwnd, 0) for hwnd in (2, windows.hwnd))
            def owner(hwnd, pid):
                if hwnd != 2:
                    return OwnedRoot.owner(windows, hwnd, pid)
                pid._obj.value = os.getpid()
                return 7
            def text(buf, value):
                buf.value = value
                return len(value)
            windows.owner = owner
            windows.caption = lambda hwnd, buf, _: text(buf, name if hwnd == 2 else windows.title)
            desk.window_class.side_effect = lambda hwnd, buf, _: text(buf, "Static" if hwnd == 2 else "Window Class")
            desk.thread.return_value = 7
            desk.thread_desktop.side_effect = lambda tid: 9 if tid == 7 else None
            desk.name.side_effect = lambda desktop: name if desktop == 9 else {"win32Error": 5}
            desk.receiving_input.return_value = False
            desk.iconic.return_value = False
        desk.foreground.side_effect = lambda: windows.hwnd if keyboard_focus else None
        api.process_identity.side_effect = lambda handle: handle * 10
        api.wait_job_empty.return_value = True
        launches = []
        result = {}
        with TemporaryDirectory() as directory:
            out = Path(directory)
            primary_log = out / (label + "-primary.log")

            def emit(text):
                with primary_log.open("ab") as stream:
                    stream.write(text.encode())

            def write(data):
                if data in (b"T", b"N"):
                    windows.hwnd = 21
                    windows.show(3, create=True)
                    emit("LAUNCHER_PRIMARY pid=12\nREADY Visible " + ("Unavailable" if private else "Available") + "\n")
                    emit(FIRST_RENDER if subject == "retained" else "GRAPHICS_READY generation=1\nADAPTER Dx12 Cpu\n")
                elif data == b"Q":
                    primary.poll.return_value = 0
                    if subject == "retained":
                        emit("WINDOW_RELEASED passes=5\n")
                    emit("DRAINED passes=5\n")
                else:
                    self.fail("Only the initial tray result and Quit belong on the primary command pipe")

            windows.on_close = lambda: emit("WINDOW_HIDDEN\n" if subject == "retained" else "WINDOW_RELEASED passes=1\n")

            @contextmanager
            def launch(_api, _desk, name, exe, args, _trial, _env, stream, first, *, private, before_resume=None):
                launches.append((name, exe, args, first, private))
                if first:
                    yield primary, 1, 8
                    return
                self.assertIsNone(windows.visible())
                if before_resume:
                    before_resume(second)
                grant = "denied hresult=-2147024891" if keyboard_focus else "granted"
                stream.write(f"LAUNCHER_FOREGROUND_GRANT server=12 state={grant}\nLAUNCHER_SECONDARY server=12\n".encode())
                emit("LAUNCHER_OPEN client=15\n")
                if subject == "canonical":
                    windows.hwnd = 22
                    emit("GRAPHICS_READY generation=2\nADAPTER Dx12 Cpu\n")
                windows.show(20, create=subject == "canonical")
                emit(f"WINDOW_FOREGROUND_REQUEST pid=12 hwnd={windows.hwnd} accepted=false\n")
                yield second, 3, None

            def accounting(_job, _kind, value, _size, _returned):
                value._obj.total = 1
                return True

            primary.stdin.write.side_effect = write
            api.query_job.side_effect = accounting
            fixture = Mock(TITLE=TITLE)
            fixture.Windows.return_value = windows
            scan = dict(witnessSeen=private, desktop=name,
                        initialThreadDesktop={"win32Error": 5} if private else name, windows=[])
            with (patch.object(observe, "child", launch), patch.object(observe, "snapshot", return_value=scan),
                  patch.object(c, "set_last_error", create=True),
                  patch.object(observe, "bind", return_value=Mock(side_effect=[14, 16, 23])),
                  patch.object(retained_window, "WindowLifetime", return_value=Mock(events=windows.life)),
                  patch.object(retained_window, "visible_surface"), patch.object(retained_window, "focus_sample",
                               return_value=dict(foreground=keyboard_focus, active=True, focused=keyboard_focus)),
                  patch.object(observe.recorder, "idle_complete", return_value=True),
                  patch.object(observe.recorder, "owned_worker", return_value=13),
                  patch.object(observe, "primary_job_members", side_effect=[[13, 1300], [13, 1300]]),
                  nullcontext() if keyboard_focus else self.assertRaisesRegex(ValueError, "foreground and keyboard focus")):
                observe.cycle(api, desk, name, 9, 2 if private else None, fixture, GUI, CONSOLE, out, {}, out,
                              label, result, tray=not private, subject=subject)
        self.assertEqual(result["stage"], "drained")
        self.assertTrue(result["primaryJobEmpty"])
        if restart:
            self.assertEqual(launches, [(name, GUI, [], True, True)])
            self.assertEqual(result["workerBefore"], [13, 1300])
            self.assertTrue(result["privateWindowMembership"]["first-visible-window"]["qualified"])
            return result
        self.assertEqual(launches, [(name, GUI, ["--autostart"] if private else [], True, private),
                                    (name, GUI, [], False, private)])
        self.assertEqual(result["secondaryLaunch"], dict(api="CreateProcessW", source="observer", callerPid=os.getpid()))
        self.assertEqual((result["initialWindow"], result["reopenedWindow"], result["workerAfter"]),
                         (21, 21 if subject == "retained" else 22, [13, 1300]))
        self.assertEqual(list(result["windowReadbacks"]), ["startup-intent", "first-dx12-adapter", "first-visible-window",
                                                          "hidden-before-launch", "reopen"])
        return result

    def test_private_activation_and_restart_require_the_witness_on_both_gui_subjects(self):
        for subject in ("canonical", "retained"):
            for restart in (False, True):
                with self.subTest(subject=subject, restart=restart):
                    result = self.exercise_cycle(subject, private=True, restart=restart)
                    members = result["privateWindowMembership"]
                    for stage in (["first-visible-window"] if restart else ["first-visible-window", "reopen"]):
                        self.assertTrue(members[stage]["qualified"])
                        self.assertEqual(members[stage]["after"]["target"]["desktop"], {"win32Error": 5})

    def test_retained_no_argument_secondary_and_shellless_fallback_reopen_original_native_root_and_worker(self):
        for private in (False, True):
            with self.subTest(private=private):
                result = self.exercise_cycle("retained", private=private)
                self.assertEqual(result["retainedWindow"]["lifetimeBeforeQuit"], [[21, "create", 3]])
                self.assertEqual(result["secondaryTotalProcesses"], 1)
                self.assertEqual(result["keyboardFocus"]["applicable"], not private)

    def test_negative_keyboard_readback_retains_the_grant_request_and_confirmed_normal_quit(self):
        clock = Mock()
        clock.monotonic.side_effect = range(100)
        with patch.object(observe, "time", clock), patch.object(retained_window, "time", clock):
            result = self.exercise_cycle("retained", keyboard_focus=False)
        self.assertEqual(result["foregroundHandoff"],
                         dict(server=12, grant="granted", hwnd=21, hresult=None, unavailableReason=None, requestAccepted=False))
        self.assertFalse(result["foregroundObservation"]["observed"])
        self.assertFalse(result["keyboardFocus"]["observed"])
        self.assertEqual((result["primaryExit"], result["primaryUiPassesAtQuit"]), (0, 5))

    def test_receipt_requires_the_original_primary_and_its_worker(self):
        secondary = ["LAUNCHER_FOREGROUND_GRANT server=12 state=denied hresult=-2147024891", "LAUNCHER_SECONDARY server=12"]
        primary = ["LAUNCHER_OPEN client=15", "WINDOW_FOREGROUND_REQUEST pid=12 hwnd=32 accepted=false"]
        receipt = dict(primaryPid=12, secondaryPid=15, initialWindowPid=12, reopenedWindowPid=12,
                       reopenedWindow=32,
                       hiddenBeforeLaunch=True, workerBefore=[13, 1234], workerAfter=[13, 1234],
                       secondaryExit=0, secondaryJobEmpty=True, secondaryTotalProcesses=1)
        observe.qualify(secondary, primary, receipt)
        self.assertEqual(receipt["foregroundHandoff"], dict(server=12, grant="denied", hwnd=32,
                                                           hresult=-2147024891, unavailableReason=None, requestAccepted=False))
        for grant in ("granted", "unavailable reason=input-desktop"):
            observe.qualify([f"LAUNCHER_FOREGROUND_GRANT server=12 state={grant}", secondary[1]], primary, receipt)
            self.assertEqual(receipt["foregroundHandoff"]["grant"], grant.split()[0])
        for key, value in (("hiddenBeforeLaunch", False), ("reopenedWindowPid", 15),
                           ("workerAfter", [13, 4321]), ("secondaryTotalProcesses", 2)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                observe.qualify(secondary, primary, dict(receipt, **{key: value}))
        for wrong_secondary, wrong_primary in [
            (["READY Visible Unavailable"], primary), (secondary, []),
            (secondary, ["LAUNCHER_OPEN"]), (secondary, primary * 2),
            ([secondary[0].replace("server=12", "server=15"), secondary[1]], primary),
            (secondary, [primary[0], primary[1].replace("hwnd=32", "hwnd=31")]),
            (secondary, primary + [primary[1]]),
        ]:
            with self.assertRaises(ValueError):
                observe.qualify(wrong_secondary, wrong_primary, receipt)


if __name__ == "__main__":
    unittest.main()
