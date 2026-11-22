from ctypes import wintypes
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from observe import WindowsInput
from text_observations import MissingObservation, last_field_pointer


class WindowsPointerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.controls = c = object.__new__(WindowsInput)
        c.log = Path(temporary.name) / 'subject.log'
        c.process = Mock()
        c.process.poll.return_value = None
        c.observer = Mock()
        c.first_gesture = True
        self.hwnd = 175
        c.observer.visible.return_value = self.hwnd
        c.observer.ancestor.side_effect = lambda hwnd, _: hwnd
        c.point = wintypes.POINT
        c.disposable = True
        c.pointer_positions = {'ownedDesktopPoint': 0, 'windowMessagesOnly': 0}
        c.pointer_events = []
        self.active = self.hwnd
        self.hit = self.hwnd
        self.pixel = (452, 301)
        self.pass_no = 2
        self.held = False
        c.foreground = lambda: self.active
        c.at_point = lambda _: self.hit
        c.client_to_screen = lambda hwnd, point: hwnd == self.hwnd
        c.cursor = self.read_cursor
        c.set_position = Mock(side_effect=self.move)
        c.observer.post.side_effect = self.post
        c.activate = Mock(side_effect=self.activate)
        self.state()
        self.enterContext(patch('observe.time.sleep'))
        # Make unsatisfied conditions expire on their first poll.
        self.enterContext(patch('text_observations.time.monotonic', side_effect=itertools.count(0, 9)))

    def state(self, *, hit=True, held=None):
        self.pass_no += 1
        x, y = self.pixel
        with self.controls.log.open('a', encoding='utf-8') as stream:
            active = self.active == self.hwnd
            down = self.held if held is None else held
            print('FONT_POINTER', self.pass_no, x, y, str(active).lower(), str(hit).lower(), str(down).lower(), file=stream)

    def read_cursor(self, position):
        position._obj.x, position._obj.y = self.pixel
        return True

    def activate(self, hwnd):
        self.active = hwnd
        self.state(hit=False)
        return True

    def move(self, x, y):
        self.pixel = x, y
        self.state()
        return True

    def post(self, hwnd, msg, key, pos):
        self.assertEqual(self.hwnd, hwnd)
        if msg == 0x200:
            self.move(pos & 0xffff, pos >> 16)
        if msg in (0x201, 0x202):
            self.held = msg == 0x201
            self.state()
        return True

    def posted(self):
        return [call.args[1] for call in self.controls.observer.post.call_args_list]

    def test_press_follows_two_witnessed_positions_on_the_owned_focused_field(self):
        self.active = 22
        self.state(hit=False)
        self.controls.click(70, 52)
        self.controls.activate.assert_called_once_with(self.hwnd)
        events = self.controls.pointer_events
        self.assertEqual([e['action'] for e in events], ['activate', 'move', 'move', 'button', 'button'])
        self.assertEqual([e['clientPixel'] for e in events[1:3]], [[71, 52], [70, 52]])
        self.assertLess(events[1]['fieldPass'], events[2]['fieldPass'])
        self.assertTrue(all(e['cursorMatched'] and e['cursorOnSubject'] for e in events[1:]))
        self.assertEqual(self.posted(), [0x201, 0x202])

    def test_drag_waits_for_the_pressed_field_at_the_end_before_releasing(self):
        self.controls.drag(45, 70, 52)
        self.assertEqual(self.posted(), [0x201, 0x202])
        final_move, release = self.controls.pointer_events[-2:]
        self.assertTrue(final_move['moveHeld'])
        self.assertEqual(final_move['clientPixel'], release['clientPixel'])
        self.assertGreater(final_move['fieldPass'], self.controls.pointer_events[1]['fieldPass'])

    def test_gone_or_old_delivery_without_current_field_hit_never_starts_a_click(self):
        def lost(x, y):
            self.move(x, y)
            self.state(hit=False)
            return True
        self.controls.set_position.side_effect = lost
        with self.assertRaisesRegex(MissingObservation, 'field pointer at') as error:
            self.controls.click(70, 52)
        self.assertFalse(error.exception.detail['lastFieldPointer']['fieldHit'])
        self.assertEqual(self.posted(), [])
        self.controls.set_position.side_effect = lambda *_: True
        self.pixel = 71, 52
        self.state()
        with self.assertRaisesRegex(MissingObservation, 'field pointer at'):
            self.controls.click(70, 52)
        self.assertEqual(self.posted(), [])

    def test_foreign_point_or_unavailable_foreground_prevents_cursor_motion_and_buttons(self):
        self.hit = 22
        with self.assertRaisesRegex(MissingObservation, 'uncovered point'):
            self.controls.click(70, 52)
        self.controls.set_position.assert_not_called()
        self.controls.first_gesture = True
        self.active = 22
        self.controls.activate.side_effect = lambda _: False
        with self.assertRaisesRegex(MissingObservation, 'active owned viewport'):
            self.controls.click(70, 52)
        self.controls.activate.assert_called_once_with(self.hwnd)
        self.controls.set_position.assert_not_called()
        self.assertEqual(self.posted(), [])

    def test_subsequent_drag_does_not_reactivate_a_window_that_lost_focus(self):
        self.controls.click(70, 52)
        self.active = 22
        self.state(hit=False)
        with self.assertRaisesRegex(MissingObservation, 'active owned viewport'):
            self.controls.drag(45, 70, 52)
        self.controls.activate.assert_not_called()
        self.assertEqual(self.posted(), [0x201, 0x202])

    def test_foreground_loss_or_cursor_change_after_hover_prevents_button(self):
        for cause in ('foreground', 'cursor'):
            with self.subTest(cause=cause):
                self.active = self.hwnd
                self.pixel = 70, 52
                self.state()
                if cause == 'foreground':
                    self.active = 22
                else:
                    self.pixel = 500, 301
                with self.assertRaises(MissingObservation):
                    self.controls.button(self.hwnd, 70, 52, True)
        self.assertEqual(self.posted(), [])

    def test_nonhosted_motion_only_posts_to_the_owned_window(self):
        self.controls.disposable = False
        self.controls.click(70, 52)
        self.controls.set_position.assert_not_called()
        self.assertEqual(self.posted(), [0x200, 0x200, 0x201, 0x202])

    def test_incomplete_stream_line_cannot_supply_a_new_hover_confirmation(self):
        text = 'FONT_POINTER 3 -1 -1 true false false\nFONT_POINTER 4 70 52 true true false'
        self.assertEqual(last_field_pointer(text)['pass'], 3)


if __name__ == '__main__':
    unittest.main()
