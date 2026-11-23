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

    def test_only_a_single_shortcut_marker_for_the_observed_hidden_root_counts(self):
        self.trial.close_window()
        log = FIRST_RENDER + "WINDOW_HIDDEN\n"
        marker = "RETAINED_VISIBILITY first=hide hwnd=99\n"
        self.assertTrue(self.trial.hidden(log))
        self.assertFalse(self.record["hidden"]["winitVisibilityShortcut"])
        self.assertTrue(self.trial.hidden(marker + log))
        self.assertTrue(self.record["hidden"]["winitVisibilityShortcut"])
        for invalid in (marker.replace("99", "91"), marker + marker):
            with self.subTest(marker=invalid), self.assertRaisesRegex(ValueError, "visibility marker"):
                self.trial.hidden(invalid + log)

    def test_reopen_requires_its_own_marker_in_the_completed_native_log(self):
        hide = "RETAINED_VISIBILITY first=hide hwnd=99\n"
        show = "RETAINED_VISIBILITY first=show hwnd=99\n"
        early = FIRST_RENDER + hide + "WINDOW_HIDDEN\n"
        drained = "WINDOW_RELEASED passes=4\nDRAINED passes=4\n"
        self.trial.close_window()
        self.assertTrue(self.trial.hidden(early))
        self.gui.show(24)
        self.trial.opened(99, lambda: early, self.wait)
        for actual in ("", show):
            retained.graphics(early + actual + drained, self.record, before_quit=False)
            self.assertEqual(self.record["reopened"]["winitVisibilityShortcut"], bool(actual))
        for mistaken in (early + show + show, early + show.replace("99", "31"),
                         early.replace(hide, show) + hide, early.replace(hide, "") + show):
            with self.subTest(log=mistaken), self.assertRaisesRegex(ValueError, "visibility markers"):
                retained.graphics(mistaken + drained, self.record, before_quit=False)

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
        self.assertTrue(self.trial.activated_show(1, wrap - 2, wrap + 4, "callbackShow"))
        self.assertTrue(self.trial.activated_show(1, wrap - 2, wrap + 2, "callbackShow"))
        self.assertEqual(self.record["callbackShow"]["basis"], "distinctTicks")
        for start, dispatch, observed in ((0, wrap - 2, wrap + 4), (1, wrap + 3, wrap + 5), (1, wrap - 2, wrap + 1)):
            with self.subTest(start=start, dispatch=dispatch), self.assertRaises(ValueError):
                self.trial.activated_show(start, dispatch, observed, "callbackShow")

    def test_shared_tick_or_show_inside_resume_call_remains_inconclusive_without_an_independent_hidden_observation(self):
        self.gui.show(100)
        for field, earliest, resume, observed in (("callbackShow", 100, None, 101), ("secondaryShow", 100, 100, 101),
                                                 ("secondaryShow", 98, 100, 101), ("secondaryShow", 99, 103, 104),
                                                 ("callbackShow", (1 << 32) + 100, None, (1 << 32) + 101)):
            with self.subTest(field=field, earliest=earliest):
                self.trial.sample_after_trigger(field, {"source": field}, lambda: earliest)
                self.assertFalse(self.trial.activated_show(1, earliest, observed, field, released_by=resume))
                self.assertEqual(self.record["afterTrigger"]["state"], "visible")
                row = self.record[field]
                self.assertEqual((row["showEvent"]["winEventTimeMs"], row["status"]), (100, "inconclusive"))
        for earliest, resume, upper in ((101, 102, 106), (99, 106, 105), (100, 99, 105), (99, 100, 35_100)):
            with self.subTest(bounds=(earliest, resume, upper)), self.assertRaisesRegex(ValueError, "outside"):
                self.trial.activated_show(1, earliest, upper, "secondaryShow", released_by=resume)

    def test_hidden_owned_root_after_the_acknowledged_trigger_orders_the_next_show_even_on_the_same_tick(self):
        self.trial.close_window()
        self.assertTrue(self.trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n"))
        start = len(self.gui.events)
        self.trial.sample_after_trigger("secondaryShow", {"secondaryPid": 34}, lambda: 100)
        self.assertEqual(self.record["afterTrigger"]["state"], "retainedRootHidden")
        self.gui.show(100)
        self.trial.opened(99, lambda: FIRST_RENDER + "WINDOW_HIDDEN\n", self.wait)
        self.assertTrue(self.trial.activated_show(start, 99, 101, "secondaryShow", released_by=100))
        self.assertEqual(self.record["secondaryShow"]["basis"], "observedHiddenAfterTrigger")
        self.assertFalse(self.trial.activated_show(start, 100, 101, "callbackShow"))
        self.gui.show(100)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.trial.activated_show(start, 99, 101, "secondaryShow", released_by=100)

    def test_background_start_needs_a_complete_post_callback_enumeration_without_the_future_root(self):
        for pid, title, count, handle, early_create, expected in ((12, "tray receiver", 1, 43, False, True),
                (12, TITLE, 1, 99, False, False), (12, "hidden helper", 1, 99, False, False),
                (12, "helper", 2, 43, False, False), (13, "foreign", 1, 43, False, False),
                (12, "tray receiver", 1, 43, True, False)):
            with self.subTest(title=title, count=count, pid=pid):
                gui = OwnedRoot(12)
                gui.desktop = 4
                scan = dict(desktop="Default", ownedCount=count, windows=[
                    dict(hwnd=handle, pid=pid, desktop="Default", title=title, titleAtLimit=False, titleError=0)])
                trial = retained.RetainedWindow(self.desk, gui, TITLE, "Default", {})
                trial.lifetime = Mock(events=gui.life)
                if early_create:
                    gui.life.append((99, "create", 90))
                with patch.object(retained, "desktop_windows", return_value=scan):
                    trial.sample_after_trigger("callbackShow", {"pid": 12, "ordinal": 1, "observedMs": 100}, lambda: 100)
                gui.show(100, create=not early_create)
                trial.hwnd = 99
                self.assertEqual(trial.activated_show(0, 100, 101, "callbackShow"), expected)

    def test_delayed_show_must_be_generated_after_the_hidden_query_even_when_the_activation_ticks_differ(self):
        # The first two traces reproduce a SHOW generated during resume or before the acknowledged Shell delivery.
        cases = (("secondaryShow", 98, 104, None, 104, 100, False),
                 ("callbackShow", 100, None, 108, 108, 100, False),
                 ("callbackShow", 100, None, 115, 115, 106, False),
                 ("callbackShow", 100, None, 108, 114, 110, False),
                 ("callbackShow", 100, None, 108, 104, 110, False),
                 ("callbackShow", 100, None, 100, 100, 100, True),
                 ("secondaryShow", 98, 104, None, 104, 104, True))
        for field, earliest, returned, ack, query, generated, expected in cases:
            with self.subTest(field=field, ack=ack, query=query, generated=generated):
                gui = OwnedRoot(12)
                trial = retained.RetainedWindow(self.desk, gui, TITLE, "Default", {})
                trial.lifetime = Mock(events=gui.life)
                gui.show(3, create=True)
                trial.first(99, lambda: FIRST_RENDER, self.wait)
                trial.close_window()
                self.assertTrue(trial.hidden(FIRST_RENDER + "WINDOW_HIDDEN\n"))
                start = len(gui.events)
                trigger = {"secondaryPid": 34} if ack is None else {"pid": 12, "ordinal": 1, "observedMs": ack}
                calls = []
                def clock():
                    calls.append("clock")
                    return query
                def hidden(hwnd):
                    calls.append("IsWindowVisible")
                    return gui.visible() == hwnd
                with patch.object(gui, "is_visible", side_effect=hidden):
                    trial.sample_after_trigger(field, trigger, clock)
                self.assertEqual(calls, ["clock", "IsWindowVisible"])
                gui.show(generated)
                trial.opened(99, lambda: FIRST_RENDER + "WINDOW_HIDDEN\n", self.wait)
                self.assertEqual(trial.activated_show(start, earliest, 120, field, released_by=returned), expected)
                self.assertEqual(trial.record["afterTrigger"]["queryBeganMs"], query)
                self.assertEqual(trial.record[field]["showMs"], generated)
                self.assertEqual(trial.record[field]["status"], "ordered" if expected else "inconclusive")

    def test_windowless_query_requires_a_compatible_create_generation_tick_before_the_same_root_show_across_wrap(self):
        wrap = 1 << 32
        for created, expected in ((0, False), (1, True), (2, True), (3, False)):
            with self.subTest(created=created):
                gui = OwnedRoot(12)
                gui.desktop = 4
                trial = retained.RetainedWindow(self.desk, gui, TITLE, "Default", {})
                trial.lifetime = Mock(events=gui.life)
                calls = []
                def clock():
                    calls.append("clock")
                    return wrap + 1
                def scan(*args):
                    calls.append("EnumDesktopWindows")
                    return dict(desktop="Default", ownedCount=0, windows=[])
                with patch.object(retained, "desktop_windows", side_effect=scan):
                    trial.sample_after_trigger("callbackShow", {"pid": 12, "observedMs": wrap}, clock)
                self.assertEqual(calls, ["clock", "EnumDesktopWindows"])
                gui.life.append((99, "create", created))
                gui.show(2)
                trial.first(99, lambda: FIRST_RENDER, self.wait)
                self.assertEqual(trial.activated_show(0, wrap - 2, wrap + 3, "callbackShow"), expected)
                self.assertTrue(trial.record["callbackShow"]["distinctTicks"])
                if expected:
                    self.assertEqual(trial.record["callbackShow"]["createMs"], wrap + created)
                else:
                    self.assertIn("CREATE", trial.record["callbackShow"]["reason"])

    def test_unavailable_launcher_timing_yields_to_an_independent_functional_failure(self):
        for failure_at in (None, "shellLess", "foreground"):
            def visit(name, row):
                row["cleanupConfirmed"] = True
                if name == failure_at:
                    raise ValueError("worker changed")
                raise retained.ShowOrderUnavailable("simultaneous Windows ticks")
            rows = {}
            issue = observe.run_cases(visit, rows)
            self.assertIsInstance(issue, ValueError if failure_at else retained.ShowOrderUnavailable)
            self.assertEqual([rows[name]["status"] for name in ("shellLess", "foreground")],
                             ["failed" if name == failure_at else "unavailable" for name in ("shellLess", "foreground")])

    def test_inconclusive_shell_clock_preserves_worker_keyboard_and_normal_quit_evidence(self):
        import native_tray
        from test_native_tray import ResidentTests

        activated = retained.RetainedWindow.activated_show
        closed = native_tray.NativeTray.check_drain
        observed = {}
        def shared_tick(trial, start, earliest, upper, field, **kwargs):
            trial.windows.events[-1]["winEventTimeMs"] = earliest
            return activated(trial, start, earliest, upper, field, **kwargs)
        def capture_drain(probe, proc, job, log, result):
            closed(probe, proc, job, log, result)
            observed.update(result)
        with (patch.object(retained.RetainedWindow, "activated_show", shared_tick),
              patch.object(native_tray.NativeTray, "check_drain", capture_drain),
              self.assertRaises(retained.ShowOrderUnavailable)):
            ResidentTests().exercise(None, subject="retained", reopen=True)
        self.assertEqual(observed["retainedWindow"]["callbackShow"]["status"], "inconclusive")
        self.assertEqual(observed["workerBefore"], observed["workerAfter"])
        self.assertTrue(observed["keyboardFocus"]["observed"])
        self.assertTrue(observed["quitRequested"] and observed["nativeShutdown"]["jobEmpty"])

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
