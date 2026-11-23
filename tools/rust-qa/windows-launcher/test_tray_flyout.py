"""Regression controls for the original Explorer flyout and the two-color marker."""
from pathlib import Path
import os
import subprocess
import sys
import unittest

import native_tray as tray
from test_native_tray import KEY, RGB, RECT, SURFACE


class OriginalFlyoutTests(unittest.TestCase):
    def history(self):
        pane = dict(hwnd=61, windowClass="NotifyIconOverflowWindow", tid=144, pid=81)
        button = dict(pid=81, bar=51, runtimeId="92,4", nativeHit=88, point=[802, 744], bounds=[790, 720, 822, 768])
        return [dict(stage="baseline", bar=51, pid=81, cursor=[4, 3], pane=None),
                dict(stage="hint", markerObserved=False, surface=dict(SURFACE, rgb="eeeeee")),
                dict(stage="opening", button=button, name="Show hidden icons", method="Invoke"), dict(stage="opened", pane=pane),
                dict(stage="cleanup", attempted=True, restored=True, baselineRead=True,
                     original=None, final=None, observedOpen=pane, cursor=[4, 3], absentSamples=12, absentMs=876, iconAttempted=False)]

    def test_only_pinned_named_visible_pane_can_report_marker_on_relocated_hit_root(self):
        events = self.history()
        pane = events[3]["pane"]
        surface = dict(SURFACE, root=61, overflow=61, rootClass="NotifyIconOverflowWindow", pane=pane)
        tray.verify_marker_route(surface, events[0], events[3])
        with self.assertRaises(tray.Unavailable):
            tray.verify_marker_route(surface | {"pane": pane | {"tid": 987}}, events[0], events[3])
        tray.confirm_surface(dict(surface=surface), KEY, 101, RECT, RGB)
        for changed in (dict(root=62), dict(rootClass="Other"), dict(root=51, overflow=51),
                        dict(overflow=0), dict(monitor=0), dict(rgb="eeeeee"), dict(pane=dict(pane, tid=0))):
            with self.subTest(changed=changed), self.assertRaises((tray.Unavailable, ValueError)):
                tray.confirm_surface(dict(surface=surface | changed), KEY, 101, RECT, RGB)
        with self.assertRaises(tray.Unavailable):
            tray.confirm_surface(dict(surface=dict(surface, cursor=[4, 4])), KEY, 101, RECT, RGB, surface)
        with self.assertRaises(tray.Unavailable):
            tray.confirm_surface(dict(surface=surface | {"pane": pane | {"tid": 987}}), KEY, 101, RECT, RGB, surface)

    def test_native_close_required_even_if_explorer_reported_an_opening_error(self):
        events = self.history()
        baseline, opened = tray.provider_route(events, (81, 51), {}, final=True)
        self.assertIsNone(baseline["pane"])
        self.assertEqual(opened["pane"]["hwnd"], 61)
        partial = events[:3] + events[-1:]
        _, opened = tray.provider_route(partial, (81, 51), {}, final=True)
        self.assertIsNone(opened)
        for invalid in (events[:-1], events + [dict(stage="cleanup-failed")], events[:2] + list(reversed(events[2:4])) + events[4:],
                        events[:-1] + [events[-1] | {"iconAttempted": True}],
                        events[:2] + [events[2] | {"name": "Other taskbar control"}] + events[3:],
                        events[:-1] + [events[-1] | {"final": events[3]["pane"]}],
                        events[:-1] + [events[-1] | {"restored": False}],
                        events[:-1] + [events[-1] | {"absentMs": 0}],
                        events[:-1] + [events[-1] | {"absentSamples": 1}],
                        partial[:-1] + [partial[-1] | {"observedOpen": None}],
                        events[:-1] + [events[-1] | {"cursor": [0, 0]}]):
            with self.subTest(invalid=invalid), self.assertRaises(tray.CleanupUnconfirmed):
                tray.provider_route(invalid, (81, 51), {}, final=True)

    def test_preexisting_surface_cannot_be_taken_over_or_reported_as_owned(self):
        events = self.history()
        old = events[3]["pane"]
        baseline = events[0] | {"pane": old}
        cleanup = dict(stage="cleanup", attempted=False, restored=False, baselineRead=True, iconAttempted=False,
                       original=old, final=old, observedOpen=None, cursor=[4, 3])
        tray.provider_route([baseline, cleanup], (81, 51), {}, final=True)
        for invalid in ([baseline, *events[1:]], [baseline, cleanup | {"final": None}]):
            with self.assertRaises(tray.CleanupUnconfirmed):
                tray.provider_route(invalid, (81, 51), {}, final=True)

    @unittest.skipUnless(sys.platform == "win32", "Uses the native Windows PowerShell installation")
    def test_original_provider_restores_a_realized_action_after_a_com_error(self):
        host = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.run([host, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        Path(__file__).with_name("test_tray_flyout.ps1")], check=True, timeout=30)
