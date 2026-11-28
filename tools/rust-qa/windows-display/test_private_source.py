from copy import deepcopy
from pathlib import Path
import runpy
import unittest

HERE = Path(__file__).resolve().parent
PRIVATE = runpy.run_path(str(HERE / "private_source.py"))
NAME = "IfwQa_" + "a" * 32


def console(name):
    return dict(windowStation="WinSta0", stationVisible=True, threadDesktop=name, inputDesktop=name,
                threadReceivesInput=True, inputObjectReceivesInput=True, session=2, activeConsoleSession=2,
                wts=dict(session=2, connectionState=0, lockFlags=1))


class PrivateSourceTests(unittest.TestCase):
    def test_only_the_selected_named_input_on_the_unlocked_console_can_receive_the_edit(self):
        eligible = PRIVATE["DISPLAY"]["eligible_input"]
        transport = dict(status="observed", code=0, transport="console")
        self.assertTrue(eligible(console(NAME), transport, NAME))
        self.assertFalse(eligible(console("Default"), transport, NAME))
        self.assertFalse(eligible(console(NAME), {**transport, "code": 2}, NAME))
        self.assertFalse(eligible(console(NAME), transport, None))
        self.assertFalse(eligible(console(NAME), transport, "Default"))
        self.assertFalse(eligible({**console(NAME), "threadReceivesInput": False}, transport, NAME))

    def test_missing_restore_unobserved_frame_wrong_worker_or_extra_qualification_cannot_pass(self):
        session = dict(created=dict(requested=NAME, actual=NAME), switchToFixture=True, beforeSwitch=console("Default"),
                       returnedDesktop=console("Default"), afterSwitch=console(NAME), cleanup=dict(inputAfterRestore="Default",
                       switchBack=True, namedClosed=True, originalHandleClosed=True), workerExit=0, jobClosed=True,
                       workerPid=34, subject="canonical", source="0"*40, run="10", attempt="1")
        member = dict(pid=45, hwnd=567, tid=125, witness="0x12", counts=dict(window=1,witness=1), desktop=NAME)
        observation = dict(originalWindow=dict(pid=45,hwnd=567,session=2), privateWindowBefore=member, privateWindowAfter=member,
                           privateWorkerPid=34, requestedPrivateDesktop=NAME, desktop=console(NAME), protocol=dict(status="observed",
                           code=0, transport="console"), subject="canonical", host="github-hosted", target=PRIVATE["TARGET"],
                           build=dict(source="0"*40), run="10", attempt="1", status="observed", requiredQualifications=["source-frame"],
                           unmetQualifications=[], hiddenEnumerationWindow="0x12", hiddenWindowDestroyed=True, mixedDpiPassed=None,
                           rdpRenderingObserved=None, rdpSessionObserved=False, inventoryPassed=True, sourceFrameObserved=True,
                           profileRemoved=True, drained=True, closedToSupervisor=True, subjectExit=0)
        verify = PRIVATE["verify_session"]
        verify(session, observation, NAME)
        for owner, key, value in (("session", "returnedDesktop", console(NAME)), ("session", "switchToFixture", False),
                                  ("session", "workerExit", 1), ("observation", "privateWorkerPid", 191),
                                  ("observation", "sourceFrameObserved", False), ("observation", "mixedDpiPassed", True),
                                  ("observation", "rdpRenderingObserved", True), ("observation", "privateWindowAfter", {}),
                                  ("observation", "hiddenWindowDestroyed", False), ("observation", "closedToSupervisor", False)):
            with self.subTest(key=key):
                s, o = deepcopy(session), deepcopy(observation)
                (s if owner == "session" else o)[key] = value
                with self.assertRaises(ValueError):
                    verify(s, o, NAME)
