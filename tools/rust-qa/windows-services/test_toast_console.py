"""Keep local and hosted physical notification receipts distinct during offline replay."""

from contextlib import ExitStack, contextmanager
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import notification_probe
import toast_console

from activation import TARGET
from toast_console import CleanupUnconfirmed, armed_screen, check_venue, corroborates_labels


class PhysicalVenueTests(unittest.TestCase):
    def test_policy_replay_requires_untouched_original_or_matching_transition_and_restoration(self):
        with TemporaryDirectory() as folder:
            target = TARGET["ARM64"][0]
            directory = Path(folder) / ("toast-history-" + target)
            directory.mkdir()
            original = dict(head="test-head", run="12", attempt="1")
            script = "tools/rust-qa/windows-services/toast_settings.ps1"
            desktop = dict(session=2, activeConsoleSession=2, stationVisible=True, windowStation="WinSta0",
                           wts=dict(session=2, connectionState=0, lockFlags=1), threadDesktop="Default",
                           inputDesktop="Default", threadReceivesInput=True, inputObjectReceivesInput=True)
            (directory / "result.json").write_text(json.dumps(dict(**original, target=target, desktop=desktop,
                                                                   observerInputs={script: "fixture-sha"})))
            identity = dict(**original, session=2, scriptSha256="fixture-sha")
            on = dict(state="On", count=1, enabled=True)
            off = {**on, "state": "Off"}
            seen = dict(**identity, action="Read", afterSender=True, status="observed", opened=True, closed=True,
                        pid=40, hwnd=90, notifications=on, doNotDisturb=on)

            def emit(suffix, item):
                path = Path(folder) / ("toast-settings-" + target + suffix + ".json")
                path.write_text(json.dumps(item))
                return path

            emit("", seen)
            self.assertEqual(toast_console.verify_policy(directory, "original")["doNotDisturb"], "On")
            permit = {**seen, "action": "Permit", "status": "permitted", "afterSender": False,
                      "toggleRequested": True, "finalDoNotDisturb": off}
            restore = {**seen, "action": "Restore", "status": "restored", "doNotDisturb": off,
                       "toggleRequested": True, "finalDoNotDisturb": on}
            emit("-permit", permit)
            emit("-restore", restore)
            intent = dict(**identity, original="On", desired="Off",
                          control="SystemSettings_Notifications_QuietHours_MuteNotification_Enabled_ToggleSwitch")
            intent_path = emit("-intent", intent)
            self.assertTrue(toast_console.verify_policy(directory, "permitted")["toggleRestored"])
            with self.assertRaises(ValueError):
                toast_console.verify_policy(directory, "original")
            for bad in ({"session": 3}, {"scriptSha256": "other"}, {"doNotDisturb": on},
                        {"finalDoNotDisturb": off}, {"closed": False}):
                emit("-restore", {**restore, **bad})
                with self.subTest(change=bad), self.assertRaises(ValueError):
                    toast_console.verify_policy(directory, "permitted")
            emit("-restore", {**seen, "action": "Restore", "status": "no-owned-change", "opened": False})
            emit("", {**seen, "doNotDisturb": off})
            emit("-permit", {**permit, "doNotDisturb": off, "toggleRequested": False})
            with self.assertRaises(ValueError):
                toast_console.verify_policy(directory, "permitted")
            intent_path.unlink()
            self.assertFalse(toast_console.verify_policy(directory, "permitted")["toggleRestored"])

    def test_clean_observer_start_failure_preserves_original_sender_once(self):
        child = MagicMock()
        child.__enter__.side_effect = OSError("could not start observer")
        with TemporaryDirectory() as folder:
            receipt, sends = {}, []
            with armed_screen(child, Path(folder), receipt):
                sends.append("original")
            self.assertEqual(sends, ["original"])
            self.assertFalse(receipt["armedBeforeSender"])
            self.assertTrue((Path(folder) / "physical.json").is_file())
            with self.assertRaises(OSError), armed_screen(child, Path(folder), {"pid": 7}):
                self.fail("The child did not drain")
            child.__enter__.side_effect = CleanupUnconfirmed("cannot confirm cleanup")
            with self.assertRaises(CleanupUnconfirmed), armed_screen(child, Path(folder), {}):
                self.fail("Unconfirmed observer cleanup cannot start a sender")

    def test_normal_arm64_entry_passes_its_pinned_profile_to_the_physical_observer(self):
        with TemporaryDirectory() as temp, ExitStack() as stubs:
            work = Path(temp)
            target, machine = TARGET["ARM64"]
            frames = work / ("toast-physical-" + target)

            @contextmanager
            def profile(_api, parent, token, receipt):
                area = parent / ("ifw-shell-" + token)
                area.mkdir()
                try:
                    yield area
                finally:
                    (area / "synthetic.fixture").unlink()
                    area.rmdir()
                    receipt["profileRemoved"] = True

            @contextmanager
            def child(_api, _exe, _args, area, env, _log, _receipt):
                token = (area / "synthetic.fixture").read_text()
                self.assertRegex(token, "^[0-9a-f]{32}$")
                self.assertEqual((env["IFW_QA_INVENTORY_TOKEN"], env["IFW_QA_ISOLATED"]), (token, "1"))
                self.assertEqual((env["TMP"], env["TEMP"]), (str(area), str(area)))
                frames.mkdir()
                (frames / "ready").touch()
                yield MagicMock()

            stubs.enter_context(patch.dict(os.environ, RUNNER_TEMP=temp))
            stubs.enter_context(patch.object(toast_console, "ART", work))
            stubs.enter_context(patch.object(toast_console, "ordinary_console", return_value=True))
            stubs.enter_context(patch.object(toast_console.toast_history, "request_identity"))
            stubs.enter_context(patch.object(toast_console.toast_history, "observe_sender", return_value=0))
            for name, stub in {"Win32": MagicMock(), "Desktop": MagicMock(), "fixture_profile": profile,
                               "pin_new_marker": lambda _, _api, p, t: p.write_text(t),
                               "select_powershell": lambda *_: ("powershell.exe", []),
                               "pe_machine": lambda _: machine, "child": child}.items():
                stubs.enter_context(patch.object(notification_probe, name, stub))
            notification_probe.Desktop.return_value.context.return_value = {"session": 2}
            self.assertEqual(toast_console.observe_arm64(), 0)
            receipt = json.loads((frames / "observer.json").read_bytes())
            self.assertTrue(receipt["armedBeforeSender"] and receipt["profileRemoved"])

    def test_desktop_corewindow_missing_from_classic_enumeration_is_counted(self):
        foreground = dict(hwnd=0x10204, pid=7600, core=True, visible=True)
        modern = dict(qpc=1000, foreground=foreground, classic=0, children=3, uiaCore=1, handlelessShell=0,
                      unresolvedShell=0, errors=0, uiaQueried=True, uniqueCore=1)
        diagnostics = dict(samples=1, firstQpc=1000, lastQpc=1000, visibleCoreWindowVisits=1)
        receipt = dict(discovery=[modern], diagnostics=diagnostics)
        toast_console.check_discovery(receipt)
        for change in ({"uniqueCore": 0}, {"uniqueCore": 3}, {"classic": 2}, {"unresolvedShell": 3},
                       {"uiaQueried": False}, {"children": 0}, {"foreground": {**foreground, "pid": 0}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                toast_console.check_discovery({**receipt, "discovery": [{**modern, **change}]})
        with self.assertRaises(ValueError):
            toast_console.check_discovery({**receipt, "diagnostics": {**diagnostics, "visibleCoreWindowVisits": 0}})

    def test_modern_popup_crop_requires_both_complete_native_coverage_checks(self):
        view = dict(bounds=[-20, 0, 180, 120], coveredPixelsBefore=3000, coveredPixelsAfter=3000)
        capture = [-10, 5, 100, 30]
        toast_console.check_crop_coverage(view, capture)
        for change in ({"bounds": [0, 0, 180, 120]}, {"coveredPixelsBefore": 2999}, {"coveredPixelsAfter": 2999}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                toast_console.check_crop_coverage({**view, **change}, capture)

    def test_original_local_observer_has_no_hosted_run(self):
        sender = {"host": "isolated-vm", "target": TARGET["X64"][0]}
        check_venue(sender, {})
        check_venue(sender, {"target": sender["target"]})
        for mismatch in ({"host": "github-hosted"}, {"target": TARGET["ARM64"][0]}):
            with self.subTest(mismatch=mismatch), self.assertRaises(ValueError):
                check_venue(sender, mismatch)

    def test_arm64_pairs_only_the_same_compiler_run_attempt_and_observer(self):
        identity = dict(target=TARGET["ARM64"][0], head="test-revision", run="test-run", attempt="test-attempt")
        sender = {**identity, "observerInputs": {"tools/rust-qa/windows-services/toast_console.ps1": "script-digest"}}
        screen = {**identity, "host": "github-hosted", "scriptSha256": "script-digest"}
        check_venue(sender, screen)
        for key in screen:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_venue(sender, {**screen, key: "different"})

    def test_capture_needs_visual_review_when_point_provider_did_not_identify_both_labels(self):
        host = dict(hwnd=2, pid=3, session=1)
        title, body = {"runtimeId": "title"}, {"runtimeId": "body"}
        crop = {**host, "labels": [title, body]}
        match = dict(host=host, title=title, body=body)
        self.assertTrue(corroborates_labels(dict(status="visible", presentation={"match": match}), crop))
        self.assertFalse(corroborates_labels(dict(status="unavailable"), crop))
        changed = {**match, "body": {"runtimeId": "covering-element"}}
        self.assertFalse(corroborates_labels(dict(status="visible", presentation={"match": changed}), crop))
