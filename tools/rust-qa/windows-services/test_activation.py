"""Portable controls for visible icon identity and genuine input/callback attribution."""

from contextlib import nullcontext
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from activation_native import ICON, Native, Unavailable, callback_tick, center, expected_colors, matches, same_spot
from activation_worker import challenge, check_registration_cleanup, gesture, overflow, snapshot


class Activation(unittest.TestCase):
    def test_private_explorer_must_present_its_taskbar_before_the_receiver_starts(self):
        api = Native.__new__(Native)
        api.require_desktop = Mock()
        api.find = Mock(side_effect=[0x40132, 0x40132, 0x40132])
        api.desk = Mock()
        sizes = iter([(0, 0, 0, 0), (0, 720, 1024, 768), (0, 720, 1024, 768)])

        def read_rect(_bar, pointer):
            rect = c.cast(pointer, c.POINTER(w.RECT)).contents
            rect.left, rect.top, rect.right, rect.bottom = next(sizes)
            return True

        api.desk.window_rect.side_effect = read_rect
        api.desk.visible.side_effect = [True, False, True]
        record = {}
        with patch("activation_native.time.sleep") as wait:
            self.assertEqual(api.wait_for_taskbar(record), 0x40132)
        self.assertEqual(wait.call_count, 2)
        self.assertEqual(api.require_desktop.call_count, 3)
        self.assertEqual(record["startupTaskbar"]["first"]["rect"], [0, 0, 0, 0])
        self.assertEqual(record["startupTaskbar"]["last"]["rect"], [0, 720, 1024, 768])

    def test_absent_or_unpositioned_taskbar_expires_without_starting_the_receiver(self):
        api = Native.__new__(Native)
        api.require_desktop = Mock()
        api.find = Mock(side_effect=[None, 0x40132])
        api.desk = Mock()
        api.desk.window_rect.return_value = False
        record = {}
        with (patch("activation_native.time.monotonic", side_effect=[0, 1, 2, 19]),
              patch("activation_native.time.sleep"), self.assertRaises(Unavailable)):
            api.wait_for_taskbar(record)
        self.assertIsNone(record["startupTaskbar"]["last"]["rect"])
        self.assertIn("shellWindowAfterAttempt", record)

    def test_native_registration_retry_requires_the_same_shell_and_confirmed_cleanup(self):
        first = {"private_tray.initial.add": True, "private_tray.registered": True, "private_tray.remove": True}
        retried = {**first, "private_tray.initial.add": False, "private_tray.startup_retry.add": True,
                   "private_tray.startup_host_unchanged": True}
        for case in (first, retried, {"private_tray.initial.add": False, "private_tray.registered": False},
                     {**retried, "private_tray.startup_retry.add": False, "private_tray.registered": False}):
            check_registration_cleanup(case)
        for case in ({**retried, "private_tray.initial.add": True},
                     {**retried, "private_tray.startup_host_unchanged": False},
                     {**retried, "private_tray.remove": False}, {**first, "private_tray.registered": False}, {}):
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                check_registration_cleanup(case)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.area = Path(temp.name)
        self.token = "112233" + "a" * 26
        self.api, self.proc = Mock(name="desktop"), Mock(pid=111)
        self.api.name = "IfwQa_" + self.token
        self.before, self.after = expected_colors(self.token)
        self.spot = {"rect": [-40, -4, -16, 20], "center": [-28, 8], "hit": 41, "root": 40,
                     "shellPid": 100, "ownerHwnd": 22, "iconId": ICON}

    def stage(self, name, *, pid=111, hwnd=22, ready=1, rect=None, opens=0):
        numbers = [pid, hwnd, ICON, ready, 0, *(rect or self.spot["rect"]), opens]
        (self.area / name).write_text(" ".join(map(str, numbers)), encoding="ascii")

    def drive(self, samples):
        with patch("activation_worker.wait_color", side_effect=samples), patch("activation_worker.overflow", return_value=nullcontext()), \
                patch("activation_worker.gesture") as gesture:
            try:
                challenge(self.api, self.area, "-", self.proc, (40, 100), 72, {})
            finally:
                self.clicked = gesture.called

    def test_both_actual_colors_and_physical_center(self):
        self.assertEqual(self.before, [41, 198, 99])
        self.assertEqual(self.after, [214, 57, 156])
        self.assertFalse(matches(self.after, self.before))
        self.assertFalse(matches([self.after[0]+9, *self.after[1:]], self.after))
        self.assertEqual(center(self.spot["rect"]), self.spot["center"])
        for r in ((3, 3, 3, 4), (0, 0, 500, 1000)):
            with self.assertRaises(Unavailable):
                center(r)

    def test_unidentified_chevron_pixel_never_reaches_input(self):
        self.stage("first")
        with self.assertRaisesRegex(Unavailable, "first colored center"):
            self.drive([None, None])
        self.assertFalse(self.clicked)
        self.assertFalse((self.area / "arm").exists())

    def test_same_center_in_another_explorer_window_is_refused(self):
        self.stage("first")
        self.stage("second")
        a = dict(self.spot, rgb=self.before)
        b = dict(self.spot, rgb=self.after, root=99)
        self.assertFalse(same_spot(a, b))
        with self.assertRaisesRegex(Unavailable, "same visible slot"):
            self.drive([a, b])
        self.assertFalse(self.clicked)

    def test_armed_callback_owner_or_rectangle_changes_refuse_input(self):
        self.stage("first")
        self.stage("second")
        for change in ({"hwnd": 71}, {"rect": [4, 4, 28, 28]}, {"opens": 1}):
            self.stage("armed", **change)
            with self.assertRaises(Unavailable):
                self.drive([dict(self.spot, rgb=self.before), dict(self.spot, rgb=self.after)])
            self.assertFalse(self.clicked)

    def test_receiver_pid_matches_the_original_live_process(self):
        self.stage("first", pid=999)
        with self.assertRaisesRegex(ValueError, "source identity"):
            snapshot(self.area, "first", self.proc, {})

    def test_color_is_checked_again_immediately_before_the_native_input_call(self):
        safe = Native.__new__(Native)
        safe.name = self.api.name
        safe.send = Mock()
        safe.require_desktop = Mock()
        with self.assertRaises(Unavailable):
            safe.input_pair(lambda: dict(self.spot, rgb=self.before), dict(self.spot, rgb=self.after), {}, "first")
        safe.send.assert_not_called()

    def test_callback_requires_our_v4_id_exact_queue_entry_and_native_dispatch_in_input_interval(self):
        event = [1, 0x400, ICON, 1004, 1, 1005, 1004]
        self.assertEqual(callback_tick(event, 1000, 1010), 1004)
        for index, bad in ((0, 0), (1, 0x202), (1, 0x401), (2, 90), (3, -1), (3, 999),
                           (3, 1000), (3, 1006), (5, 999), (5, 1011)):
            altered = event.copy()
            altered[index] = bad
            self.assertIsNone(callback_tick(altered, 1000, 1010))
        self.assertIsNone(callback_tick([], 1000, 1010))
        event[1] = 0x203
        self.assertIsNone(callback_tick(event, 1000, 1010))
        self.assertIsNone(callback_tick(event, 1000, 1010, 1004))
        self.assertIsNone(callback_tick(event, 1000, 1010, 1005))
        self.assertEqual(callback_tick(event, 1000, 1010, 1003), 1004)

    def test_queued_time_extends_across_both_clock_wraps_and_rejects_old_messages_dispatched_late(self):
        mask64 = (1 << 64) - 1
        for boundary in (1 << 31, 1 << 32, 2 << 32, 1 << 64):
            start, dispatch, read = boundary - 4, (boundary + 3) & mask64, (boundary + 9) & mask64
            event = [1, 0x400, ICON, (boundary + 1) & 0xffffffff, 0, dispatch, 0]
            self.assertEqual(callback_tick(event, start, read), (boundary + 1) & mask64)
            event[3] = (boundary - 5) & 0xffffffff
            self.assertIsNone(callback_tick(event, start, read))
            event[3] = (boundary + 5) & 0xffffffff
            self.assertIsNone(callback_tick(event, start, read))

    def pointer(self, sends, *, moved=False, released=False):
        api = Native.__new__(Native)
        api.name = self.api.name
        api.send = Mock(side_effect=sends)
        api.require_desktop, api.tick = Mock(), Mock(return_value=100)
        def position(out):
            point = c.cast(out, c.POINTER(w.POINT)).contents
            point.x, point.y = self.spot["center"]
            if moved and api.send.call_count:
                point.x += 40
            return 1
        api.cursor = position
        api.key = lambda key: 0x8000 if key == 1 and api.send.call_count and not released else 0
        return api

    def test_partial_down_never_releases_after_the_cursor_color_owner_or_desktop_changes(self):
        good = dict(self.spot, rgb=self.after)
        for change in ("cursor", "color", "shell", "job", "desktop", "button"):
            with self.subTest(change=change):
                api = self.pointer([1], moved=change == "cursor", released=change == "button")
                after = dict(good)
                if change == "color":
                    after["rgb"] = self.before
                if change == "shell":
                    after["root"] = 99
                if change == "job":
                    after = Unavailable("Visible owner failed job check")
                if change == "desktop":
                    api.require_desktop.side_effect = [None, None, Unavailable("Lost the input desktop")]
                receipt = {}
                with self.assertRaisesRegex(RuntimeError, "release on the owned icon"):
                    api.input_pair(Mock(side_effect=[good, after]), good, receipt, "first")
                self.assertTrue(receipt["incompleteInput"])
                self.assertIn("firstReleaseError", receipt)
                self.assertEqual(api.send.call_count, 1)

    def test_partial_down_remains_a_failed_trial_after_a_fully_guarded_release(self):
        good = dict(self.spot, rgb=self.after)
        api, receipt = self.pointer([1, 1]), {}
        recheck = Mock(return_value=good)
        with self.assertRaisesRegex(RuntimeError, "complete gesture"):
            api.input_pair(recheck, good, receipt, "first")
        self.assertEqual(recheck.call_count, 2)
        self.assertEqual([call.args[0] for call in api.send.call_args_list], [2, 1])
        self.assertEqual(receipt["firstCleanupUp"], 1)
        self.assertTrue(receipt["incompleteInput"])

    def test_incomplete_input_never_drags_the_pointer_or_becomes_unavailable_in_cleanup(self):
        good = dict(self.spot, rgb=self.after)
        api, receipt = self.pointer([1], moved=True), {}
        api.move = Mock(return_value=1)
        with self.assertRaisesRegex(RuntimeError, "release on the owned icon"):
            gesture(api, lambda: good, good, self.proc, self.area, receipt)
        api.move.assert_called_once_with(*self.spot["center"])
        self.assertTrue(receipt["cursorRestoreWithheldAfterIncompleteInput"])

    def test_qualification_reaches_gesture_with_matching_native_and_external_evidence(self):
        for label in ("first", "second", "armed"):
            self.stage(label)
        self.drive([dict(self.spot, rgb=self.before), dict(self.spot, rgb=self.after)])
        self.assertTrue(self.clicked)


class OverflowCompletion(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.area = Path(temp.name)
        self.host = self.area / "pwsh.exe"
        self.host.touch()
        self.provider = {"overflow": "requested", "providerReady": True, "completed": True,
                         "releaseAcknowledged": True, "overflowClosed": True, "restoreOutcome": "verified closed"}

    def observe(self, data, *, ready=True, exit_code=0, timeout=False, diagnostic=b"", startup_timeout=False):
        record, api, proc = {}, Mock(), Mock()
        self.record, self.entered = record, False
        proc.returncode = exit_code
        proc.poll.return_value = None if startup_timeout else exit_code
        if ready:
            (self.area / "overflow.ready").write_bytes(b"ready")
        api.launch_child.return_value = nullcontext(proc)
        reply = (data, diagnostic)
        proc.communicate.side_effect = [subprocess.TimeoutExpired("owned helper", 6), reply] if timeout else [reply]
        with patch("activation_worker.shutil.which", return_value=str(self.host)), \
                patch.object(subprocess, "CREATE_NO_WINDOW", 0, create=True), \
                patch("activation_worker.time.monotonic", side_effect=[0, 0, 37]), patch("activation_worker.time.sleep"):
            with overflow(str(self.host), self.area, api, 40, 100, record):
                self.entered = True
        return record

    def test_only_verified_restore_or_a_proven_untouched_flyout_can_pass(self):
        self.assertTrue(self.observe(json.dumps(self.provider).encode())["provider"]["overflowClosed"])
        untouched = {"overflow": "already visible", "providerReady": True, "completed": True, "restoreOutcome": "untouched"}
        self.assertTrue(self.observe(json.dumps(untouched).encode())["ready"])

    def test_absent_ready_or_start_timeout_cannot_enter_the_observation(self):
        for late in (False, True):
            with self.subTest(late=late), self.assertRaises(RuntimeError):
                self.observe(json.dumps(self.provider).encode(), ready=False, startup_timeout=late)
            self.assertFalse(self.entered)
            self.assertEqual(self.record["startTimedOut"], late)

    def test_provider_failures_and_cleanup_timeouts_reject_even_a_successful_gesture(self):
        for values, options in (({"completed": False}, {}), ({"operationError": "provider"}, {}), ({"operationError": ""}, {}),
                                ({"restoreError": "lost owner"}, {}), ({"releaseAcknowledged": False}, {}),
                                ({"overflowClosed": False}, {}), ({"restoreOutcome": "untouched"}, {}),
                                ({"overflow": "unknown"}, {}), ({}, {"exit_code": 1}),
                                ({}, {"timeout": True}), ({}, {"diagnostic": b"restore failed"})):
            with self.subTest(values=values, options=options), self.assertRaises(RuntimeError):
                self.observe(json.dumps({**self.provider, **values}).encode(), **options)
            self.assertTrue(self.entered)

    def test_missing_or_malformed_provider_json_rejects_completion(self):
        for output in (b"", b"invalid", b"[]", b"{}"):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                self.observe(output)


if __name__ == "__main__":
    unittest.main()
