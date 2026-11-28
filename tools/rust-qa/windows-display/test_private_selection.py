from copy import deepcopy
import unittest

from private_selection import verify_selection
from test_private_source import NAME, console


class PrivateSelectionTests(unittest.TestCase):
    def test_focus_direction_origin_and_return_desktop_are_required(self):
        session = dict(workerPid=10, workerExit=0, jobClosed=True, beforeSwitch=console("Default"),
                       returnedDesktop=console("Default"), created=dict(requested=NAME, actual=NAME),
                       afterSwitch=console(NAME), switchToFixture=True,
                       cleanup=dict(inputAfterRestore="Default", switchBack=True, namedClosed=True,
                                    originalHandleClosed=True), build=dict(binarySha256="ab" * 32))
        worker = dict(pid=10, before=console(NAME), after=console(NAME), exit=0, hiddenWindowDestroyed=True,
                      profileRemoved=True, transport=dict(status="observed", code=0, transport="console"))
        field = dict(status="passed", observerDesktop=NAME, binarySha256="AB" * 32, primaryPid=92, secondaryPid=95,
                     firstHwnd=24, reopenedHwnd=61, profileRemoved=True, closedAlive=True, primaryExit=0, secondaryExit=0)
        initial = "Grüße – Sommer.jpg"
        stages = field["stages"] = {}
        for stage, hwnd, value, index, selected in (
                ("beforeClose", 24, initial, 2, "üße"), ("afterReopen", 61, initial, 2, "üße"),
                ("afterShiftLeft", 61, initial, 1, "rüße"), ("afterReplacement", 61, "Gx – Sommer.jpg", 2, "")):
            stages[stage] = dict(pid=92, hwnd=hwnd, foregroundHwnd=hwnd, inputDesktop=True, focusedElementMatches=True,
                                 hasKeyboardFocus=True, foreground=True, value=value, document=value,
                                 selection=dict(start=index, text=selected))
        verify_selection(session, worker, field, NAME)
        for stage, key, wrong in (("afterReopen", "hasKeyboardFocus", False), ("afterReopen", "foregroundHwnd", 24),
                                  ("afterShiftLeft", "selection", {"start": 2, "text": "üß"}),
                                  ("afterReplacement", "document", initial), ("afterReplacement", "pid", 95)):
            with self.subTest(stage=stage, key=key):
                broken = deepcopy(field)
                broken["stages"][stage][key] = wrong
                with self.assertRaises(ValueError):
                    verify_selection(session, worker, broken, NAME)
        with self.assertRaises(ValueError):
            verify_selection({**session, "returnedDesktop": console(NAME)}, worker, field, NAME)
        with self.assertRaises(ValueError):
            verify_selection(session, {**worker, "transport": {"status": "observed", "code": 2, "transport": "RDP"}},
                             field, NAME)
