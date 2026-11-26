"""Replay the native desktop, window and restoration conditions independently of Windows."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from shared import QA, module, read, write
import private_desktop as trial

sys.path.insert(0, str(QA / "windows-desktop"))
NAME = "IfwQa_" + "a" * 32


def context(thread, input_name):
    return dict(windowStation="WinSta0", stationVisible=True, session=1, activeConsoleSession=1,
                wts=dict(session=1, connectionState=0, lockFlags=1), threadDesktop=thread, inputDesktop=input_name,
                inputObjectReceivesInput=True, threadReceivesInput=thread == input_name)


def phase(pid, created):
    root = dict(pid=pid, hwnd=pid + 5, tid=pid + 3)
    sample = dict(desktop=NAME, receivesInput=True, root=root, context=context(NAME, NAME), observerPid=15,
                  surfaces=dict(witnessCount=1, rootCount=1, otherVisible=0))
    return dict(primary=dict(pid=pid, created=created, machine=[0xaa64, 0xaa64]), root=root,
                privateRoot=sample, beforeQuitDesktop=deepcopy(sample), quit=dict(issuedQpc=20, exitedQpc=50),
                quitHelper=dict(pid=pid+1, tid=pid+8, desktop=NAME, created=created+1, machine=[0xaa64, 0xaa64],
                                exit=0, observedQpc=30, exitQpc=40))


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.ordinary, self.switched = context("Default", "Default"), context("Default", NAME)
        self.ticket = dict(name=NAME, parent=10, session=1, target=trial.ARM)
        self.supervisor = dict(supervisorPid=10, beforeSwitch=self.ordinary, afterSwitch=self.switched, switchToFixture=True,
                               created=dict(actual=NAME, requested=NAME, supervisorDesktop="Default"), nameExistedBefore=False,
                               afterRestore=self.ordinary, worker=dict(workerPid=15, jobClosed=True, workerExit=0),
                               status="observed", restorationStatus="restored", cleanup=dict(beforeRestore=self.switched,
                               inputBeforeRestore=NAME, switchBack=True, inputAfterRestore="Default", namedClosed=True,
                               originalHandleClosed=True))
        self.worker = dict(pid=15, parent=10, context=context(NAME, NAME), hiddenEnumerationWindow="0x45", hiddenWindowDestroyed=True,
                           before=dict(witnessCount=1, rootCount=0, otherVisible=0), after=dict(witnessCount=1, rootCount=0, otherVisible=0))
        self.first, self.second = phase(100, 200), phase(400, 700)

    def replay(self, full=True):
        for name, record in (("private-desktop", self.supervisor), ("desktop-start", self.ticket), ("private-worker", self.worker)):
            write(self.out / (name + ".json"), record)
        return trial.replay(self.out, dict(target=trial.ARM), self.first, [self.first, self.second] if full else [])

    def test_two_separate_processes_occupy_same_owned_desktop(self):
        self.assertEqual(self.replay(), dict(name=NAME, session=1, originalRestored=True))
        self.assertEqual(self.replay(False)["name"], NAME)

    def test_detached_mode_cannot_substitute_either_desktop(self):
        from upload.readback import replay
        for report, requested in (({}, True), ({"desktopMode":trial.MODE}, False)):
            write(self.out / "result.json", report)
            with self.assertRaisesRegex(ValueError, "desktop modes differ"):
                replay(self.out, live_only=True, expect_private=requested)

    def test_worker_failure_keeps_only_live_result_after_real_restore(self):
        self.supervisor["worker"]["workerExit"] = 1
        self.supervisor["status"] = "incomplete"
        self.replay(False)
        with self.assertRaises(ValueError):
            self.replay()

    def test_missing_restore_wrong_session_and_foreign_visible_root_fail(self):
        for row, field, value in (
            (self.ticket, "session", 7), (self.supervisor, "nameExistedBefore", True),
            (self.supervisor["cleanup"], "switchBack", False), (self.supervisor, "afterRestore", self.switched),
            (self.worker, "hiddenWindowDestroyed", False), (self.worker["after"], "witnessCount", 0),
            (self.first["privateRoot"]["surfaces"], "otherVisible", 1), (self.first["privateRoot"], "observerPid", 14),
        ):
            with self.subTest(field=field), patch.dict(row, {field:value}), self.assertRaises(ValueError):
                self.replay(False)

    def test_second_quit_on_default_or_incorrect_root_or_wrong_time_fails_full(self):
        for row, key, value in (
            (self.second["quitHelper"], "desktop", "Default"), (self.second["quitHelper"], "pid", 15),
            (self.second["beforeQuitDesktop"], "root", self.first["root"]),
            (self.second["quitHelper"], "exitQpc", 51), (self.second["quitHelper"], "exit", 1),
        ):
            with self.subTest(key=key), patch.dict(row, {key:value}), self.assertRaises(ValueError):
                self.replay()

    def test_early_refusal_observes_only_original_state(self):
        unexpected = context("Default", "Other")
        receipt = {"beforeSwitch": unexpected}
        trial.finish_restoration(SimpleNamespace(context=lambda: unexpected), receipt, RuntimeError)
        self.assertEqual(receipt["restorationStatus"], "fixture-not-selected")
        self.assertNotIn("cleanup", receipt)
        for bad in (context("Default", "Other"), dict(self.ordinary, activeConsoleSession=3)):
            with self.assertRaises(RuntimeError):
                trial.finish_restoration(SimpleNamespace(context=lambda: bad), self.supervisor, RuntimeError)
            self.assertEqual(self.supervisor["restorationStatus"], "unconfirmed")

    def run_supervisor(self, scenario):
        calls = []
        selected = "Other" if scenario == "early" else "Default"
        native = module("ifw_upload_original_desktop_contract", QA / "windows-desktop/run.py")

        class Desk:
            def context(self):
                return context("Default", selected)

            def open_named(self, name, *_):
                self.assert_default(name)
                return name

            @staticmethod
            def assert_default(name):
                if name != "Default":
                    raise AssertionError("Expected the supervisor's original handle")

            def create_detached(self, name):
                calls.append("create")
                return name

            def switch(self, name):
                nonlocal selected
                calls.append("original" if name == "Default" else "private")
                selected = name
                return True

            def close(self, _handle):
                return True

            def input_name(self):
                return selected

            def name(self, handle):
                return handle

            def thread(self):
                return 1

            def thread_desktop(self, _thread):
                return "Default"

        def run_worker(script, args, desktop, cwd, record, **_):
            nonlocal selected
            calls.append("worker")
            self.assertEqual(desktop, selected)
            self.assertEqual(args[-2:], ["--owned-desktop", desktop])
            if scenario == "timeout":
                raise TimeoutError("owned worker timed out")
            if scenario == "foreign":
                selected = "Other"
            record.update(workerPid=10, workerExit=0, jobClosed=True)
            return 0

        launch = SimpleNamespace(Desktop=Desk, recorder=SimpleNamespace(CleanupUnconfirmed=RuntimeError))
        with (patch.object(trial, "module", return_value=native), patch.object(native, "run_worker", side_effect=run_worker),
              patch.object(native.c, "set_last_error", create=True), patch.object(trial, "name_present", return_value=False)):
            if scenario == "success":
                trial.supervisor(launch, trial.ARM, self.out, self.out, self.out / "original.exe")
            else:
                with self.assertRaises((TimeoutError, RuntimeError)):
                    trial.supervisor(launch, trial.ARM, self.out, self.out, self.out / "original.exe")
        return calls, read(self.out / "private-desktop.json")

    def test_original_switch_and_restore_under_success_or_worker_timeout(self):
        for scenario, status in (("success", "observed"), ("timeout", "incomplete")):
            with self.subTest(scenario=scenario):
                calls, result = self.run_supervisor(scenario)
                self.assertEqual(calls, ["create", "private", "worker", "original"])
                self.assertEqual((result["status"], result["restorationStatus"]), (status, "restored"))

    def test_invalid_initial_or_unrelated_later_input_desktop_is_never_switched(self):
        calls, result = self.run_supervisor("early")
        self.assertEqual(calls, [])
        self.assertEqual(result["restorationStatus"], "fixture-not-selected")
        calls, result = self.run_supervisor("foreign")
        self.assertEqual(calls, ["create", "private", "worker"])
        self.assertEqual((result["status"], result["restorationStatus"]), ("incomplete", "unconfirmed"))
