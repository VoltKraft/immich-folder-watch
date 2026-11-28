"""Portable controls for the installed WPF observer's passive Default desktop samples."""
from copy import deepcopy
from itertools import count
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverse.evidence import activation_desktop
from reverse.foreground import ForegroundSamples, verify
import private_desktop


class ForegroundTests(unittest.TestCase):
    def setUp(self):
        context = dict(windowStation="WinSta0", stationVisible=True, threadDesktop="Default", threadReceivesInput=True,
                       inputDesktop="Default", inputObjectReceivesInput=True, session=2, activeConsoleSession=2,
                       wts=dict(session=2, connectionState=0, lockFlags=1))
        self.row = dict(root=dict(hwnd=70, pid=11, tid=13), primary=dict(image=r"C:\fixture\Wpf.exe", created=120),
                        desktopBefore=context, desktopAfter=context)
        self.proc = SimpleNamespace(pid=11, _handle=51, poll=lambda: None)
        self.launch = SimpleNamespace(ordinary_console=lambda state, name: state == context and name == "Default")
        self.api = SimpleNamespace(clock=count(1000).__next__, process_identity=lambda handle: 120)
        self.desk = Mock(spec_set=["context", "thread_desktop", "thread", "owner", "pid_session", "ancestor",
                                  "count_top_level_window", "window", "foreground"])
        self.desk.context.return_value = context
        self.desk.thread_desktop.return_value = 73
        self.desk.pid_session.return_value = 2
        self.desk.ancestor.side_effect = lambda hwnd, _kind: hwnd
        self.desk.count_top_level_window.return_value = 1
        def owner(hwnd, pid):
            pid._obj.value = 11 if hwnd == 70 else 20
            return 13 if hwnd == 70 else 21
        self.desk.owner.side_effect = owner
        def metadata(hwnd):
            own = hwnd == 70
            return dict(hwnd=hex(hwnd), pid=11 if own else 20, tid=13 if own else 21,
                        executable="Wpf.exe" if own else "Shell.exe", rect=[-32, 0, 700, 450],
                        title="Excluded", **{"class": "WPF Class" if own else "Other Class"})
        self.desk.window.side_effect = metadata
        self.samples = ForegroundSamples(True, self.launch, self.api, self.desk, 73, 2, self.proc, self.row)

    def sample(self, name="foregroundAtStartup"):
        self.samples.record(name)
        return verify(self.row, name, 2)

    def test_two_stable_roots_record_only_window_metadata(self):
        self.desk.foreground.return_value = 90
        value = self.sample()
        self.assertEqual(value["relation"], "otherRoot")
        self.assertEqual(value["foreground"], {"class": "Other Class", "basename": "Shell.exe",
                                               "bounds": [-32, 0, 700, 450], "desktop": "Default", "session": 2})
        self.assertEqual(value["root"]["basename"], "Wpf.exe")
        for extra in ({"title": "other window"}, {"pid": 20}, {"basename": r"C:\other\Shell.exe"},
                      {"session": 7}, {"bounds": [0, 0, False, 5]}):
            with self.subTest(extra=extra), patch.dict(value["foreground"], extra), self.assertRaises(ValueError):
                verify(self.row, "foregroundAtStartup", 2)

    def test_own_missing_and_switching_foreground_are_distinct(self):
        for readings, relation in (((70, 70), "wpfRoot"), ((0, 0), "none"), ((90, 70), "changed")):
            with self.subTest(relation=relation):
                self.desk.foreground.side_effect = readings
                value = self.sample()
                self.assertEqual(value["relation"], relation)
                self.assertEqual(value["foreground"], value["root"] if relation == "wpfRoot" else None)

    def test_unqualified_foreign_window_is_never_inspected(self):
        self.desk.foreground.return_value = 90
        for prop, implementation in (("count_top_level_window", lambda _,hwnd: int(hwnd == 70)),
                                     ("pid_session", lambda pid: 2 if pid == 11 else 9)):
            with self.subTest(prop=prop), patch.object(self.desk, prop, side_effect=implementation):
                self.desk.window.reset_mock()
                value = self.sample()
                self.assertEqual(value["relation"], "unavailable")
                self.assertIsNone(value["foreground"])
                self.desk.window.assert_called_once_with(70)

    def test_switched_desktop_or_exited_process_discards_the_observation(self):
        self.desk.foreground.return_value = 90
        state = self.desk.context.return_value
        for states in (({**state, "session": 3},), (state, {**state, "inputDesktop": "another"})):
            with self.subTest(states=states):
                self.desk.context.side_effect = states
                value = self.sample()
                self.assertEqual((value["relation"], value["root"], value["foreground"]), ("unavailable", None, None))
        self.desk.context.side_effect = None
        with patch.object(self.proc, "poll", return_value=0):
            self.desk.window.reset_mock()
            self.assertEqual(self.sample()["relation"], "unavailable")
            self.desk.window.assert_not_called()
        self.samples.enabled = False
        self.desk.reset_mock()
        self.samples.record("private")
        self.assertNotIn("private", self.row)
        self.assertFalse(self.desk.mock_calls)

    def test_missing_native_metadata_is_a_diagnostic(self):
        self.desk.foreground.return_value = 90
        metadata = self.desk.window.side_effect
        def partial(hwnd):
            raw = metadata(hwnd)
            if hwnd == 90:
                raw["executable"] = {"win32Error": 5}
            return raw
        self.desk.window.side_effect = partial
        self.assertEqual(self.sample()["foreground"]["basename"], {"win32Error": 5})
        self.desk.window.side_effect = OSError(5, "lookup failed")
        refused = self.sample()
        self.assertEqual((refused["relation"], refused["win32Error"]), ("unavailable", 5))

    def test_detached_activation_uses_each_original_phase_interval(self):
        self.desk.foreground.return_value = 70
        self.sample()
        self.row["before"] = dict(qpc=self.api.clock())
        self.row["after"] = dict(qpc=self.api.clock())
        self.sample("foregroundAfterReactivation")
        self.sample("foregroundBeforeQuit")
        self.row["quit"] = {"issuedQpc": self.api.clock()}
        with TemporaryDirectory() as temp:
            args = (Path(temp), {"target": private_desktop.ARM}, self.row, "")
            activation_desktop(*args, completed=True)
            for phase,bound in (("foregroundAtStartup", "endQpc"), ("foregroundAfterReactivation", "beginQpc"),
                                ("foregroundBeforeQuit", "endQpc")):
                value = deepcopy(self.row[phase])
                value[bound] = 1 if bound == "beginQpc" else 100000
                with self.subTest(phase=phase), patch.dict(self.row, {phase: value}), self.assertRaises(ValueError):
                    activation_desktop(*args, completed=True)
