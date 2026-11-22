"""Portable controls for visible icon identity and genuine input/callback attribution."""

from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from activation_native import ICON, Native, Unavailable, callback_ok, center, expected_colors, matches, same_spot
from activation_worker import challenge, snapshot


class Activation(unittest.TestCase):
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
        with self.assertRaises(Unavailable):
            safe.input_pair(lambda: dict(self.spot, rgb=self.before), dict(self.spot, rgb=self.after), {}, "first")
        safe.send.assert_not_called()

    def test_callback_requires_our_v4_id_activation_and_native_dispatch_in_input_interval(self):
        event = [1, 0x203, ICON, 32, 2, 1005]
        self.assertTrue(callback_ok(event, 1000, 1010))
        for index, bad in ((0, 0), (1, 0x202), (1, 0x401), (2, 90), (5, 999), (5, 1011)):
            altered = event.copy()
            altered[index] = bad
            self.assertFalse(callback_ok(altered, 1000, 1010))
        self.assertFalse(callback_ok([], 1000, 1010))

    def test_qualification_reaches_gesture_with_matching_native_and_external_evidence(self):
        for label in ("first", "second", "armed"):
            self.stage(label)
        self.drive([dict(self.spot, rgb=self.before), dict(self.spot, rgb=self.after)])
        self.assertTrue(self.clicked)


if __name__ == "__main__":
    unittest.main()
