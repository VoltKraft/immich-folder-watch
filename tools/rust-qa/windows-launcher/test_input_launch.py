"""Controls for the gesture, foreground caller and retained-window outcome on any build host."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import input_launch
import input_gesture
from input_gesture import DOWN, UP, F24, InputUnavailable, KeyWindow, accept_key


def event(msg, **changes):
    row = dict(hwnd=51, vk=F24, message=msg, time=701, repeats=1, previous=int(msg == UP), released=int(msg == UP),
               extra=912, dispatchThread=103)
    return {**row, **changes}


def completed():
    root = dict(pid=12, tid=9, hwnd=52, title="Desktop input probe", desktop="IfwQa_test")
    events = [dict(event=name, hwnd=52, root=True, winEventTimeMs=tick)
              for name, tick in (("show", 600), ("hide", 650), ("show", 730))]
    return dict(stage="drained", secondaryLaunch=dict(api="CreateProcessW", source="foreground-key-handler", callerPid=17),
                primaryPid=12, secondaryPid=21, secondaryCreation100ns=823, initialWindow=52, reopenedWindow=52,
                suspendedSecondary=dict(events=2, tick=713, resumeReturnedMs=714),
                windowReadbacks={"reopen": {"recentPrimaryEvents": events}},
                retainedWindow=dict(first=dict(root, showEvent=events[0]), hidden=dict(root, hideEvent=events[1]),
                                    reopened=dict(root, events=events[1:]), secondaryShow=dict(earliestMs=713,
                                    releasedByMs=714, observedMs=740, distinctTicks=True, status="ordered",
                                    showEvent=events[-1], showMs=730, basis="distinctTicks")),
                foregroundHandoff=dict(grant="granted", requestAccepted=True), foregroundObservation=dict(observed=True),
                keyboardFocus=dict(observed=True, lastSample=dict(foreground=True, active=True, focused=True)),
                inputGesture=dict(hwnd=51, callerPid=17, callerThread=103, marker=912, keys=[event(DOWN), event(UP)],
                                  beforeQueue=dict(owner=True, privateInput=True, foreground=True, focus=True, visible=True,
                                                   centerOwned=True, foregroundAfter=True),
                                  beforeCreate=dict(hwnd=51, thread=103, tick=710),
                                  created=dict(pid=21, creation100ns=823, parentPid=17, parentCreation100ns=433,
                                               image="native-gui-assessment.exe", foreground=51, tick=712),
                                  queued=2, windowDestroyed=True))


class InputLaunchTests(unittest.TestCase):
    def test_detached_post_ipc_receipt_requires_a_hidden_owned_root_before_the_original_show(self):
        cycle = completed()
        retained = cycle["retainedWindow"]
        root = {k: retained["first"][k] for k in ("pid", "tid", "hwnd", "title", "desktop")}
        retained["afterTrigger"] = dict(field="secondaryShow", pid=12, root=root, trigger={"secondaryPid": 21},
                                        queryBeganMs=720, eventCursor=2, state="retainedRootHidden")
        retained["secondaryShow"]["basis"] = "observedHiddenAfterTrigger"
        input_launch.check_handoff(cycle, 17)
        for key, bad in (("eventCursor", 3), ("queryBeganMs", 731), ("trigger", {"secondaryPid": 22})):
            damaged = deepcopy(cycle)
            damaged["retainedWindow"]["afterTrigger"][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                input_launch.check_handoff(damaged, 17)

    def test_secondary_queries_visibility_only_after_successful_resume_and_before_returning_to_the_handler(self):
        observe = input_launch.observe
        name = "IfwQa_" + "1" * 32
        for resume_ok in (True, False):
            with self.subTest(resume_ok=resume_ok):
                api, desk, proc = Mock(), Mock(), Mock()
                actions = []
                desk.name.side_effect = ["WinSta0", name, name]
                desk.receiving_input.return_value = True
                def resume():
                    actions.append("resume")
                    if not resume_ok:
                        raise ValueError("ResumeThread failed")
                proc.resume.side_effect = resume
                def witness(child):
                    self.assertIs(child, proc)
                    actions.append("query")
                with (patch.object(observe, "start_named", return_value=proc),
                      patch.object(observe, "ordinary_console", return_value=True)):
                    trial = observe.child(api, desk, name, None, [], None, {"IFW_QA_INVENTORY_TOKEN": "1" * 32},
                                          None, False, private=False, named_input=True, after_resume=witness)
                    if resume_ok:
                        with trial:
                            actions.append("handler")
                    else:
                        with self.assertRaisesRegex(ValueError, "ResumeThread"), trial:
                            self.fail("A failed resume returned a child")
                self.assertEqual(actions, ["resume", "query", "handler"] if resume_ok else ["resume"])

    def test_keyboard_target_or_modifier_change_never_submits_input_or_starts_the_secondary(self):
        for target, modifier in (([False], 0), ([True, False], 0), ([True], -32768)):
            with self.subTest(target=target, modifier=modifier):
                window = KeyWindow.__new__(KeyWindow)
                window.owned_input, window.key_state, window.send = Mock(side_effect=target), Mock(return_value=modifier), Mock()
                window.marker = 19
                create = Mock()
                with patch.object(input_gesture.c, "sizeof", return_value=40), self.assertRaises(InputUnavailable):
                    window.launch(create)
                create.assert_not_called()
                window.send.assert_not_called()

    def test_one_tagged_queue_transition_required_for_election(self):
        valid = []
        self.assertFalse(accept_key(valid, 51, 912, event(DOWN)))
        self.assertTrue(accept_key(valid, 51, 912, event(UP)))
        for initial, row in (([], event(UP)), (valid, event(UP)), ([], event(DOWN, previous=1)),
                             ([], event(DOWN, repeats=3)), ([], event(DOWN, extra=0)),
                             ([], event(DOWN, hwnd=53)), ([event(DOWN)], event(UP, vk=0)),
                             ([event(DOWN)], event(UP, released=0))):
            with self.subTest(row=row), self.assertRaises(ValueError):
                accept_key(list(initial), 51, 912, row)

    def test_held_caller_checks_immediately_bracket_process_creation(self):
        key = KeyWindow.__new__(KeyWindow)
        key.hwnd, key.pid, key.desk = 51, 17, Mock()
        key.desk.thread.return_value = 103
        key.owned_input = Mock(return_value=True)
        key.clock = Mock(side_effect=(710, 712))
        key.record = dict(keys=[event(DOWN), event(UP)])
        api, proc, exe = Mock(), Mock(), Mock()
        proc.pid, proc._handle, exe.name = 21, 33, "native-gui-assessment.exe"
        api.processes.return_value = {21: (17, exe.name)}
        api.process_identity.side_effect = (823, 433)
        key.before_create()
        key.observe_child(api, proc, exe)
        expected = completed()["inputGesture"]
        self.assertEqual(key.record["beforeCreate"], expected["beforeCreate"])
        self.assertEqual(key.record["created"], expected["created"])
        for foreground, parent in ((True, 99), (False, 17)):
            with self.subTest(foreground=foreground, parent=parent):
                key.owned_input.return_value = foreground
                api.processes.return_value[21] = (parent, exe.name)
                with self.assertRaises(ValueError):
                    key.observe_child(api, proc, exe)
        with self.assertRaises(ValueError):
            key.before_create()

    def test_receipt_rejects_observer_launch_or_foreign_focus_or_worker(self):
        current = completed()
        input_launch.check_handoff(current, 17)
        for nested, field, value in (
                ("secondaryLaunch", "source", "observer"), ("inputGesture", "windowDestroyed", False),
                ("keyboardFocus.lastSample", "focused", False), ("inputGesture.created", "foreground", 52),
                ("inputGesture.beforeCreate", "tick", 800), ("inputGesture.beforeCreate", "thread", 111),
                ("inputGesture.created", "creation100ns", 824), ("inputGesture.created", "parentPid", 18),
                ("inputGesture", "queued", 1), ("inputGesture", "marker", 913),
                ("inputGesture.beforeQueue", "centerOwned", False),
                ("inputGesture", "keys", [event(DOWN), event(UP, dispatchThread=99)]),
                ("foregroundHandoff", "grant", "denied"), ("foregroundHandoff", "requestAccepted", False),
                ("foregroundObservation", "observed", False), ("", "reopenedWindow", 53)):
            copy = deepcopy(current)
            row = copy
            for part in filter(None, nested.split(".")):
                row = row[part]
            row[field] = value
            with self.subTest(nested=nested, field=field), self.assertRaises(ValueError):
                input_launch.check_handoff(copy, 17)

    def test_only_the_original_retained_build_qualifies(self):
        ordinary = dict(subject="retained", revision="r", target="x", run="2", attempt="1", gui="g",
                        buildReceipt="b", graph="d", lock="l")
        input_launch.check_build("x", ordinary, ordinary)
        for field in ordinary:
            with self.subTest(field=field), self.assertRaises(ValueError):
                input_launch.check_build("x", {**ordinary, field: "different"}, ordinary)


if __name__ == "__main__":
    unittest.main()
