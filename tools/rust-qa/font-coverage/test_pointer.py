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
