import unittest
from ctypes import wintypes
from unittest.mock import Mock, call, patch

from observe import WindowsInput


class WindowsPointerTests(unittest.TestCase):
    def test_click_keeps_coordinates_and_button_together_on_the_owned_window(self):
        controls = object.__new__(WindowsInput)
        controls.disposable = False
        controls.observer = Mock()
        controls.observer.visible.return_value = 175
        controls.observer.post.return_value = True
        controls.point = wintypes.POINT
        controls.pointer_positions = {"ownedDesktopPoint": 0, "windowMessagesOnly": 0}
        controls.pointer_events = []
        calls = Mock()
        calls.attach_mock(controls.observer.post, "post")
        with patch("observe.time.sleep", calls.sleep):
            controls.click(5, 12)
        position = (12 << 16) | 5
        self.assertEqual(calls.mock_calls, [
            call.post(175, 0x200, 0, position), call.post(175, 0x201, 1, position), call.sleep(.09),
            call.post(175, 0x200, 1, position), call.post(175, 0x202, 0, position), call.sleep(.09),
        ])
        self.assertEqual(controls.pointer_positions, {"ownedDesktopPoint": 0, "windowMessagesOnly": 2})
        self.assertEqual([e["button"] for e in controls.pointer_events], [0x201, 0x202])
        self.assertTrue(all(e["movePosted"] and e["buttonPosted"] for e in controls.pointer_events))

    def test_foreign_hit_preserves_only_messages_to_the_verified_fixture(self):
        controls = object.__new__(WindowsInput)
        controls.disposable, controls.point = True, wintypes.POINT
        controls.observer, controls.set_position = Mock(), Mock()
        controls.observer.visible.return_value = 11
        controls.foreground, controls.client_to_screen, controls.at_point = lambda: 11, lambda *_: True, lambda _: 22
        controls.observer.ancestor.return_value = 22
        controls.pointer_positions, controls.pointer_events = {"ownedDesktopPoint": 0, "windowMessagesOnly": 0}, []
        with patch("observe.time.sleep"):
            controls.mouse(70, 52, False, 0x201)
        controls.set_position.assert_not_called()
        self.assertFalse(controls.pointer_events[0]["pointOwned"])
        self.assertEqual([post.args[0] for post in controls.observer.post.call_args_list], [11, 11])
