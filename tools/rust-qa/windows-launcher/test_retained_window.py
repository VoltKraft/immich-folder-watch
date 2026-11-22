"""Exercise native HWND/renderer/keyboard evidence for the retained launch and Shell cases."""
import unittest
from unittest.mock import Mock, patch

import observe
import retained_window as retained

TITLE = "Grüße – retained GUI"
FIRST_RENDER = ("GRAPHICS_ATTEMPT generation=1 policy=preferred\nGRAPHICS_MEMORY generation=1 hint=MemoryUsage\n"
                "GRAPHICS_READY generation=1\nADAPTER Dx12 Cpu Microsoft Basic Render Driver\n")


class OwnedRoot:
    def __init__(self, pid):
        self.pid, self.hwnd, self.shown = pid, 99, False
        self.events, self.life = [], []
        self.tid = 8
        self.title = TITLE
        self.on_close = lambda: None

    def show(self, tick, *, create=False):
        self.shown = True
        if create:
            self.life.append((self.hwnd, "create", tick))
        self.events.append(dict(event="show", hwnd=self.hwnd, root=True, winEventTimeMs=tick))

    def close_window(self, hwnd):
        if self.visible() != hwnd:
            raise ValueError("Expected visible test HWND")
        self.shown = False
        self.events.append(dict(event="hide", hwnd=hwnd, root=True, winEventTimeMs=12))
        self.on_close()

    def visible(self, **_kwargs):
        return self.hwnd if self.shown else None

    def is_visible(self, hwnd):
        return self.visible() == hwnd

    def owner(self, hwnd, pid):
        pid._obj.value = self.pid if hwnd == self.hwnd else 0
        return self.tid if hwnd == self.hwnd else 0

    def caption(self, hwnd, buf, _size):
        buf.value = self.title if hwnd == self.hwnd else ""
        return len(buf.value)

    def ancestor(self, hwnd, _flags):
        return hwnd

    def pump(self):
        pass

    def close(self):
        pass


class RetainedWindowTests(unittest.TestCase):
    def setUp(self):
        self.gui = OwnedRoot(12)
        self.record = {}
        self.desk = Mock()
        self.desk.name.return_value = "Default"
        self.enterContext(patch.object(retained, "WindowLifetime", return_value=Mock(events=self.gui.life)))
        self.enterContext(patch.object(retained, "visible_surface", side_effect=lambda *args: args[-2].update(surface=True)))
        self.trial = retained.RetainedWindow(self.desk, self.gui, TITLE, "Default", self.record)
        self.gui.show(4, create=True)
        self.trial.first(self.gui.hwnd, lambda: FIRST_RENDER, self.wait)

    def wait(self, observation, reason):
        if not observation():
            raise TimeoutError(reason)

    def test_close_show_uses_the_same_hidden_title_kernel_events_and_renderer(self):
        self.trial.close_window()
        self.assertTrue(self.trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n"))
        self.gui.show(24)
        self.trial.opened(99, lambda: FIRST_RENDER + "WINDOW_HIDDEN\n", self.wait)
        self.assertEqual([e["event"] for e in self.record["reopened"]["events"]], ["hide", "show"])
        self.assertEqual(self.record["lifetimeBeforeQuit"], [[99, "create", 4]])
        self.assertEqual(self.record["first"]["renderer"], self.record["reopened"]["renderer"])

    def test_same_numeric_hwnd_cannot_hide_recreation_changed_title_or_repeated_native_visibility(self):
        self.trial.close_window()
        self.gui.title = "another window"
        with self.assertRaisesRegex(ValueError, "title"):
            self.trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n")
        self.gui.title = TITLE
        self.gui.life.extend([(99, "destroy", 15), (99, "create", 16)])
        with self.assertRaisesRegex(ValueError, "created again"):
            self.trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n")
        del self.gui.life[1:]
        self.assertTrue(self.trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n"))
        self.gui.show(17)
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.trial.opened(100, lambda: FIRST_RENDER, self.wait)
        self.gui.show(18)
        with self.assertRaisesRegex(ValueError, "visibility events"):
            self.trial.opened(99, lambda: FIRST_RENDER, self.wait)

    def test_renderer_rejects_diagnostic_measurements_altered_generations_or_early_release(self):
        for row in ("GRAPHICS_ATTEMPT generation=2 policy=preferred", "GRAPHICS_READY generation=2", "WINDOW_RELEASED passes=5",
                    "WINDOW_WAKE mode=single", "GRAPHICS_MEMORY generation=1 hint=Performance", "ADAPTER Dx12 Cpu Other"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                retained.graphics(FIRST_RENDER + row, {})
        retained.graphics(FIRST_RENDER + "WINDOW_RELEASED passes=5\nDRAINED passes=5", {}, before_quit=False)
        for tail in ("WINDOW_RELEASED passes=0\nDRAINED passes=0", "WINDOW_RELEASED passes=5\nDRAINED passes=6"):
            with self.subTest(drain=tail), self.assertRaisesRegex(ValueError, "UI passes"):
                retained.graphics(FIRST_RENDER + tail, {}, before_quit=False)

    def test_callback_show_requires_the_actual_root_after_dispatch_including_uptime_wrap(self):
        wrap = 1 << 32
        self.gui.show(2)
        self.trial.activated_show(1, wrap - 2, wrap + 4, "callbackShow")
        for start, dispatch, observed in ((0, wrap - 2, wrap + 4), (1, wrap + 3, wrap + 5), (1, wrap - 2, wrap + 1)):
            with self.subTest(start=start, dispatch=dispatch), self.assertRaises(ValueError):
                self.trial.activated_show(start, dispatch, observed, "callbackShow")

    def test_a_visible_owned_window_without_real_foreground_and_keyboard_focus_is_preserved_as_a_failure(self):
        for missing in ("foreground", "focused", "active"):
            sample = dict(foreground=True, active=True, focused=True) | {missing: False}
            result = {}
            with (self.subTest(missing=missing), patch.object(retained, "focus_sample", return_value=sample),
                  patch.object(retained.time, "monotonic", side_effect=[0, 2]), self.assertRaisesRegex(ValueError, "focus")):
                self.trial.focus(result)
            self.assertTrue(result["sameWindowVisible"])
            self.assertFalse(result["observed"])
        self.trial.name = "IfwQa_Tray_private"
        with patch.object(retained, "focus_sample") as sample:
            self.trial.focus(result)
            sample.assert_not_called()
            self.assertFalse(result["applicable"])

    def test_single_focus_sample_requires_the_active_gui_threads_focused_descendant(self):
        self.desk.foreground.return_value = 99
        windows = Mock(pid=12)
        def owner(hwnd, pid):
            pid._obj.value = 12 if hwnd in (99, 100) else 13
            return 8
        windows.owner.side_effect = owner
        windows.ancestor.side_effect = lambda hwnd, _: 99 if hwnd == 100 else hwnd
        def get(tid, data):
            self.assertEqual(tid, 8)
            data._obj.active, data._obj.focus = 99, focus
            return True
        with (patch.object(retained.c, "WinDLL", create=True), patch.object(retained, "bind", return_value=get)):
            for focus, expected in ((100, True), (101, False)):
                self.assertEqual(retained.focus_sample(self.desk, windows, 99)["focused"], expected)


if __name__ == "__main__":
    unittest.main()
